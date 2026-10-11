# EMG wearable, Rev A (KiCad, JLCPCB)

Single-channel 3.3 V surface EMG front end on a battery-powered wearable, with a
XIAO ESP32-S3 that sends data to the pedal wirelessly. This spec merges the
Concept A design report and both reviews in `../../docs/`. Values here supersede
the report where they differ.

Rev A is a bench board. Synthetic differential inputs first; no body electrodes
until the isolation checks in "Bring-up" pass.

## Decisions

| Topic | Decision | Source |
|---|---|---|
| Architecture | Battery wearable, wireless to pedal (BLE / ESP-NOW). Optional USB for flashing, charging and debug | Liam, 11 Oct 2026 |
| Sample rate | 4 kSPS on ADC1, decimate in firmware | Reviews |
| Anti-alias | 4th-order Butterworth Sallen-Key, about 480 Hz, on a second OPA2333 (U4) | Reviews (4th chosen over 2nd: parts are cheap) |
| First-stage gain | G1 ≈ 6 (RG = 20 kΩ), tolerates about ±250 mV electrode offset | Review 2 |
| Second-stage gain | R403 = 100 kΩ (G2 = 11, total ≈ 66) or 390 kΩ (G2 = 40, total ≈ 240), solder-jumper selectable | Review 2 |
| Reference electrode | R205 = 100 kΩ to VMID (footprint allows 47 to 220 kΩ) | Reviews, safe once on battery |
| Schematic | Flat or 2 to 3 sheets, not 5 | Review 2 |

## Isolation and USB debug

The wearable is isolated from the pedal and mains by being battery powered and
wireless. The XIAO's own USB-C is the one non-isolated path: when it is plugged
into a computer, the body would be connected through the reference electrode,
AGND and the USB shield to mains earth, and the guitar strings are on mains
earth too.

Rev A handles this in two layers:

1. **USB serial over the XIAO's USB-C is the debug default** (Liam, 11 Oct 2026),
   as on any Arduino-style R&D board. With electrodes on the body and USB
   plugged in, run the laptop on battery and unplugged from mains, or use a
   synthetic input instead of electrodes. This note is on the schematic.
2. **Optional isolated UART footprint (DNP)** for live data when the laptop
   has to stay on mains: a digital isolator (ISO7721DWVR, C2864013) between the
   ESP32 UART and a 4-pin header (VCC_ISO, GND_ISO, TX, RX). The computer side
   is powered by a USB-UART adapter plugged into the header, so no isolated
   DC-DC is needed on the board.

Alternatives considered:

- **Rule only** (no isolator): cheapest, but nothing enforces it.
- **Full isolated USB** (USB isolator plus isolated DC-DC): heavier, and the
  XIAO's USB data lines are not on its castellations, so it would need a
  different MCU layout.

Charging while worn: only from a battery-powered laptop or an isolated (Class II) USB charger.

## Signal chain and values

Net names follow the design report: `+3V3_A`, `AGND`, `VMID_RAW`, `VMID`,
`ELEC_P`, `ELEC_N`, `ELEC_REF`, `IN_P`, `IN_N`, `INA_OUT`, `HP_NODE`,
`GAIN_FB`, `GAIN_OUT`, `AAF_MID`, `AAF_OUT`, `ADC_OUT`, `VMID_MON`.

**Power and reference**
- LiPo (protected cell) on J3, wired to the XIAO BAT pads. The XIAO charges it
  from USB-C.
- Passive power path, no switches: USB 5 V through a Schottky (D101, B5819W)
  and the battery through a P-MOSFET (Q101, AO3401A, gate on VBUS with a 100 kΩ
  pull-down) join at `VSYS`. USB present: Q101 is off and VSYS ≈ 4.7 V from
  USB. USB absent: Q101 is on and VSYS = VBAT. Both: USB carries the load while
  the XIAO charges the battery.
