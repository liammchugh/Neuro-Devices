# EMG wearable, Rev A (KiCad, JLCPCB)

One to three channel surface EMG front end on a battery-powered headband
wearable, built around a TI ADS1298 and a XIAO ESP32-S3 that sends data to the
pedal wirelessly. The original discrete single-channel design (INA333 + OPA2333)
is in git history (commit 3aedaac) and in `../../docs/`.

Rev A is a bench board. Synthetic differential inputs first; no body electrodes
until the isolation checks in "Bring-up" pass.

## Requirements (reviewed, Liam, 11 Oct 2026)

1. Works with 1, 2 or 3 simultaneous electrode pairs, chosen by firmware mode,
   with no rework.
2. Electrodes: one 3.5 mm TRS jack for CH1 (tip +, ring −, sleeve REF) plus a
   1 mm FPC carrying CH1 to CH3 for flex-PCB arrays or a breakout (Liam, 11 Oct
   2026: three 3.5 mm jacks do not fit the 2.5" × 1" board). All REF sleeves share
   one reference/RLD net, so 9 electrodes (3 REF) or 7 (1 REF) both work.
   Series resistors on every input.
3. Power: passive USB/battery handling in every state (battery, USB, both), no
   switches. Dedicated low-noise analog rail. Protected LiPo.
4. Debug: USB serial over the XIAO USB-C. The isolated UART footprint was
   dropped for size.
9. Board: 2-layer flex PCB, 63.5 × 25.4 mm (2.5" × 1") max, XIAO soldered by
   its castellations at one end with USB-C pointing down (across the long
   axis), jack and FPC at the other end.
5. Filtering in firmware: capture wide (about 0.5 Hz up, 4 kSPS or more) so
   blink/EOG and envelope data are kept; 20 to 450 Hz is the EMG band.
6. Lead-off detection (built into the ADS1298).
7. JLCPCB assembly, LCSC parts, smallest practical size for a headband.
8. Pedal side is out of scope; it gets data wirelessly.

## Decisions

| Topic | Decision | Source |
|---|---|---|
| Architecture | Battery wearable, wireless to pedal (BLE / ESP-NOW). USB-C for flashing, charging and serial debug | Liam, 11 Oct 2026 |
| Front end | ADS1298 (8 ch, 24-bit, PGA, RLD, lead-off), CH1 to CH3 used, CH4 to CH8 tied to AVDD and powered down | Liam, 11 Oct 2026 |
| Sample rate | 4 kSPS (or 8 kSPS) from the ADS1298, decimate in firmware | Reviews |
| Filtering | Firmware: HPF about 0.5 Hz for wideband capture, 20 to 450 Hz for EMG features | Liam, 11 Oct 2026 |
| Input network | 22 kΩ series + 1 nF C0G to AGND per input (≈ 7 kHz). The ADS1298 modulator runs at 512 kHz, so no higher-order anti-alias filter is needed | Datasheet |
| Reference / RLD | RLDOUT with 1 MΩ ∥ 1.5 nF feedback (datasheet), 330 kΩ series to the REF electrode(s), DC fault current < 10 µA | Datasheet, critic review |
| Schematic | Flat, one A3 sheet | Review 2 |

## Isolation and USB debug

The wearable is isolated from the pedal and mains by being battery powered and
wireless. The XIAO's own USB-C is the one non-isolated path: when it is plugged
into a computer, the body would be connected through the reference electrode,
AGND and the USB shield to mains earth, and the guitar strings are on mains
earth too.

Rev A relies on one rule: **USB serial over the XIAO's USB-C is the debug
path** (Liam, 11 Oct 2026), as on any Arduino-style R&D board. With electrodes
on the body and USB plugged in, run the laptop on battery and unplugged from
mains, or use a synthetic input instead of electrodes. This note is on the
schematic. A USB isolator dongle between the laptop and the board is the easy
upgrade when the laptop has to stay on mains.

The isolated UART footprint (ISO7721) from earlier drafts was dropped to fit
the 2.5" × 1" flex board.

Charging while worn: only from a battery-powered laptop or an isolated (Class II) USB charger.

## Circuit

**Power and reference**
- LiPo (protected cell) soldered to J3 (two SMD pads), which also feed the
  XIAO BAT pads under the module (pad position to verify against Seeed). The XIAO charges it
  from USB-C.
- Passive power path, no switches: USB 5 V through a Schottky (D101, B5819W)
  and the battery through a P-MOSFET (Q101, AO3401A, gate on VBUS with a 100 kΩ
  pull-down) join at `VSYS`. USB present: Q101 is off and VSYS ≈ 4.7 V from
  USB. USB absent: Q101 is on and VSYS = VBAT. Both: USB carries the load while
  the XIAO charges the battery.
- `+3V0_A` (ADS1298 AVDD) from a dedicated low-noise LDO (U6, LP5907MFX-3.0, 6.5 µVrms,
  82 dB PSRR at 1 kHz) fed from VSYS, replacing the ferrite off the XIAO 3V3.
  EN is tied to the XIAO 3V3, so the AFE is never live while the ESP32 is
  unpowered. ADS1298 DVDD runs from the XIAO 3V3 (AVDD − DVDD = −0.3 V, inside
  the −2.1 to 3.6 V limit).
