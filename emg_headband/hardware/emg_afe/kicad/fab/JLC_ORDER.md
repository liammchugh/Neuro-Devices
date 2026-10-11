# Ordering Rev A at JLCPCB (flex PCB + assembly)

Files, all in this folder:

| File | Use |
|---|---|
| `emg_wearable_revA_gerbers.zip` | Board upload (copper, mask, silk, outline, drills, stiffener layer) |
| `emg_wearable_revA_bom_jlc.csv` | Assembly BOM (LCSC part numbers) |
| `emg_wearable_revA_cpl_jlc.csv` | Assembly placement (positions and rotations) |

## 1. Upload the board

1. On jlcpcb.com, choose **Order now** and upload `emg_wearable_revA_gerbers.zip`.
2. Check that the preview shows a 62.5 × 25.4 mm board with rounded corners.

## 2. PCB options

- **Base material:** Flex.
- **Layers:** 2.
- **Quantity:** 5 is the minimum.
- **Thickness:** the default 2-layer flex thickness, about 0.11 mm.
- **Surface finish:** ENIG, the flex default.
- **Coverlay colour:** any.
- **Stiffener:** FR4, 0.2 mm, on the bottom side. Put this in the stiffener notes or remark:
  "Stiffener: FR4 0.2 mm on the bottom side, per the Stiffener layer
  (emg_wearable_revA-Stiffener.gbr), 3 areas. Everything outside them is flex."

## 3. Assembly

1. Turn on **PCB Assembly**, top side only. Accept the tooling holes or edge rails if JLC adds them.
2. Upload `emg_wearable_revA_bom_jlc.csv` as the BOM and `emg_wearable_revA_cpl_jlc.csv` as the CPL. If it asks for column mapping, use Comment / Designator / Footprint / LCSC Part #, and Designator / Mid X / Mid Y / Layer / Rotation.
3. On the parts page:
   - Every line should match an LCSC part.
   - Check stock for ADS1298IPAGR (C527440) and the jack J1 (C4991872).
   - If anything shows "shortage", tell me and I'll pick a substitute.
4. Expect 54 placed parts. These are not placed, and that's intentional:
   - J3: the LiPo solder pads.
   - TP1 to TP10: test pads.

## 4. Placement preview (most important step)

Check each of these against the silkscreen or pad outline, and rotate in JLC's tool if it's off:

- **U1, ADS1298 (TQFP-64):** the pin 1 dot matches the board's pin 1 marker.
- **U2, ESP32-S3 module:** the antenna end is at the left board edge, over the copper-free area.
- **J7, USB-C:** the opening faces the bottom board edge.
- **J6, FPC connector:** the opening faces the right board edge.
- **J1, jack:** the plug opening faces the right board edge.
- **SOT-23 and SOT-23-5 parts** (U6, U7, U8, U9, Q101): pin 1 matches.
- **D101 diode:** the cathode band matches the silkscreen.

### Rotation corrections already applied to the CPL

KiCad and JLC's part models disagree on a few rotations. These are already
corrected in `emg_wearable_revA_cpl_jlc.csv`, from JLC's preview on 11 Oct 2026:

| Part | KiCad rotation | JLC rotation |
|---|---|---|
| J1 (jack) | -90 | 180 |
| J6 (FPC) | 90 | 270 |
| U1 (ADS1298, TQFP-64) | 180 | 90 |
| U6, U8, U9 (SOT-23-5), U7 (SOT-23-6) | 0 | 270 |
| Q101 (SOT-23) | 0 | 180 |

If the board is re-exported from KiCad, apply the same offsets again.

## 5. Order

Confirm and pay. JLC engineers sometimes email a question about the stiffener, the through-hole USB shell tabs, or a rotation. Forward it to the thread if you're unsure.

## After it arrives

- Solder a protected LiPo to J3: + is the left pad, − is the right pad, as marked.
- Flash over USB-C. If USB doesn't enumerate, short TP10 (BOOT) to GND, then tap TP9 (EN) to GND.
- Follow "Bring-up" in `../../README.md` before using body electrodes.
