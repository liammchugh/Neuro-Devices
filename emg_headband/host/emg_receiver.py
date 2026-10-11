#!/usr/bin/env python3
"""Record EMG from the Zephyr headband (BLE) or the XIAO serial logger.

Transports
----------
ble
    Nordic/Zephyr firmware in ``../app``. Advertises as ``EMG_HEADBAND`` and
    notifies on 3f5b0002-d946-4844-b1ce-b29134ddeaf5 with five little-endian
    int16 samples per packet.
serial
    Arduino firmware in ``../rnd/xiao_emg_reader``. USB CDC at 460800 baud,
    one CSV row per sample: ``sample_index,raw_adc,median_adc``.

``--transport auto`` (the default) uses the serial port when exactly one
XIAO-like USB device is present, and otherwise scans for the BLE headband.
Pass ``--transport`` when both are attached.

``--plot`` opens a live window redrawn at 15 Hz. Capture keeps writing the CSV.
"""

import argparse
import asyncio
import csv
import signal
import struct
import sys
import threading
import time
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

DATA_UUID = "3f5b0002-d946-4844-b1ce-b29134ddeaf5"
BLE_NAME = "EMG_HEADBAND"
BLE_CHANNELS = 5
BAUD = 460800
SAMPLE_HZ = 1000
PLOT_HZ = 15
SERIAL_TAGS = ("usbmodem", "ttyacm", "esp32", "xiao", "usb serial", "jtag/serial")


def require_serial():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise SystemExit(
            "pyserial is required for serial capture: python -m pip install -r requirements.txt"
        ) from exc
    return serial, list_ports


def require_bleak():
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise SystemExit(
            "bleak is required for BLE capture: python -m pip install -r requirements.txt"
        ) from exc
    return BleakClient, BleakScanner


def serial_candidates(list_ports):
    matches = []
    for port in list_ports.comports():
        label = f"{port.device} {port.description}".lower()
        if any(tag in label for tag in SERIAL_TAGS):
            matches.append(port)
    return matches


def choose_port(requested, list_ports):
    if requested:
        return requested
    matches = serial_candidates(list_ports)
    for port in matches:
        print(f"Found: {port.device}: {port.description}")
    if len(matches) == 1:
        print(f"Auto-selected serial: {matches[0].device}")
        return matches[0].device
    if not matches:
        raise RuntimeError("No XIAO serial port found. Pass --port, or --transport ble.")
    raise RuntimeError("Several serial ports match. Pass --port.")


def resolve_transport(args, list_ports):
    if args.port and args.transport == "ble":
        raise SystemExit("--port applies to the serial logger, not BLE.")
    if args.transport == "serial" or args.port:
        return "serial"
    if args.transport == "ble":
        return "ble"
    matches = serial_candidates(list_ports)
    if len(matches) == 1:
        print(f"Auto-selected serial: {matches[0].device}: {matches[0].description}")
        args.port = matches[0].device
        return "serial"
    if len(matches) > 1:
        for port in matches:
            print(f"Found: {port.device}: {port.description}")
        raise SystemExit("Several serial ports match. Pass --port, or --transport ble.")
    print(f"No XIAO serial port found; scanning BLE for {args.name}")
    return "ble"


def next_filename(directory, transport):
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for number in range(1, 10000):
        base = directory / f"data_{date_str}_{transport}_test{number}"
        if not base.with_suffix(".csv").exists() and not base.with_suffix(".zip").exists():
            return base.with_suffix(".csv")
    raise RuntimeError("No unused test number found")


