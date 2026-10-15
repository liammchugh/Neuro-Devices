# 3.3 V EMG Analog Front End — Engineering Design Report
**Project:** Brain-Controlled Guitar Pedal / compact wearable EMG | **Revision:** Concept A, 10 October 2026  
**Status:** Preliminary engineering design for isolated bench evaluation. **NOT a production schematic, patient-connected device, or safety-certified design.**

## Executive summary
Design a compact three-electrode surface electromyography (sEMG) acquisition board operating from one regulated 3.3 V rail, replacing the existing ±9 V muscle-sensor arrangement. A precision instrumentation amplifier rejects common-mode interference, a mid-supply reference allows bipolar EMG waveforms to be represented as positive ADC voltages, selectable gain prevents saturation, an analog band-pass and anti-alias network conditions the signal, and a XIAO ESP32-S3 acquires it using ADC1 GPIO1 (D0). The initial target is a **benchtop proof of concept with simulated differential input**, not a human-connected prototype.

**Design targets:** three input terminals (EMG+, EMG−, reference electrode); regulated 3.3 V; nominal midrail 1.65 V; approximate sEMG passband 20–450 Hz (reassess for intended muscle/motion tasks); variable total gain initially 50–250 V/V; 2 kSPS or higher if measuring raw EMG; optional digitally computed 1 kHz envelope stream; DC baseline centered around 1.65 V. Keep all electrode and analog circuitry within a battery-powered isolated domain and never attach body electrodes while the board is directly USB-connected to a computer.

## 1. Inputs and reference-project findings
Available reference inputs are `headband_flexpcb.PrjPcb`, `main.SchDoc`, `PCB1.PcbDoc`, and `headband_flexpcb.BomDoc` (Altium files) plus photographs of the present red muscle-sensor PCB and its dual-supply power/output connectors. The readable BOM identifies a project using an STM32WB5MMG family wireless MCU and USB-C hardware. The Altium schematic/PCB are binary Compound Document files; their complete net connectivity has **not** been independently reconstructed or electrical-rule-checked here. Do not infer that the headband reference contains an INA333, an EMG AFE, or any particular sensor input net. The pictured ±9 V analog board is a separate reference, and its exact amplifier part number and permitted output range are not confirmed. Accordingly, this report is a proposed new schematic, **not** a verified Altium conversion.

## 2. Key specifications and engineering decisions
| Item | Target / decision |
|---|---|
| Supply | 3.3 V ±5%, regulated, low-noise battery-derived |
| Analog ground | AGND = physical ground; VMID = buffered 1.65 V signal reference, never relabel as ground |
| Electrode interface | Differential EMG+, EMG−; third reference electrode via passive bias network during benchtop development |
| Instrumentation stage | INA333 (1.8–5.5 V supply), proposed first-stage gain G1=11 using RG=10 kΩ |
| Gain after AC coupling | Configurable non-inverting gain G2 ≈5.7 or 21; prefer switchable resistor footprints |
| Signal passband | HP ≈19.4 Hz; low-pass 400–450 Hz target for raw sEMG acquisition |
| Sampling | Recommend ≥2 kSPS raw acquisition and sufficiently steep analog anti-alias attenuation above Nyquist; 1 kSPS only with carefully designed lower-cutoff analog filter |
| ADC output | 0–3.3 V absolute electrical limits; nominal VMID ≈1.65 V; restrict operating swing with headroom |
| Interface | J_OUT: ADC_OUT, AGND, optional VMID_MON; XIAO GPIO1 / D0 |
| Validation | Simulated signals only until isolated power, limiting, creepage/clearance, fault analysis and human-use review |

**Why gain matters:** For ±5 mV differential input, total gain 231 gives ≈±1.155 V excursions around 1.65 V, assuming the electrodes and input stage remain within common-mode range. Higher offsets and movement artifacts can saturate either stage. A switchable second-stage gain is strongly recommended.

