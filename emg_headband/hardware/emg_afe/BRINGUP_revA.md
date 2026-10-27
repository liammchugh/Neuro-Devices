# Rev A bring-up plan

Work through the stages in order and stop at the first failure. Each stage only
assumes the ones before it passed. Firmware and flash steps:
[`../../firmware/revA_bringup/README.md`](../../firmware/revA_bringup/README.md).

You need: a multimeter, a USB-C cable, ideally an inline USB-C power meter
(shows V and mA), a protected 1S LiPo, a 3.5 mm TRS plug or 3-lead snap
electrode cable, gel snap electrodes. A scope helps but isn't required.

**Safety rule for every stage with skin contact:** the board runs on its
battery, or the laptop runs on its battery and is unplugged from mains. No
guitar, amp or pedal connected. See "Isolation and USB debug" in the
[README](README.md).

## Known risks to check first

These come from the design reviews ([REVIEW_revA.md](REVIEW_revA.md),
[kicad/fab/JLC_ORDER.md](kicad/fab/JLC_ORDER.md), PR #4):

1. **Placement rotations.** JLC's CPL needed manual offsets for U1, U2, J1, J6
   and the SOT-23s. A part rotated 90° or 180° is the most likely Rev A fault.
2. **J3 has no reverse-polarity protection.** A reversed LiPo kills U8 and
   Q101 and can damage more. Check polarity with the meter before soldering.
3. **Flex bend zones carry parts.** The power column (21–30 mm from the
   ESP32 end) and the input RC block (44–57 mm, bottom half) are unstiffened.
   Don't bend there; look for cracked 0603s and SOT-23 joints.
4. **Custom footprints:** J6 (FH34SRJ), SW1 (MSK12C02), the ESP32-S3 module
   and J3. Inspect their joints closely.
5. **Electrode flex FPC orientation** (PR #4): contacts may be mirrored.
   Stage 7 has a continuity test before any signal test.
6. **J1 and J6 share CH1.** Use the TRS jack or the flex for CH1, never both.

## Stage 0: visual, unpowered

Under a loupe or microscope, with the board flat:

- [ ] U1 (ADS1298, TQFP-64): pin-1 dot on the silkscreen marker; no bridges
      along the 0.5 mm pins (check all four sides).
- [ ] U2 (ESP32-S3 module): antenna end at the board edge over the copper-free
      area; the module sits flat (no tilted castellations).
- [ ] U6 LP5907, U7 USBLC6, U8 MCP73831, U9 AP2112, Q101 AO3401A: pin 1
      matches the silkscreen.
- [ ] D101 cathode band toward VSYS (matches the silkscreen). D102 (red
      charge LED) polarity matches the silkscreen.
- [ ] J7 USB-C shell tabs soldered through; J1 opening and J6 opening face the
      right board edge.
- [ ] J6: no bridges across the 12 pins at 0.5 mm.
- [ ] Stiffeners present under the module/USB-C, ADS1298 and J1/J6; no
      cracked parts in the two bend zones.

Resistance checks (meter on ohms, black lead on TP3 or TP8 = AGND):

| Point | Net | Expect | Fault if |
|---|---|---|---|
| TP4 | VSYS | > 10 kΩ (charges up slowly) | < 100 Ω |
| TP2 | +3V3 | > 1 kΩ | < 100 Ω |
| TP1 | +3V0_A | > 1 kΩ | < 100 Ω |
| USB-C VBUS (C703 +) | VBUS | ≈ 100 kΩ (R104) | < 1 kΩ |
| J3 + pad | VBAT | > 10 kΩ | < 100 Ω |
| TP5 | RLD_OUT | > 100 kΩ | < 1 kΩ |

And between nets (unpowered):

- [ ] TP2 to TP1 (+3V3 to +3V0_A): not a short.
- [ ] J1 tip to R201 far pad (CH1_P): 22 kΩ. Ring to R202: 22 kΩ.
- [ ] J1 sleeve to TP5 (RLD_OUT): 330 kΩ (R102).

## Stage 1: first power from USB, no battery

Plug in USB-C through the power meter (a phone charger or powered hub is fine;
no electrodes). Unplug at once if current goes above 200 mA or anything gets
warm.

- [ ] Current: about 30–80 mA. A blank ESP32 may reboot in a loop, so current
      can wobble.
- [ ] TP4 VSYS: 4.6–4.8 V (USB minus the B5819W drop).
- [ ] TP2 +3V3: 3.25–3.35 V.
- [ ] TP1 +3V0_A: 2.97–3.03 V. With a scope, ripple under 5 mVpp.
- [ ] D102 charge LED: off, or flickering. With no cell, the MCP73831 STAT pin
      toggles. This is normal.
- [ ] Touch-test U1, U6, U9, U8 and the module: none of them get warm.

## Stage 2: USB enumeration and flashing

- [ ] On the Mac, `ls /dev/cu.usbmodem*` shows a new port. System Information
      → USB lists "USB JTAG/serial debug unit" (VID 0x303A, PID 0x1001).
- [ ] Flash the bring-up firmware (see the firmware README). Open the monitor
      and you should see the banner `revA-bringup 0.1. ADS1298 ID 0x92`.

If it doesn't enumerate: try another cable (some USB-C cables are charge-only).
Then force the ROM bootloader: hold TP10 (BOOT, IO0) to GND, tap TP9 (EN) to
GND, release TP10. Still nothing? Check J7 and U7 joints, R701/R702 (5.1 kΩ CC),
and that D+/D− aren't bridged.

## Stage 3: ADS1298 self-test (no electrodes)

Type `selftest` in the monitor. The firmware runs these and prints PASS/FAIL:

| Check | Pass | If it fails |
|---|---|---|
| ID register | 0x92 | 0x00 or 0xFF: SPI or U1 power. Check U1 orientation/joints, +3V0_A, +3V3, CS/SCLK/DOUT/DIN joints. |
| Register write/readback | 0x85 | DIN (IO14) or timing |
| DRDY rate | 4000 Hz ± 2 % | DRDY (IO16) or START (IO17) joint; CLKSEL (U1.52) must be high |
| AVDD via ADS1298 | 2.90–3.10 V | LP5907 (U6), C101/C118 |
| DVDD via ADS1298 | 3.20–3.40 V | AP2112 (U9) |
| Die temperature | room temp + a few °C | very high: something on U1 is shorted |
| Internal test signal, CH1–3 | about 2.0 mVpp each, all equal | One channel off: that channel's PGA/joints. All exactly half: tell me, it's my amplitude assumption, not the board. |
| Input-short noise, CH1–3 | 20–450 Hz under 2 µVrms; broadband under 5 µVrms | Reference caps (C112/C113 VREFP, C114 VCAP1, C115–C117), AVDD noise |

The noise limits are my guide numbers, not datasheet guarantees. A healthy
ADS1298 at gain 6 should be comfortably below them. Write the actual values
in the results table below.

Also run `info` and save the output: it dumps all registers and the
counters (`queue_drops` and `bad_status` should be 0).

## Stage 4: battery, switch, charging LED, battery divider

With the meter, confirm which J3 pad is + (the left one, connected to C704
and U8 pin 3) before soldering. Slide SW1 to OFF. Solder a **protected** LiPo
to J3.

| Condition | Expect |
|---|---|
| SW1 OFF, no USB | Board dead. No current from the cell. |
| SW1 ON, no USB | Board boots. TP4 VSYS ≈ cell voltage. |
| SW1 ON, no USB, `bat` | Within ~3 % of the cell voltage on the meter |
| SW1 OFF, USB in | Board runs from USB. D102 lit while the cell charges (off when full). `bat` reads ≈ 0 V (the divider is after SW1). |
| SW1 ON, USB in | VSYS ≈ 4.7 V. D102 lit while charging. J3 + stays at the cell voltage (no USB backfeed through Q101). |
| SW1 ON: run `info`, unplug USB for 5 s, re-plug, reopen the monitor, `info` again | No reset during the switchover: the uptime in `info` kept counting (a reset sets it back to 0). |
| Charge current (power meter, SW1 OFF) | Board current + about 100 mA while charging (R703 = 10 kΩ) |

Low-battery note: below about 3.5 V on the cell, +3V3 starts to sag (AP2112
dropout), and below about 3.1 V +3V0_A drops under 3.0 V. Run `supply` on a
low cell to see where it starts to fail.

## Stage 5: noise floor with inputs shorted externally

This adds the input RC, the jack and RLD to the stage 3 test.

1. Short a 3.5 mm TRS plug's tip, ring and sleeve together (or wire one up)
   and insert it in J1.
2. Laptop on battery and unplugged from mains if possible.
3. `noise ext`. CH1 is the one that counts here (CH2/CH3 float unless you short
   their flex pins). Expect CH1 20–450 Hz under 4 µVrms.
4. Repeat with `rld off` and then `rld on`, and with the laptop plugged into
   mains, to see how much mains pickup the RLD removes.
5. Record a capture for the PSD:
   `python tools/revA_host.py record --seconds 10 --out short_ch1.csv --plot`.
   The 50/60 Hz line should be small; note its height.

Optional synthetic signal, if you have no signal generator: a battery-powered
phone playing a 100 Hz tone, at low volume, through a 1000:1 divider (100 kΩ
from the phone's left channel to the J1 tip, 100 Ω from tip to ring, ring and
sleeve to the phone's ground). That gives about 100 µVpp. In `plot emg` the
CH1 trace should show a clean 100 Hz sine at the expected amplitude.

## Stage 6: electrodes through the TRS jack (CH1)

Board on its battery, or laptop on battery and off mains. No guitar rig.

1. Gel snap electrodes on the forearm first (biggest, easiest signal): + and
   − 2–3 cm apart along the flexor muscles, REF on the bony elbow. Lead cable:
   tip = +, ring = −, sleeve = REF.
2. `ch 1`, `leadoff on`, `plot env`. In the Arduino Serial Plotter (or any
   plotter), `loffP`/`loffN` should read 0 with the electrodes on. Pull one
   electrode off and its bit should set.
3. `leadoff off`, `plot emg`. Relaxed: a few µVrms of baseline. Make a fist:
   bursts of about 50–500 µV.
4. `plot env`: a clean envelope that rises with grip force.
5. Move to the forehead (CH1 at right frontalis, REF high midline): raise
   your eyebrows → EMG bursts. `plot wide` should show blinks as slow
   deflections (EOG), which proves the 0.5 Hz low end works.
6. Record 30 s with rest/contract/rest for later
   (`revA_host.py record --seconds 30 --out forearm.csv`).

## Stage 7: electrode flex through the FPC (CH1–CH3)

If the PR #4 flex has been fabricated.

1. **Unplug the TRS cable** (J1 and J6 share CH1).
2. **Continuity first, unpowered.** Insert the flex in J6 and close the
   actuator. With the meter on ohms:
   - CH1+ electrode pad → J1 tip contact: ≈ 0 Ω. CH1− pad → J1 ring: ≈ 0 Ω.
     REF pad → J1 sleeve: ≈ 0 Ω.
   - CH2+ / CH2− pads → R203 / R204 pad on the J6 side: ≈ 0 Ω.
   - CH3+ / CH3− pads → R205 / R206 pad on the J6 side: ≈ 0 Ω.
   - If CH1+ reads on a REF pad or CH3 pads read on CH1, the FPC contacts are
     mirrored (the open question from PR #4). Stop and tell me; the fix is in the flex
     pin order, not the main board.
3. Power up on battery, `ch 3`, `leadoff on`, `plot env`. All six P/N bits
   read 0 once the band is on and the skin is prepped.
4. `leadoff off`, `plot env`, then try each in turn:
   - raise eyebrows → CH1 (frontalis)
   - frown → CH2 (corrugator)
   - clench the jaw → CH3 (temporalis)

   Note the crosstalk: how much each action shows on the other two channels.
5. Record a 60 s session with each gesture for the feature work.

## Results (fill in)

| Board # | S0 visual | S1 rails (VSYS / 3V3 / 3V0_A, mA) | S2 USB | S3 ID / noise CH1–3 (µVrms 20–450) | S4 battery | S5 ext noise | S6 TRS | S7 flex |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