def zip_and_remove(csv_path, threshold):
    if csv_path is None or not csv_path.exists():
        print("No recording was created.")
        return
    if csv_path.stat().st_size <= threshold:
        print(f"Saved CSV: {csv_path}")
        return

    zip_path = csv_path.with_suffix(".zip")
    try:
        with zipfile.ZipFile(zip_path, mode="x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            archive.write(csv_path, arcname=csv_path.name)
        with zipfile.ZipFile(zip_path, "r") as archive:
            if archive.testzip() is not None:
                raise IOError("ZIP archive failed CRC verification")
            info = archive.getinfo(csv_path.name)
            if info.file_size != csv_path.stat().st_size:
                raise IOError("ZIP archive size mismatch")
    except Exception:
        print(f"Compression failed; original CSV retained: {csv_path}")
        raise
    csv_path.unlink()
    print(f"Compressed to: {zip_path} (original CSV deleted)")


class LivePlot:
    """Rolling scope. ``push`` is safe from the capture thread; ``show`` runs on the main thread."""

    def __init__(self, names, window_s, ylabel="ADC counts"):
        self.names = names
        self.window_s = window_s
        self.ylabel = ylabel
        self.lock = threading.Lock()
        self.times = deque()
        self.channels = [deque() for _ in names]

    def push(self, t, values):
        with self.lock:
            if self.times and t < self.times[-1]:
                self.times.clear()
                for channel in self.channels:
                    channel.clear()
            self.times.append(t)
            for channel, value in zip(self.channels, values):
                channel.append(value)
            cutoff = t - self.window_s
            while self.times and self.times[0] < cutoff:
                self.times.popleft()
                for channel in self.channels:
                    channel.popleft()

    def snapshot(self):
        with self.lock:
            if not self.times:
                return None
            return list(self.times), [list(channel) for channel in self.channels]

    def load_pyplot(self):
        cached = getattr(self, "_pyplot", None)
        if cached is not None:
            return cached
        try:
            import matplotlib
            if sys.platform == "darwin":
                try:
                    matplotlib.use("MacOSX")
                except Exception:
                    pass
            import matplotlib.pyplot as plt
            from matplotlib.animation import FuncAnimation
        except ImportError as exc:
            raise SystemExit(
                "matplotlib is required for --plot: python -m pip install -r requirements.txt"
            ) from exc
        if plt.get_backend().lower() == "agg":
            raise SystemExit("No interactive matplotlib backend is available; --plot needs a display.")
        self._pyplot = (plt, FuncAnimation)
        return self._pyplot

    def show(self, stop):
        plt, FuncAnimation = self.load_pyplot()
        fig, ax = plt.subplots()
        manager = getattr(fig.canvas, "manager", None)
        if manager is not None and hasattr(manager, "set_window_title"):
            manager.set_window_title("EMG")
        lines = [ax.plot([], [], label=name, linewidth=1.2)[0] for name in self.names]
        ax.set_xlim(0, self.window_s)
        ax.set_xlabel("sample time (s)")
        ax.set_ylabel(self.ylabel)
        ax.set_title(f"EMG  ({PLOT_HZ} Hz refresh)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")
        closed = {"value": False}

        def on_close(_event):
            closed["value"] = True
            stop.set()

        anim = {}

        def update(_frame):
            if closed["value"]:
                return lines
            if stop.is_set():
                event = anim.get("event")
                if event is not None:
                    event.event_source.stop()
                plt.close(fig)
                return lines
            snap = self.snapshot()
            if snap is None:
                return lines
            times, series = snap
            t_end = times[-1]
            for line, values in zip(lines, series):
                line.set_data(times, values)
            ax.set_xlim(t_end - self.window_s, t_end)
            finite = [value for values in series for value in values if value == value]
            if finite:
                lo, hi = min(finite), max(finite)
                if hi - lo < 20:
                    mid = (lo + hi) / 2
                    lo, hi = mid - 10, mid + 10
                else:
                    pad = 0.05 * (hi - lo)
                    lo, hi = lo - pad, hi + pad
                ax.set_ylim(lo, hi)
            return lines

        fig.canvas.mpl_connect("close_event", on_close)
        anim["event"] = FuncAnimation(
            fig, update, interval=1000 / PLOT_HZ, blit=False, cache_frame_data=False,
        )
        previous_sigint = signal.getsignal(signal.SIGINT)

        def on_sigint(_signum, _frame):
            if stop.is_set():
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                raise KeyboardInterrupt
            stop.set()

        signal.signal(signal.SIGINT, on_sigint)
        print(f"Live plot at {PLOT_HZ} Hz; close the window or press Ctrl+C to stop")
        try:
            plt.show()
        finally:
            signal.signal(signal.SIGINT, previous_sigint)


def record_serial(args, filename, progress, stop=None, plot=None):
    serial, _list_ports = require_serial()
    last_index = None
    started = time.monotonic()
    with serial.Serial(port=args.port, baudrate=args.baud, timeout=1) as esp32:
        with filename.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["host_time_utc", "sample_index", "sample_time_s", "raw_adc", "median_adc"])
            how = "close the plot or press Ctrl+C" if plot is not None else "Ctrl+C"
            print(f"Recording serial on {args.port} -> {filename}; {how} to stop")
            while stop is None or not stop.is_set():
                line = esp32.readline()
                if not line or not line.endswith(b"\n"):
                    continue
                text = line.decode("ascii", errors="replace").strip()
                if not text or text.startswith("#"):
                    if text.startswith("# ADC_ERROR"):
                        print(text)
                    continue
                fields = text.split(",")
                if len(fields) != 3:
                    continue
                try:
                    sample_index, raw, median = map(int, fields)
                except ValueError:
                    continue
                if not (0 <= raw <= 4095 and 0 <= median <= 4095):
                    continue
                if last_index is not None and sample_index > last_index + 1:
                    progress["skipped"] += sample_index - last_index - 1
                last_index = sample_index
                timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                writer.writerow([timestamp, sample_index, f"{sample_index / SAMPLE_HZ:.3f}", raw, median])
                if plot is not None:
                    plot.push(sample_index / SAMPLE_HZ, (raw, median))
                progress["count"] += 1
                if progress["count"] % 1000 == 0:
                    handle.flush()
                    print(
                        f"{progress['count']} samples | missing indices: {progress['skipped']}"
                        f" | elapsed: {time.monotonic() - started:.1f}s"
                    )