## 3. Functional schematic and exact net suggestions
### 3.1 Power, decoupling and virtual reference — sheet `01_Power_Reference`
- J_PWR.1 = `+3V3_A`, J_PWR.2 = `AGND`. This connector is for a **regulated** 3.3 V battery-powered domain; do not connect raw batteries or ±9 V.
- U3 `OPA2333` dual amplifier (SOIC-8), supply pin 8=`+3V3_A`, pin 4=`AGND`. C101 100 nF X7R and C102 1 µF X7R directly between U3 pins 8 and 4.
- R101 100 kΩ, +3V3_A→VMID_RAW; R102 100 kΩ, VMID_RAW→AGND; C103 1 µF, VMID_RAW→AGND.
- U3A: pin 3 (+)=VMID_RAW, pin 2 (−)=VMID, pin 1 (OUT)=VMID. C104 1 µF from VMID→AGND is **optional only after assessing U3 capacitive-load stability**; otherwise use a series isolation resistor and local bypass at each load. This midrail buffer drives amplifier reference/bias networks; calculate worst-case sourcing/sinking current.
- Add TP_VDD, TP_GND, TP_VMID, TP_VMID_RAW. Optional ferrite bead from digital `3V3` to analog `+3V3_A`, with local capacitors, subject to return-current review. Do not introduce a separated floating ground plane.

### 3.2 Electrode input, protection and bias — sheet `02_Electrodes_Protection`
- J_ELEC is a clearly keyed, touch-safe, three-contact connection: J_ELEC.1=`ELEC_P`, .2=`ELEC_N`, .3=`ELEC_REF`. Physically label electrode names rather than colors; lead color codes are not universal.
- R201 and R202 each 100 kΩ: ELEC_P→IN_P and ELEC_N→IN_N. Treat these as **functional current-limiting resistors only**, not as proof of protection in single-fault human exposure. Actual electrodes need a formal protection/isolation design and its own review.
- R203 and R204 each 10 MΩ: IN_P→VMID and IN_N→VMID, providing DC return for amplifier input bias currents. Keep matched.
- C201 and C202 each 100 pF C0G: IN_P→AGND and IN_N→AGND; C203 100 pF C0G: IN_P→IN_N. These are candidate RF suppression components; test CMRR degradation due to tolerance and parasitics. Place after the series resistance and close to the INA input pins.
- R205 1 MΩ: ELEC_REF→VMID is a **passive reference-bias hypothesis** only. A third-electrode topology is not automatically equivalent to a driven-right-leg circuit, and it requires common-mode and leakage testing. Do **not** implement an active driven electrode without a separate stability, fault-current and compliance analysis.
- Protection device footprints: add optional low-leakage, low-capacitance clamp placeholders for input-to-rail protection, but leave their final parts/topology **TBD** pending input-leakage, current-limit, fault, and measurement-bandwidth review. Generic TVS components may leak enough to overwhelm a microvolt-level EMG input.

### 3.3 Instrumentation amplifier — sheet `03_Instrumentation`
U1 = TI INA333, VSSOP-8 (DGK), pins: 1 RG_A, 2 IN−, 3 IN+, 4 V−, 5 REF, 6 OUT, 7 V+, 8 RG_B. Connection table:
| Pin | Connect to |
|---|---|
| 1 | R301 terminal A |
| 2 | IN_N |
| 3 | IN_P |
| 4 | AGND |
| 5 | VMID |
| 6 | INA_OUT |
| 7 | +3V3_A |
| 8 | R301 terminal B |

R301=10 kΩ between pins 1 and 8; G1 = 1 + 100 kΩ/R301 = 11. C301 100 nF between pins 7 and 4 as close as possible; C302 1 µF nearby. TP_INA_OUT to observe DC saturation. Review the INA333 datasheet input common-mode **versus differential output swing** plots at the selected gain and single 3.3 V supply: rail-to-rail labeling does not guarantee unrestricted common-mode range at all gains.

