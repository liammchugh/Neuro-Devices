# Review: 3.3 V EMG Analog Front End (Concept A, 10 Oct 2026)

The signal chain is sound and most of the arithmetic checks out (G1 = 11, G2 = 5.7 / 21, totals 62.7 / 231, HP 19.4 Hz, ±5.6 mV input at G = 231, INA333 DGK and OPA2333 SOIC-8 pinouts, XIAO D0 = GPIO1 = ADC1_CH0). The issues below are what I'd settle before layout, most important first.

## 1. Grounding vs. the guitar (architecture decision, settle first)

A guitarist's hands touch the strings, and the strings are bonded to the amp's audio ground (usually mains earth). So the player's body is already tied to audio ground. This design biases the body to VMID (1.65 V) through the reference electrode.

- If the EMG board shares ground with the pedal's audio path, the strings hold the body at 0 V while the reference electrode pulls it to 1.65 V. That pushes a DC current through the body (about 1.65 µA through the 1 MΩ today, milliamps if the reference is made low impedance as suggested below), and leaves the INA333 inputs at 0 V, outside its input common-mode range (V− + 0.1 V).
- Isolation is therefore a hard requirement for this use case, not a later nice-to-have. The cleanest version is already your P2 idea: make the EMG board a battery-powered wearable and send data to the pedal over BLE / ESP-NOW from the XIAO. Then the only thing tied to the body is the battery-powered island.
- Decide now whether this board lives **on the pedal** or **on the body**. That changes the connector, the power section and the board outline.

## 2. Reference electrode impedance is too high (R205 = 1 MΩ)

Mains displacement current into the body is typically around 0.2–1 µA. Through 1 MΩ that gives roughly 0.2–1 V of 50/60 Hz common mode, which eats most of the 3.3 V headroom. Mismatched electrode impedances then turn that into a differential signal across the 10 MΩ bias resistors: 1 V × 50 kΩ mismatch / 10 MΩ ≈ 5 mV, which is as big as the EMG itself. CMRR can't help, because the conversion happens before the INA.

- Fix: tie ELEC_REF to VMID through tens of kΩ (10–47 kΩ is a reasonable starting range) instead of 1 MΩ. At 47 kΩ the common mode drops to around 25 mV. This is only acceptable once item 1 (isolation) is settled.

## 3. First-stage gain vs. electrode DC offset

The INA333 sits ahead of the AC coupling, so DC half-cell offsets get gained by 11. With about ±1.6 V of output swing around VMID, the tolerable electrode offset is about ±145 mV. Gelled Ag/AgCl usually stays well under that, but dry or poorly prepped electrodes can exceed it, and then the INA saturates and the 19 Hz high-pass can't recover it.

- Consider G1 ≈ 5–6 (RG ≈ 20–25 kΩ) and move the gain into stage 2. INA333 noise barely changes: at G = 11 it's already about 53 nV/√Hz input-referred.

## 4. Anti-alias filter and the U4 contradiction

- U3 is a dual: channel A is the VMID buffer and channel B is the gain stage. The report proposes "U4 (e.g., OPA2333 channel A)", but that channel is already used. U4 has to be a separate part.
- The alias spec is aimed at the wrong frequency. What matters is attenuation at fs − f_pass (the frequency that folds onto your 450 Hz band edge), not at Nyquist. At 2 kSPS that's 1550 Hz, where a 4th-order Butterworth at 450 Hz already gives about 43 dB.
- Simplest concrete plan: sample at 4–8 kSPS (the ESP32-S3 continuous ADC handles this easily), decimate in firmware, and use one unity-gain Sallen-Key 2nd-order Butterworth stage. Suggested starting point to simulate: R1 = R2 = 10 kΩ, C2 (to ground) = 22 nF C0G, C1 (feedback) = 47 nF C0G, which gives fc ≈ 495 Hz and Q ≈ 0.73. At 4 kSPS the fold frequency is 3.55 kHz, where this stage gives about 34 dB, and the ADC RC adds more.
- Use a second OPA2333 for U4 (the spare half can buffer ADC_OUT or VMID_MON). It's the same LCSC part, so there's no extra extended-part fee. An OPA4333 quad that replaces U3 also works.