async def record_ble(args, filename, progress, stop=None, plot=None):
    BleakClient, BleakScanner = require_bleak()
    name = args.name

    def match(device, adv):
        advertised = device.name or getattr(adv, "local_name", None) or ""
        return name in advertised

    device = await BleakScanner.find_device_by_filter(match, timeout=args.scan_s)
    if device is None:
        print(f"BLE device {name!r} not found")
        if stop is not None:
            stop.set()
        return

    warned = False
    started = time.monotonic()
    t0 = time.time()

    with filename.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["host_time_utc", "elapsed_s", "ch0", "ch1", "ch2", "ch3", "ch4"])

        def on_notify(_handle, data):
            nonlocal warned
            if len(data) < 2 or len(data) % 2:
                return
            n = len(data) // 2
            if n != BLE_CHANNELS and not warned:
                print(f"BLE payload has {n} channels (expected {BLE_CHANNELS}); recording the first {BLE_CHANNELS}")
                warned = True
            samples = struct.unpack("<" + "h" * min(n, BLE_CHANNELS), data[:min(n, BLE_CHANNELS) * 2])
            row = [""] * BLE_CHANNELS
            for i, sample in enumerate(samples):
                row[i] = sample
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            elapsed = time.time() - t0
            writer.writerow([timestamp, f"{elapsed:.6f}", *row])
            if plot is not None:
                values = [float(sample) for sample in samples]
                values.extend(float("nan") for _ in range(BLE_CHANNELS - len(values)))
                plot.push(progress["count"] / SAMPLE_HZ, values)
            progress["count"] += 1
            if progress["count"] % 1000 == 0:
                handle.flush()
                print(f"{progress['count']} samples | elapsed: {time.monotonic() - started:.1f}s")

        async with BleakClient(device) as client:
            await client.start_notify(DATA_UUID, on_notify)
            how = "close the plot or press Ctrl+C" if plot is not None else "Ctrl+C"
            print(f"Recording BLE {device.name or name} -> {filename}; {how} to stop")
            while stop is None or not stop.is_set():
                await asyncio.sleep(0.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--transport", choices=("auto", "ble", "serial"), default="auto",
                        help="auto uses a lone XIAO serial port, otherwise BLE (default: auto)")
    parser.add_argument("--port", help="serial port, e.g. /dev/cu.usbmodem101 or COM5")
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--name", default=BLE_NAME, help="BLE local name to match")
    parser.add_argument("--scan-s", type=float, default=10.0, help="BLE scan timeout")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--zip-mb", type=float, default=10.0)
    parser.add_argument("--plot", action="store_true", help=f"live plot, redrawn at {PLOT_HZ} Hz")
    parser.add_argument("--plot-seconds", type=float, default=5.0, help="seconds of history in the live plot")
    args = parser.parse_args()
    if args.zip_mb < 0:
        parser.error("--zip-mb must be >= 0")
    if args.plot_seconds <= 0:
        parser.error("--plot-seconds must be > 0")

    list_ports = None
    if args.transport != "ble":
        try:
            _serial, list_ports = require_serial()
        except SystemExit:
            if args.transport == "serial" or args.port:
                raise
            print("pyserial is not installed; scanning BLE instead")
    if list_ports is None:
        transport = "ble"
    else:
        transport = resolve_transport(args, list_ports)
    if transport == "serial":
        args.port = choose_port(args.port, list_ports)
    else:
        require_bleak()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = next_filename(args.output_dir, transport)
    progress = {"count": 0, "skipped": 0}
    stop = threading.Event()
    if transport == "serial":
        plot_names = ("raw_adc", "median_adc")
    else:
        plot_names = tuple(f"ch{i}" for i in range(BLE_CHANNELS))
    plot = LivePlot(plot_names, args.plot_seconds) if args.plot else None

    def run_capture():
        try:
            if transport == "serial":
                record_serial(args, filename, progress, stop, plot)
            else:
                asyncio.run(record_ble(args, filename, progress, stop, plot))
        except Exception as exc:
            progress["error"] = exc
            stop.set()

    try:
        if plot is None:
            if transport == "serial":
                record_serial(args, filename, progress)
            else:
                asyncio.run(record_ble(args, filename, progress))
        else:
            plot.load_pyplot()
            worker = threading.Thread(target=run_capture, name="emg-capture", daemon=True)
            worker.start()
            try:
                plot.show(stop)
            finally:
                stop.set()
                worker.join(timeout=3)
            if progress.get("error") is not None:
                raise progress["error"]
    except KeyboardInterrupt:
        print("\nStopping recording...")
    finally:
        print(f"Recorded {progress['count']} samples; observed missing indices: {progress['skipped']}")
        zip_and_remove(filename, int(args.zip_mb * 1024 * 1024))


if __name__ == "__main__":
    main()