### 3.4 High-pass and adjustable post-gain — sheet `04_AC_Coupling_Gain`
- C401 100 nF film or stable dielectric, INA_OUT→HP_NODE. R401 82 kΩ, HP_NODE→VMID, giving f_HP≈1/(2π·82k·100n)=19.4 Hz.
- U3B OPA2333: pin 5 (+)=HP_NODE; pin 6 (−)=GAIN_FB; pin 7 (OUT)=GAIN_OUT.
- R402 10 kΩ from GAIN_FB→VMID; R403 selectable from GAIN_OUT→GAIN_FB: populate 47 kΩ for G2=5.7 (total ~62.7) initially, or 200 kΩ for G2=21 (total ~231) after baseline and artifact measurements. Use mutually exclusive resistor options or a solder-jumper footprint, not parallel links.
- **Correction to earlier proposal:** placing 2.2 nF only across R403 reduces high-frequency *excess gain* toward unity; it does **not** create a conventional unity-to-zero low-pass filter. Do not count this capacitor as the sole anti-alias filter.
- OPA2333 GBW typical 0.35 MHz and slew rate ~0.16 V/µs. At G2=21 approximate closed-loop bandwidth is ~16.7 kHz before other limits; bandwidth is ample for 450 Hz, but simulated transient recovery and output load still need confirmation. A different amplifier may be selected after noise evaluation.

### 3.5 Analog low-pass / anti-alias / ADC — sheet `05_Filter_ADC`
- A single R=4.7 kΩ plus C=100 nF (fc≈339 Hz) is an easy functional filter after GAIN_OUT, but at 1 kSPS its ~4.5 dB attenuation at 500 Hz is **insufficient as an anti-alias solution**. Even two gentle poles may allow meaningful aliasing from broadband EMG.
- Recommended **Rev A test design**: allocate a footprint for a 2nd-order unity-gain low-pass section plus an RC pole and test point, implemented with an additional rail-to-rail op-amp U4 (e.g., OPA2333 channel A, after simulation) and a properly calculated Butterworth/Bessel-style topology. First select the sampling regime:
  - **Preferred raw EMG:** sample ADC at 2–4 kSPS and pass approximately 20–450 Hz. Design analog stopband attenuation for the chosen Nyquist frequency after quantifying ADC/noise budget; e.g., specify target ≥40 dB at Nyquist for out-of-band interference and assess if a higher-order stage is needed.
  - **If fixed at 1 kSPS:** reduce analog passband (e.g., ~20–250 Hz), design 4th-order or otherwise adequately selective low-pass, and document the remaining EMG spectral information that is lost.
- Place R501 1 kΩ–4.7 kΩ and C501 10–100 nF as a final ADC charge reservoir / RC conditioner only after checking sample-and-hold acquisition loading and filter-output stability. Route `ADC_OUT` through a test point to J_ADC.1; J_ADC.2=AGND. Add option for buffered ADC output if required.
- Device protection must be designed so **all normal and single-fault conditions** respect GPIO1's allowed terminal voltage. Power sequencing is important: a live sensor driving an unpowered ESP32 can inject current through ESD diodes. Use a current-limiting and isolation strategy appropriate to this fault.
- GPIO1 on the XIAO ESP32-S3 is D0/A0 (ADC1 channel 0). ADC continuous/DMA configuration must explicitly parse ESP32-S3 DMA result metadata. Log sample indices and buffer-overrun statistics; USB receive timestamps do not represent acquisition timing.

## 4. Schematic sheet boundaries and KiCad practical guidance
**Root project:** `EMG_AFE_3V3.kicad_pro`, `EMG_AFE_3V3.kicad_sch`, `EMG_AFE_3V3.kicad_pcb`.
Suggested hierarchical sheets: `01_Power_Reference.kicad_sch`, `02_Electrodes_Protection.kicad_sch`, `03_Instrumentation.kicad_sch`, `04_AC_Coupling_Gain.kicad_sch`, and `05_Filter_ADC.kicad_sch`.

