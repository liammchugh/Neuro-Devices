# Pedal side: EMG link and grounding notes

Status: parked suggestions from the October 2026 EMG AFE design review. Current
work is on the EMG wearable (`emg_headband/hardware/emg_afe/`); revisit this
when the pedal hardware starts.

## Why the EMG front end is not on the pedal

A guitarist's hands touch the strings, and the strings are bonded to the amp's
audio ground, which is usually mains earth. The player's body is therefore
already tied to audio ground.

The EMG front end biases the body to VMID (1.65 V) through the reference
electrode. If the EMG board shared a ground with the pedal's audio path:

- the strings would hold the body at 0 V while the reference electrode pulls it
  to 1.65 V, driving a DC current through the player (about 1.65 µA through the
  original 1 MΩ, milliamps with the lower reference resistor the review
  recommends);
- the INA333 inputs would sit at 0 V, outside its input common-mode range
  (V− + 0.1 V), so the front end would not work either.

Decision (11 Oct 2026): the EMG board is a battery-powered wearable that sends
data to the pedal wirelessly. The only circuit tied to the body is the battery
island on the wearable.

## What this means for the pedal

1. **No galvanic connection to the wearable.** The pedal receives EMG data over
   BLE or ESP-NOW. Do not add a wired EMG input, a shared ground lead, or a
   charging cable from the pedal to the wearable while it is worn.
2. **Radio receiver.** The pedal needs a matching receiver: a second
   XIAO ESP32-S3 (ESP-NOW gives lower, more predictable latency than BLE) or the
   ground unit's own radio. Budget link latency end to end, since the README's
   timing targets assume it.
3. **Keep the audio ground conventional.** The pedal's audio ground stays tied
   to the amp as in any pedal. Nothing on the pedal needs to be isolated for
   EMG as long as point 1 holds.
4. **If an on-pedal front end is ever revisited**, it needs a fully isolated
   domain: an isolated DC-DC converter for the AFE supply, a digital isolator
   for the ADC data, and creepage/clearance sized for the isolation rating. The
   AFE ground then floats with the body rather than the strings. This is more
   parts, cost and safety review than the wearable, which is why it was not
   chosen.
5. **Wearable charging and debug** stay on the wearable side. Its USB port is
   for flashing and charging with electrodes unplugged, plus an isolated debug
   header; see the wearable spec.

## Source

Design report `EMG_AFE_3V3_design_report.md` (Concept A, 10 Oct 2026) and the
merged review, both under `emg_headband/docs/`.
