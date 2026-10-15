# EMG wearable Rev A: pre-order design review (11 Oct 2026)

Scope: goals, schematic, layout, BOM and JLC placement for
`kicad/emg_wearable_revA.*` at commit 5e6353a.

## Verdict

**Update, later on 11 Oct:** the on/off switch, battery monitor and charge LED below are now in the design, and the input caps are 100 pF. Re-checked: ERC 0 errors, DRC 0 errors, all nets routed. The board is ready to order once the new parts look right in JLC's preview.

Original verdict: the board was ready to order **except for power on/off**. With no switch, the
board is always on while a battery is soldered in. The ESP32 can deep-sleep,
but the ADS1298 and both regulators keep drawing current. Two small additions
are worth making at the same time (see "Recommended changes").

## 1. Goals vs design

| Requirement | Status | Where |
|---|---|---|
| 1, 2 or 3 EMG channels by firmware mode, no rework | Met | ADS1298 CH1–CH3; unused channels powered down in firmware |
| One TRS jack + flex-array connector, shared REF | Met | J1 (CH1), J6 FH34SRJ 12-pin (CH1–CH3), all REF on `RLD_ELEC` |
| Series resistor on every input | Met | 22 kΩ + 1 nF C0G per line |
| Passive USB/battery handling, no switches | Met | D101 + Q101 path to VSYS, MCP73831 charger |
| Dedicated low-noise analog rail | Met | LP5907 3.0 V (6.5 µVrms) |
| Protected LiPo | Assumed | J3 pads expect a cell with its own protection board |
| USB serial debug | Met | ESP32-S3 native USB-Serial-JTAG on USB-C |
| Wide capture, filters in firmware | Met | ADS1298 to 32 kSPS; input RC at about 7 kHz |
| Lead-off detection | Met | ADS1298 LOFF, RLDIN on the REF net |
| JLC-assembled, ≤ 2.5" × 1" flex | Met | 62.5 × 25.4 mm, 2-layer flex, all parts JLC-placed except the LiPo |
| USB-C points down the spine | Met | J7 on the bottom long edge |
| **Turn it off on battery** | **Missing** | Raised by Liam at review |

## 2. Schematic

Checks done:
- **ERC:** 0 errors. 2 expected warnings: TESTP pins tied to AVDD, as the datasheet asks.
- **Rails against part limits:**
  - VSYS ≤ 4.75 V on USB. The LP5907 is rated to 5.5 V, the AP2112 to 6 V, the MCP73831 to 6 V.
  - ADS1298 AVDD 3.0 V and DVDD 3.3 V (AVDD − DVDD = −0.3 V, allowed range −2.1 to 3.6 V).
  - AO3401A Vgs ≤ 5 V (rated ±12 V).
- **ADS1298 support parts:** match datasheet Figure 106.
  - VCAP1 22 µF; VCAP2/3/4 1 µF.
  - VREFP 10 µF + 100 nF.
  - RLD feedback 1 MΩ ∥ 1.5 nF, plus a 330 kΩ series limit (DC fault current < 10 µA).
  - RESV1 and DAISY_IN to ground, CLKSEL high.
- **ESP32-S3 boot:**
  - EN has a 10 kΩ / 1 µF RC.
  - No strapping pin (IO0, IO3, IO45, IO46) drives anything at reset.
  - USB D± on IO19/IO20.
- **Power path:** USB carries the load while the charger tops up an isolated battery. MCP73831 charge termination therefore works normally.

Findings:
- **S1 (must fix): no off state.** The battery feeds VSYS through Q101 whenever USB is absent. Rough standby draw with the ESP32 in deep sleep:
  - ADS1298 in standby: a few hundred µA (estimate). PWDN is pulled high, so firmware can't fully power it down.
  - LP5907 and AP2112 quiescent current: about 70 µA.
  - Total: a few hundred µA, so a 150 mAh cell goes flat in weeks on the shelf.
- **S2 (recommended): no battery-level reading.** Firmware can't report charge or shut down cleanly before the cell's protection trips.
- **S3 (optional): no charge or power indicator.** The MCP73831 STAT pin is unused.
- **S4 (note):** J3 has no reverse-polarity protection. "+" and "−" are marked on the silkscreen; solder carefully.

## 3. Layout