**Signal net names:** `+3V3_A`, `AGND`, `VMID_RAW`, `VMID`, `ELEC_P`, `ELEC_N`, `ELEC_REF`, `IN_P`, `IN_N`, `INA_OUT`, `HP_NODE`, `GAIN_FB`, `GAIN_OUT`, `ADC_OUT`. Avoid ground symbols on VMID; it is a **biased analog reference net**.

**Recommended schematic practices:** place power flags only for real external regulated sources; give every sheet explicit hierarchical pins; use component symbols matching the **manufacturer pinout**, then choose footprints based on the corresponding orderable MPN; annotate test points, filter variant footprints, net ties only when actually needed, no-connect marks on genuinely unused pins; include title block, revision, schematic notes, assembly variant field, manufacturer MPN fields, and measured test limits. Run KiCad ERC before PCB layout; resolve rather than blindly suppress pin-type errors.

**PCB:** Start with a 2-layer rigid 0603 prototype (larger packages are acceptable), continuous AGND return plane, guarded/high-impedance input traces where appropriate, well-matched differential parasitics and RC placement, input connector separated from MCU USB/RF antennas, local supply decoupling, quiet VMID return, test points for every gain/filter stage. Leave optional external ADC and isolated telemetry footprints for an eventual wearable revision. Separate analog input area physically from DC/DC switches and digital traces. Keep schematic subcircuits modular so the flexible-headband design can later reuse the verified AFE, without treating its original binary PCB as automatically electrically equivalent.

## 5. Preliminary BOM (functional, not safety-complete)
| Ref | Qty | Part / Value | Function |
|---|---:|---|---|
| U1 | 1 | INA333IDGKR / VSSOP-8 | Differential amplifier |
| U3 | 1 | OPA2333AIDR / SOIC-8 | VMID buffer + gain stage |
| U4 | 1 | TBD low-noise RRIO op-amp | Proper multi-pole analog low-pass filter |
| R101–102 | 2 | 100 kΩ 1% 0603 | Midrail divider |
| R201–202 | 2 | 100 kΩ 1% 0603 | Functional input series limiting |
| R203–204 | 2 | 10 MΩ 1% 0603 | Input-bias return |
| R205 | 1 | 1 MΩ 1% 0603 | Passive reference-electrode bias (experimental) |
| R301 | 1 | 10 kΩ 1% 0603 | INA333 gain G1=11 |
| C201–203 | 3 | 100 pF C0G 0603 | RF filtering |
| C401/R401 | 1 ea. | 100 nF / 82 kΩ | 19.4 Hz high-pass |
| R402/R403 | 1 ea. | 10 kΩ / 47 kΩ or 200 kΩ | Selectable post gain |
| C101–104, C301–302 | 6 | 100 nF / 1 µF as designated | Supply/reference decoupling |
| J_ELEC | 1 | Touch-safe keyed 3-contact | Electrode connector (final selection TBD) |
| J_PWR, J_ADC | 1 ea. | Appropriate connector | Power and ADC interface |
| TP | 8+ | SMD test pads | Verification |
| AAF network | TBD | R/C based on designed topology | Anti-aliasing; not yet fully specified |

**BOM caveat:** The number of components in the low-pass filter, its precise op-amp arrangement, input safety components, battery regulator, USB isolation, and test-point count are intentionally pending safety and SPICE reviews. Ordering this BOM alone cannot yield a fully functional, verified human-use board.