## 5. ADC RC values can cut the passband

R501 1–4.7 kΩ with C501 10–100 nF spans a pole from 339 Hz to 16 kHz. 4.7 kΩ / 100 nF puts the pole at 339 Hz, inside the EMG band. Pick something like 1 kΩ + 10–22 nF (7–16 kHz). That gives plenty of charge reservoir for the ESP32-S3's few-pF sample capacitor.

## 6. ESP32-S3 ADC realities

- At 12 dB attenuation the usable range is about 0–3.1 V, and it's nonlinear near the ends, not a clean 0–3.3 V. Budget roughly ±1.3 V around 1.65 V (the report already does) and use eFuse calibration.
- Wire VMID_MON to a second ADC1 pin (D1 / GPIO2) and subtract it in firmware. That cancels supply and divider drift for free.
- Power sequencing: if the AFE runs from the XIAO's own 3V3 (through a ferrite and LC), the AFE can never be live while the ESP32 is unpowered, which removes the injection-current fault the report worries about. If it gets a separate supply, the series resistor into GPIO1 needs to limit current to ESD-diode-safe levels.

## 7. Smaller items

- **BOM MPN error:** "INA333IDGKR" isn't an orderable part. Use **INA333AIDGKR**.
- **C401 "film, 100 nF"** doesn't come in 0603 / SMT-assembly form at JLC. Either use 10 nF C0G with R401 = 820 kΩ (same 19.4 Hz), or accept X7R (it sees almost no DC here).
- **C104 on the VMID buffer:** the OPA2333 won't like 1 µF directly on its output. Plan for a 47–100 Ω series isolation resistor footprint now.
- **RFI filter:** f_diff ≈ 5.3 kHz and f_cm ≈ 16 kHz are fine. TI's guidance is Cdiff ≥ 10 × Ccm to swamp mismatch, so consider C203 = 1 nF. At 50/60 Hz the effect is small either way.
- **Input series resistor noise:** two 100 kΩ resistors add about 57 nV/√Hz, comparable to the INA333's 50 nV/√Hz, for about 1.6 µVrms total over 20–450 Hz. That's acceptable, but 47 kΩ halves it if the safety review allows.
- **Power section is unspecified:** pick the regulator before layout (low-noise LDO from LiPo, or filtered XIAO 3V3).
- **Electrode connector:** a 3.5 mm TRS jack matches common snap-electrode cable kits and is easy to source on JLC.

## 8. JLCPCB sourcing

All three TI parts are on LCSC, as extended parts, so each unique one adds the extended-part setup fee. Stock moves, so check before ordering:

| Part | LCSC # |
|---|---|
| INA333AIDGKR (VSSOP-8) | C19450 |
| OPA2333AIDR (SOIC-8) | C38732 |
| OPA2333AIDGKR (VSSOP-8 alt) | C19608 |

Generic 0603 resistors and X7R capacitors mostly fall in the basic library. 10 MΩ, 82 kΩ and the C0G filter capacitors may be extended, so check each one when assigning LCSC numbers. In KiCad, add an `LCSC` field to every symbol, and the kicad-jlcpcb-tools plugin will generate the BOM/CPL. The XIAO isn't JLC-assemblable, so give it header or castellated footprints and hand-solder it.

## Pre-layout checklist

1. Choose on-body wireless vs. on-pedal isolated architecture (item 1).
2. Lower R205 to tens of kΩ.
3. Decide G1 (11 vs. about 5).
4. Fix the sample rate (suggest 4 kSPS) and add U4 with the Sallen-Key + ADC RC.
5. Pick the regulator and connectors.
6. Correct the MPNs, assign LCSC numbers, and run a quick LTspice / ngspice pass on the full chain.