- Check before layout that the XIAO 5V pin reads ~0 V with USB unplugged
  (no back-feed from BAT), or Q101 will not turn on.

**Electrodes**
- J1: CUI SJ-3523-SMT 3.5 mm TRS jack for CH1 (tip ELEC1_P, ring ELEC1_N,
  sleeve `RLD_ELEC`).
- J6: Hirose FH34SRJ-12S-0.5SH(50) back-flip FPC (C424659; 12 pins, 0.5 mm,
  1.0 mm tall), in parallel with J1 for CH1: use one or the other. CH2 and CH3 are on J6 only. Pinout (ordered to match the board routing; it can change when the flex
  array is designed): 1 AGND, 2/3 CH3 N/P, 4 REF, 5 AGND, 6/7 CH2 N/P, 8 REF,
  9 AGND, 10/11 CH1 N/P, 12 REF, MP AGND. Footprint `emg_wearable:Hirose_FH34SRJ-12S-0.5SH_...` is drawn from
  the Hirose land pattern; check it against the datasheet before ordering. The
  FPC enters from the signal-pad side; contact 1 is at +X.

**ADS1298 (U1)**
- IN1 to IN3 from the input RC. IN4 to IN8 and TESTP_PACE_OUT1/2 to AVDD, as
  the datasheet asks for unused analog pins.
- Internal 2.4 V reference: VREFP 10 µF + 100 nF to AGND, VREFN to AGND.
- VCAP1 22 µF, VCAP2/3/4 1 µF to AGND. AVDD 10 µF + 2× 100 nF, DVDD 1 µF +
  100 nF.
- Internal clock (CLKSEL high, CLK not connected). RESV1 and DAISY_IN to DGND.
  RLDREF and WCT not connected (internal mid-supply reference). GPIO1 to 4 not
  connected: set them as outputs in firmware.
- RLDIN tied to `RLD_ELEC` so firmware can measure the REF electrode.
- SPI to the XIAO: D5 SCLK (GPIO6, moved for routing), D9 DOUT, D10 DIN, D3 CS (10 k pull-up), D4 DRDY,
  D1 START, D0 RESET (10 k pull-up). PWDN held high by 10 k; use register
  standby instead. D2/GPIO3 is left free because it is a strapping pin.
- Firmware: power down unused channels (CHnSET.PDn), pick RLD sense channels
  (RLD_SENSP/N) and use lead-off (LOFF) to detect which electrodes are attached.

## BOM notes for JLCPCB

| Part | LCSC | Note |
|---|---|---|
| ADS1298IPAGR | C527440 | extended, ≈ $20, 1,953 in stock on 11 Oct 2026 |
| LP5907MFX-3.0/NOPB | C475492 | extended |
| AO3401A, B5819W | C15127, C8598 | basic |
| SJ-3523-SMT-TR | C4991872 | extended, 737 in stock; PJ-320D (C431535) is a fallback with a different footprint |
| FH34SRJ-12S-0.5SH(50) | C424659 | extended, 1 mm tall, custom footprint |

Every JLC-placed symbol in `kicad/emg_wearable_revA.kicad_sch` carries an
`LCSC` field; the grouped BOM is in `kicad/bom/`. The XIAO is not
JLC-assemblable: footprint for headers or castellations, hand-soldered.

## Board

2-layer flex (polyimide), 63.5 × 25.4 mm, all parts on top. Layout notes:

- XIAO at the left, soldered by its castellations, USB-C on the bottom edge
  (points down the spine). Top-layer copper is kept out from under the module.
- ADS1298 in the middle with its decoupling caps above and below; input RC
  filters on the electrode side; J1 jack and J6 FPC on the right edge.
- AGND pours on both layers with stitching vias. Routed with Freerouting, then
  checked in KiCad: DRC is clean apart from the J1 silkscreen running over the
  board edge where the jack overhangs.
- Stiffeners (0.2 mm FR4, back side) are drawn on the `Stiffener` (User.1)
  layer: under the XIAO, under the ADS1298 block and under J1/J6. The strips
  between them (power column, input RC column) are the bend zones; keep bends
  there gentle since they carry 0603 parts.

Fab outputs are in `kicad/fab/`: gerbers and drill files, `*_bom_jlc.csv` and
`*_cpl_jlc.csv` for JLCPCB assembly. The XIAO, LiPo pads and test points are
excluded from assembly. Check part rotations in JLC's placement preview
(SOT-23, SOT-23-5 and TQFP often need an offset).

## Bring-up

1. No electrodes. Check VSYS on battery, USB and both; `+3V0_A`; idle current.
2. Read the ADS1298 ID register, run its internal test signal and input-short
   noise test on each channel.
3. Synthetic 1 mVpp differential input, sweep 1 Hz to 2 kHz, one to three
   channels at a time.
4. 50/60 Hz common-mode test with mismatched source impedances, RLD on and off.
5. Confirm no continuity between electrode nets and the debug header's computer
   side.
6. Only then electrodes, on battery or a battery-powered laptop.