## 6. Electrical analysis / tolerances
- **Midrail:** 3.3 V×100k/(100k+100k)=1.65 V nominal. Divider resistance and leakage introduce finite output bias; buffer handles reference drive but remains a potential single point of failure.
- **First gain:** 11 V/V using 10 kΩ RG. **Second selectable gain:** 5.7 or 21 V/V. **Total midband gain:** ~62.7 or 231 V/V (ignoring filter transmission).
- **High-pass:** ~19.4 Hz. For 100 nF with actual ±10% tolerance and 82 kΩ ±1%, calculate the range and test the assembled pole.
- **ADC swing:** With a nominal ±1.3 V useful budget around VMID, approximate ideal unclipped differential input amplitude is ±20.7 mV at total G=62.7 or ±5.6 mV at G=231. True limits depend on input common mode, amplifier output swing, ADC loading and waveform artifacts.
- **INA333 input noise:** datasheet typical ~50 nV/√Hz at 1 kHz; input-referred integrated noise increases with measurement bandwidth and environmental pickup. Evaluate electrode contact impedance, 50/60 Hz common-mode rejection, ADC effective number of bits and input-referred noise as a system.
- **No arbitrary clamp choice:** leakage currents through protective diodes or dirty PCB surfaces can produce offsets across 10 MΩ resistors. Evaluate under worst-case humidity, temperature and fault conditions.
- **ADC and filtering:** a median filter is useful for isolated glitches but distorts raw spectral information; retain unfiltered ADC samples, and calculate a rectified/envelope channel digitally for muscle activation. Keep bandpass, rectification and smoothing in distinct signal-processing stages.

## 7. Bench verification and acceptance criteria
1. **No body electrodes.** Apply regulated 3.3 V to the analog domain with a current-limited, isolated power source. Verify supply rails, idle current, 1.65 V VMID within tolerance, and no excessive startup transients.
2. Replace electrode inputs with a low-impedance synthetic differential source at a valid common-mode voltage ~1.65 V; inject 100 Hz, 1 mVpp. Check first-stage gain ≈11 and selected total gain, allowing tolerance/filter effects.
3. Test 10 Hz, 20 Hz, 100 Hz, 300 Hz, 450 Hz, 1 kHz, 2 kHz sweeps. Record measured transfer function, stopband attenuation, noise floor and settling; confirm filter target and Nyquist alias budget before fabricating Rev B.
4. Verify 50/60 Hz common-mode rejection with a controlled test setup; intentionally mismatch input impedances to evaluate susceptibility and stability.
5. Sweep DC common-mode and electrode offsets within device ratings; ensure recoverable saturation without long lockups or unintended output excursions.
6. Test the analog output unloaded and with the ESP ADC input; verify 0–3.3 V compliance and power-off sequencing/current limits.
7. Exercise XIAO DMA acquisition at 2/4 kSPS, test 20-minute dropout counters and reconstruct sample timing from hardware sample index, not OS serial timestamps.
8. Perform independent electrical-safety review before any on-body use. Evaluate insulation/isolation barriers, leakage, ESD, contact/connector touch safety, single-fault behavior and intended regulatory scope (IEC 60601-1 and IEC 60601-1-2 may be relevant for medical use, but applicability depends on intended purpose).

## 8. Main risks, prioritization and next revision
**P0 (before fabrication):** qualify input common-mode range and bipolar power/reference behavior; design true anti-alias low-pass; establish power-isolation architecture; complete ADC overvoltage/power-off protection; simulate full netlist; verify symbol/footprint/MPN.
**P1:** alternative lower-noise amplifier trade study; switchable gain; lead-off detection; active common-mode drive only with dedicated safety/stability review; optional 24-bit external ADC.
**P2:** wireless battery-powered telemetry, headband flex integration, size/assembly optimization, impedance monitoring and artifact rejection.

**Rev A deliverables recommended:** (a) ERC-clean KiCad hierarchical schematic; (b) SPICE simulation and gain/filter report; (c) design review checklist and BOM with sourced manufacturer numbers; (d) 2-layer rigid test PCB; (e) firmware that retains raw ADC and metadata; (f) isolated bench test report. **Do not treat this concept document as approved for human-connected acquisition.**

## 9. References
- Texas Instruments INA333 datasheet and product page: https://www.ti.com/product/INA333 and https://www.ti.com/lit/gpn/ina333
- Texas Instruments OPA2333 product/datasheet: https://www.ti.com/product/OPA2333
- Espressif ESP32-S3 ADC continuous driver: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/peripherals/adc_continuous.html
- User-provided Altium files: `headband_flexpcb.PrjPcb`, `main.SchDoc`, `PCB1.PcbDoc`, `headband_flexpcb.BomDoc` (limited verification as noted).
