# Review: EMG_AFE_3V3 design report (Concept A)

Overall: the architecture is sound and the math checks out (G1 = 11, G2 = 5.7 / 21, HP 19.4 Hz, midrail 1.65 V, swing budgets). The safety framing is right for a bench-only Rev A. These are the changes I'd make before we lay out the board, most important first.

## Fix before layout

1. **Settle the anti-alias problem by sampling faster, not by building a steeper filter.** What matters is attenuation at fs − 450 Hz, the lowest frequency that folds back into the passband, not at Nyquist. A 2nd-order Butterworth at 450 Hz gives about 21 dB at 1.55 kHz (fs = 2 k) but about 36 dB at 3.55 kHz (fs = 4 k). A 4th-order gives about 43 dB / 72 dB. Recommendation: sample at 4 kSPS (easy for ESP32-S3 continuous mode), use a 4th-order Sallen-Key built from a second OPA2333, then decimate digitally. That closes the U4 "TBD" with a part already on the BOM.

2. **Fix the input RFI cap ratio.** With C201 = C202 = C203 = 100 pF, any mismatch in the common-mode caps turns CM noise straight into a differential signal. TI's guidance for INA inputs is C_diff ≥ 10 × C_cm. With the 100 k series resistors, a good set is **C201/C202 = 22 pF C0G, C203 = 220 pF C0G**: differential corner about 1.7 kHz, CM corner about 72 kHz. Don't go up to 1 nF differential, because with 100 k that pulls the corner down to about 390 Hz, inside the EMG band.

3. **Lower the INA gain a little to tolerate electrode offset.** The INA333 stage is DC-coupled, so electrode half-cell offset gets multiplied by 11 before C401 removes it. ±1.55 V of output headroom / 11 = about ±140 mV of differential offset before the first stage saturates. Gel Ag/AgCl is usually fine; dry or mismatched electrodes may not be (IEC 60601-2-47 designs for ±300 mV). Suggest **RG = 20 k (G1 ≈ 6)**, which tolerates about ±250 mV, and take the difference back in G2 (R403 = 100 k / 390 k for G2 ≈ 11 / 40, total ≈ 66 / 240).

4. **Strengthen the reference electrode.** With R205 = 1 MΩ, the body is only weakly tied to VMID. Typical 0.1–1 µA of mains displacement current puts roughly 0.1–1 V of 60 Hz common mode on the body. CMRR then has to reject all of it, and it also eats INA333 common-mode headroom at 3.3 V. Consider 100–220 kΩ (still ≤ 33 µA worst-case fault at 3.3 V for bench use), or leave a footprint for a DRL later. Either way, this is a candidate for the safety review.

## Worth changing

5. **HP network: use 820 k + 10 nF C0G 0603 instead of 82 k + 100 nF film.** Same 19.4 Hz, but cheaper, smaller, a stock JLC part, and no X7R piezo/microphonic effects. OPA2333 bias current through 820 k is negligible.
6. **VMID buffer load.** OPA333-family parts don't like large capacitive loads. Plan on 20–50 Ω in series out of U3A before C104, and feed the INA333 REF pin from the buffer side (REF wants low impedance for CMRR).
7. **Correct the MPN:** INA333**A**IDGKR (the report says INA333IDGKR). OPA2333AIDR is correct.
8. **Minor:** the 4.7 k / 100 n single pole is about 5.0 dB down at 500 Hz, not 4.5 dB.

## For the KiCad / JLCPCB build

9. **Use a flat schematic or two or three sheets instead of five.** The board is about 35 parts, and hierarchy adds pin bookkeeping (and is the more fragile part of the MCP schematic tools) without much benefit at this size.
10. **Decide board scope:** does the XIAO plug onto this board (headers), or do we only break out J_ADC? Is there an on-board low-noise LDO from a LiPo, or is regulated 3.3 V brought in? Both change the outline and connectors.
11. **JLC sourcing:** INA333 and OPA2333 will be "extended" parts at JLC assembly (one-time fee per unique part). I'll check live stock and LCSC numbers with the MCP's JLCPCB search before we lock the BOM, and lean toward 0603 basic parts for the passives.
12. **Leave a footprint for lead-off detection** (for example, comparators on IN_P/IN_N vs. rails) even if it's unpopulated in Rev A.