- `+3V0_A` from a dedicated low-noise LDO (U6, LP5907MFX-3.0, 6.5 µVrms,
  82 dB PSRR at 1 kHz) fed from VSYS, replacing the ferrite off the XIAO 3V3.
  EN is tied to the XIAO 3V3, so the AFE is never live while the ESP32 is
  unpowered. 1 µF and 100 nF at the output.
- VMID (now 1.5 V): R101/R102 100 kΩ divider, C103 1 µF, buffered by U3A
  (OPA2333). 47 Ω series resistor out of U3A before C104 1 µF. Feed INA333 REF
  from the buffer side of that resistor.
- Check before layout that the XIAO 5V pin reads ~0 V with USB unplugged
  (no back-feed from BAT), or Q101 will not turn on.

**Electrode input**
- J_ELEC: 3.5 mm TRS jack (tip ELEC_P, ring ELEC_N, sleeve ELEC_REF).
- R201/R202 100 kΩ series, R203/R204 10 MΩ to VMID, R205 100 kΩ ELEC_REF to VMID.
- C201/C202 22 pF C0G to AGND, C203 220 pF C0G across IN_P/IN_N.
- DNP footprints for low-leakage input clamps and lead-off comparators.

**Instrumentation amplifier**
- U1 INA333AIDGKR, RG = R301 20 kΩ, G1 = 6. C301 100 nF and C302 1 µF at the pins.

**High-pass and gain**
- C401 10 nF C0G, R401 820 kΩ to VMID: 19.4 Hz.
- U3B non-inverting, R402 10 kΩ, R403 100 kΩ or 390 kΩ (solder jumper).

**Anti-alias (U4 = second OPA2333, unity-gain Sallen-Key, both to VMID)**

| Stage | Q target | R1 = R2 | C1 (feedback) | C2 (to VMID) | fc |
|---|---|---|---|---|---|
| U4A | 0.541 | 165 kΩ | 2.2 nF C0G | 1.8 nF C0G | ≈ 485 Hz, Q ≈ 0.55 |
| U4B | 1.307 | 127 kΩ | 6.8 nF C0G | 1 nF C0G | ≈ 480 Hz, Q ≈ 1.30 |

Impedance is scaled ×10 from the first draft (16.5 k / 12.7 k with 22 to
68 nF) because 15 to 68 nF C0G parts are barely stocked at JLC in 0603. fc and
Q are unchanged; the extra resistor noise is negligible after a gain of 66.

About 69 dB at 3.55 kHz, the frequency that folds onto 450 Hz at 4 kSPS.
Simulate before layout and check LCSC stock for the C0G values.

**ADC**
- R501 1 kΩ, C501 15 nF to AGND (≈ 10.6 kHz) into XIAO D0 / GPIO1.
- VMID_MON through 1 kΩ to D1 / GPIO2, subtracted in firmware.

## BOM notes for JLCPCB

| Part | LCSC | Note |
|---|---|---|
| INA333AIDGKR | C19450 | extended |
| OPA2333AIDR ×2 | C38732 | extended, one fee for both |
| ISO7721DWVR | C2864013 | extended, DNP in Rev A |

Every symbol in `kicad/emg_wearable_revA.kicad_sch` carries an `LCSC` field;
the grouped BOM is in `kicad/bom/`.

Add an `LCSC` field to every symbol for kicad-jlcpcb-tools. The XIAO is not
JLC-assemblable: footprint for headers or castellations, hand-soldered.

## Board

2-layer rigid, 0603 passives, continuous AGND plane. Keep the electrode jack and
input network away from the XIAO antenna and USB. Guard IN_P/IN_N, match their
layout. Test points on every stage. Isolation gap under the ISO7721 with no
copper crossing it.

## Bring-up

1. No electrodes. Check `+3V3_A`, VMID, idle current.
2. Synthetic 1 mVpp differential at VMID common mode, sweep 10 Hz to 4 kHz.
3. 50/60 Hz common-mode test with mismatched source impedances.
4. Confirm no continuity between electrode nets and the debug header's computer side.
5. Only then electrodes, on battery, with USB unplugged.
