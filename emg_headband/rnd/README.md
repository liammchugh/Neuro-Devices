# XIAO ESP32-S3 EMG logger

Experimental single-channel USB logger. Firmware is `xiao_emg_reader/xiao_emg_reader.ino`. The Zephyr headband firmware stays in `../app`. Both are recorded by `../host/emg_receiver.py`.

## Hardware

For an AD8232-style breakout powered at 3.3 V:

| Module | XIAO ESP32-S3 |
|---|---|
| 3.3V | 3V3 |
| GND | GND |
| OUTPUT / SIG | D0 / A0 / GPIO1 |

Optional LO+ and LO- can be left disconnected (not used in firmware).
Do not wire analog output to 5V/VBUS. Keep the signal within the ESP32-S3 ADC input range.

**Safety:** This prototype is not a medically isolated bioamplifier. Do not attach skin/body electrodes when USB is connected to a computer or wall-powered supply. Use suitable battery-powered isolation-rated acquisition hardware for body-connected recordings.

## Arduino IDE

1. Install the **esp32 by Espressif Systems** board package (3.x series) in Boards Manager.
2. Select **XIAO_ESP32S3** under Tools > Board (in some releases displayed as Seeed XIAO ESP32S3).
3. Set **USB CDC On Boot: Enabled**. Connect the XIAO with a USB-C data cable.
4. Open `xiao_emg_reader/xiao_emg_reader.ino` and upload. If upload fails, enter bootloader: hold BOOT, tap RESET, release BOOT, then select the newly detected port and upload.
5. Optional: open Serial Monitor at 460800 baud (close it before Python opens the same port).

Firmware sends `sample_index,raw_adc,median_adc` CSV rows at a nominal 1000 Hz. ADC hardware is clocked at 20000 Hz and one in 20 samples is retained. A five-point median is performed on the retained stream. There is no timer polling or blocking delay in `loop()`.

Note: This is *decimation without an anti-alias low-pass filter*. For faithful raw EMG waveform acquisition, design an appropriate analog/digital anti-alias filter, and characterize the front-end's bandwidth. The AD8232 is primarily an ECG front-end; suitability for raw EMG depends on its external filter components.

## Python (macOS/Linux)

```bash
cd emg_headband/host
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m serial.tools.list_ports -v
python emg_receiver.py --transport serial --port /dev/cu.usbmodemXXXX
```

## Python (Windows PowerShell)

```powershell
cd emg_headband\host
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m serial.tools.list_ports -v
python emg_receiver.py --transport serial --port COM5
```

Replace the port example with your actual port. With no flags, `python emg_receiver.py` uses the serial port when exactly one recognizable USB device is present, and otherwise scans BLE for the Zephyr `EMG_HEADBAND`. Pass `--transport ble` to force the headband, or `--transport serial` to force the XIAO.

Add `--plot` for a live window redrawn at 15 Hz (last 5 seconds; `--plot-seconds` changes the history). Close the window or press Ctrl+C to stop. The CSV is still written.

Press Ctrl+C to stop. Recordings are saved under `host/data/` as CSV (git-ignored). CSVs larger than 10 MiB are archived into ZIP, integrity checked, and then removed. Smaller CSVs are retained as-is. Override threshold with `--zip-mb 5`.

Data columns: `host_time_utc`, `sample_index`, `sample_time_s`, `raw_adc`, `median_adc`. Host timestamps reflect **USB reception**, not actual instant of conversion. `sample_time_s` is inferred from the nominal 1 kHz clock; inspect index gaps and elapsed wall time to validate capture.

## Troubleshooting

- **No serial port:** check the cable is data-capable, USB CDC On Boot enabled, and USB permissions. On macOS `/dev/cu.usbmodem*` is common; on Windows use `COMx`.
- **Wrong ADC value:** GPIO35 was specific to the old ESP32 and is NOT the new input; use physical D0 = GPIO1. Raw values should normally be 0–4095.
- **Missing indices:** Python reports gaps. A poor USB connection, host scheduling stalls, or excessive throughput can lose data; for high-rate recording consider a binary protocol and larger queues.
- **Firmware compile failure:** ensure Espressif Arduino-ESP32 core **3.x**, which includes `esp_adc/adc_continuous.h`.