Checks done:
- **DRC:** 0 errors, 0 unconnected. Schematic-to-board parity: 0 issues. Only warnings: silkscreen at the board edge on J1, J7 and the module outline.
- **Antenna:** the ESP32 antenna sits at the board end, with copper kept out of the footprint keep-out on both layers. USB-C is outside that area.
- **ADS1298 placement:** VREF/VCAP caps sit along the top edge of the chip and the RLD network along the bottom. The input RC filters are next to J6, and inputs run as P/N pairs.
- **Ground:** AGND pours on both layers, with stitching vias outside the module's pad field.
- **J6 (Hirose FH34SRJ):** the footprint matches the Hirose land pattern. The FPC inserts on the side opposite the leads (datasheet p.8), so the opening faces the board edge. Contact 1 is at the jack end.
- **J1 (CUI SJ-3523-SMT):** the KiCad footprint matches CUI's recommended layout rotated 180°. Sleeve is 2.4 mm and ring 4.4 mm from the front face, on opposite sides; tip is 11.8 mm from the front face, on the sleeve side. The pegs are 7.0 mm apart.
- **Flex zones:** 21–30 mm (power column) and 44–57 mm on the bottom half (input RC block). Both carry parts, so keep bends gentle.

Findings:
- **L1 (note):** the ESP32 3V3 pin is about 14 mm of 0.25 mm trace from the AP2112 output caps. Expected drop at a 350 mA TX burst is about 30 mV. The module has its own decoupling. Acceptable for Rev A.
- **L2 (note):** USB D± are not impedance-matched. That's fine for 12 Mbps full-speed.

## 4. BOM and placement

- **Cost:** about $28 per board in parts (ADS1298 $19.88, ESP32-S3 module $4.71), plus 11 extended part types for JLC's extended-part fees.
- **Stock (11 Oct):**
  - ADS1298: 1,953.
  - J1: 693, the lowest line but plenty for a few boards.
  - Everything else: > 13,000.
- **CPL:** rotations and offsets corrected and checked in JLC's preview. J1 is −90° → 180° and shifted 1.1 mm; J6 is centred on its body. The rest of the table is in `kicad/fab/JLC_ORDER.md`.
- **Order settings agreed:**
  - Board: flex 2-layer, 0.11 mm, ENIG.
  - Stiffener: FR4 (0.4 mm suggested for USB-C robustness). Confirm Production file: Yes.
  - Panel: 3-up, 79 mm side.
  - Assembly: 2 panels assembled, Confirm Parts Placement: Yes.

## Added after the adversarial pre-order check

- **Done: input caps C201–C206 changed from 1 nF to 100 pF C0G (C14858, basic part).**
  With dry electrodes (MΩ at 50/60 Hz), 1 nF to ground forms a large,
  mismatched divider with the electrode impedance. That converts mains
  common-mode into differential hum. 100 pF is 26 MΩ at 60 Hz, so the
  mismatch effect shrinks about 10×. The RC corner moves to about 72 kHz,
  still far below the 512 kHz modulator.
- **Board material: Liam chose to keep the flex configuration.** The stiffener now also covers the slide switch, and it has holes at every peg and USB-C shell tab.
- **Board material (background).** Parts in the two unstiffened zones (the power
  column with SOT-23s, and the filter block) can crack if the board actually
  bends. Options:
  - Rigid 0.8 mm FR4 with the same gerbers (the stiffener layer is ignored).
    The electrodes and their flex already conform to the head, and a 2.5"
    board sits fine on padding.
  - Keep flex, with one stiffener over the whole board.
  - Keep flex as drawn and never bend it in those zones.

## Recommended changes before ordering

1. **On/off: MSK-12C02 slide switch (C431540, 187k in stock).** Side-actuated, 8 × 2.8 mm, on the bottom edge beside the power column.
   - It sits between the battery and Q101.
   - **Off:** the battery is disconnected from the system and draws 0 µA. USB still powers the board and still charges the cell.
   - **On:** behaves exactly as today.
   - Alternative: a pushbutton with firmware soft-off. It costs no edge space, but the board never truly turns off; it still draws a few hundred µA unless the AFE supply is also switched.
2. **Battery monitor:** a 1 MΩ / 1 MΩ divider from VBAT to ESP32 IO1, with 100 nF. Draws 2 µA.
3. **Charge LED (optional):** MCP73831 STAT through 1 kΩ to a small LED. It's lit only while charging.

Items 1 and 2 add five parts and a local re-route of the power column, then a fresh ERC, DRC, re-export and CPL check.
