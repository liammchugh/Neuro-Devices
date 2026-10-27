# Rev A bring-up firmware

Bench firmware for the Rev A EMG wearable (ESP32-S3-MINI-1-N8 + ADS1298). It
talks over USB serial on the board's USB-C and has no wireless yet. Use it with
the staged plan in
[`../../hardware/emg_afe/BRINGUP_revA.md`](../../hardware/emg_afe/BRINGUP_revA.md).

What it does:
- Brings up the ADS1298: internal clock and 2.4 V reference, high-resolution
  mode, 4 kSPS default, gain 6 (±400 mV input range), CH4–CH8 powered down.
- `selftest`: ID, SPI readback, DRDY rate, AVDD/DVDD/die temperature measured
  by the ADS1298 itself, internal test signal and input-short noise, with
  PASS/FAIL.
- 1, 2 or 3 channels (`ch 1|2|3`), RLD from the active channels, DC lead-off.
- Filtering in firmware, capturing wide from 0.5 Hz:
  - `plot wide`: 0.5 Hz HPF, mains notch, 100 Hz LPF. Keeps blinks and EOG.
  - `plot emg`: 20–450 Hz band plus mains harmonic notches.
  - `plot env`: rectified EMG through a 5 Hz LPF, the activation envelope.
  The plot modes print at 250 Hz in Arduino Serial Plotter format.
- `bin`: raw 24-bit samples at the full rate, recorded with
  `tools/revA_host.py` to CSV, with an optional PSD plot.

Pin map (from the board file, U2 module pin → net): SCLK IO12, DOUT/MISO
IO13, DIN/MOSI IO14, CS IO15, DRDY IO16, START IO17, RESET IO18, battery
divider IO10. ADS1298 PWDN is pulled high in hardware. See `src/board_pins.h`.

## Flashing

USB-C straight to the Mac. There's no USB-UART chip: the ESP32-S3's built-in
USB-Serial-JTAG does both flashing and serial.

### Option A: PlatformIO (build from source)

```sh
brew install platformio            # or: pipx install platformio
cd ~/Code/Neuro-Devices
git fetch origin && git checkout firmware/emg-rev-a-bringup
cd emg_headband/firmware/revA_bringup
pio run -t upload                  # first build downloads the ESP32 toolchain (a few minutes)
pio device monitor                 # Ctrl-C to quit
```

PlatformIO finds the `/dev/cu.usbmodem*` port by itself. If several boards
are plugged in, add `--upload-port /dev/cu.usbmodemXXXX`.

### Option B: prebuilt binary (no toolchain)

`revA_bringup_merged.bin` (in the project files, under `bringup/`) is the
whole flash image (bootloader, partitions, app) to write at offset 0x0.

- Browser: open https://espressif.github.io/esptool-js/ in Chrome. Click
  Connect, pick the "USB JTAG/serial debug unit" port, set Flash Address to
  `0x0`, choose the .bin file and click Program. Then use the page's Console
  tab or any serial terminal.
- Command line: `pip install esptool`, then
  `esptool.py --chip esp32s3 write_flash 0x0 revA_bringup_merged.bin`.

### If the port doesn't show up

1. Try another USB-C cable (charge-only cables are common).
2. Force the ROM bootloader: hold TP10 (BOOT, IO0) to GND, tap TP9 (EN) to
   GND, release TP10. Both pads are on the back. Flash again, then tap TP9 to
   run.

## Using it

Any serial terminal works (`pio device monitor`, `screen /dev/cu.usbmodem* 115200`,
the Arduino IDE Serial Monitor). Commands end with Enter; type `help` for the list.

```
selftest            run first, with nothing plugged into J1/J6
info                ID, all registers, battery, counters
noise ext           noise with your own shorted plug in J1
ch 1                one channel (TRS jack); ch 3 for the flex
leadoff on          then plot env, watch loffP/loffN
plot emg            20-450 Hz EMG, uV
plot env            activation envelope
stop
mains 50            if you're on 50 Hz mains (60 is the default)
```

For plots, close the terminal and open the Arduino IDE Serial Plotter on the
same port, then type `plot env` into its input box.

Raw capture (stop any open monitor first, since the port is single-user):

```sh
pip install pyserial numpy matplotlib
python tools/revA_host.py record --seconds 10 --out capture.csv --plot
```

## Notes

- Defaults: 3 channels, gain 6, 4000 SPS, RLD on, lead-off off, 60 Hz mains.
  Settings reset on reboot.
- DC lead-off injects 6 nA. Leave it off for the cleanest noise numbers.
- The `selftest` noise limits are guide values chosen to catch real faults,
  not datasheet limits.
- The old `../../app` (Zephyr, nRF) and `../../rnd/xiao_emg_reader` firmware
  are for earlier boards and don't run on Rev A.
