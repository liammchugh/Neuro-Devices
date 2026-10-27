#!/usr/bin/env python3
"""Record raw ADS1298 data from the Rev A bring-up firmware over USB serial.

    python revA_host.py record --seconds 10 --out capture.csv [--port /dev/cu.usbmodem101]
    python revA_host.py record --seconds 10 --out capture.csv --plot   # PSD + time plot

The firmware's `bin` mode sends 18-byte frames:
    A5 5A | index u32 LE | loffP | loffN | CH1..CH3 int24 LE | xor of bytes 2..16
preceded by a text line "#BIN fs=... gain=... nch=... uv_per_lsb=... frame=18".

The CSV has one row per sample: index, loffP, loffN, ch1_uV, ch2_uV, ch3_uV.
Requires: pyserial, numpy (matplotlib for --plot).
"""

import argparse
import csv
import sys
import time

import numpy as np
import serial
from serial.tools import list_ports

FRAME = 18


def find_port():
    ports = [p for p in list_ports.comports()
             if p.vid == 0x303A or "usbmodem" in p.device.lower() or "ttyacm" in p.device.lower()]
    if len(ports) != 1:
        names = ", ".join(p.device for p in list_ports.comports()) or "none"
        sys.exit(f"pass --port (found: {names})")
    return ports[0].device


def parse_frames(buf):
    """Return (rows, remaining_bytes, bad_count). rows: list of (idx, lp, ln, c1, c2, c3)."""
    rows, bad, i = [], 0, 0
    while i + FRAME <= len(buf):
        if buf[i] != 0xA5 or buf[i + 1] != 0x5A:
            i += 1
            continue
        f = buf[i:i + FRAME]
        x = 0
        for b in f[2:17]:
            x ^= b
        if x != f[17]:
            bad += 1
            i += 1
            continue
        idx = int.from_bytes(f[2:6], "little")
        chans = [int.from_bytes(f[8 + 3 * k:11 + 3 * k], "little", signed=True) for k in range(3)]
        rows.append((idx, f[6], f[7], *chans))
        i += FRAME
    return rows, buf[i:], bad


def record(args):
    port = args.port or find_port()
    ser = serial.Serial(port, 115200, timeout=0.2)
    ser.write(b"stop\n")
    time.sleep(0.3)
    ser.reset_input_buffer()
    ser.write(b"bin\n")
    header = None
    t0 = time.time()
    pending = b""
    while header is None:
        pending += ser.read(256)
        if b"#BIN" in pending:
            start = pending.index(b"#BIN")
            end = pending.find(b"\n", start)
            if end > 0:
                header = dict(kv.split("=") for kv in pending[start:end].decode().split()[1:])
                pending = pending[end + 1:]
        if time.time() - t0 > 3:
            sys.exit("no #BIN header; is the bring-up firmware running?")
    fs = int(header["fs"])
    uv = float(header["uv_per_lsb"])
    nch = int(header["nch"])
    want = int(args.seconds * fs)
    print(f"{port}: fs={fs} gain={header['gain']} nch={nch}, recording {args.seconds} s")

    rows, bad, buf = [], 0, bytearray(pending)
    while len(rows) < want:
        buf += ser.read(8192)
        new, rest, b = parse_frames(buf)
        rows += new
        bad += b
        buf = bytearray(rest)
    ser.write(b"stop\n")
    ser.close()
    rows = rows[:want]

    idx = np.array([r[0] for r in rows], dtype=np.int64)
    gaps = int(np.sum(np.diff(idx) - 1)) if len(idx) > 1 else 0
    data = np.array([r[3:3 + nch] for r in rows], dtype=float) * uv
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["index", "loffP", "loffN"] + [f"ch{k + 1}_uV" for k in range(nch)])
        for r, d in zip(rows, data):
            w.writerow([r[0], r[1], r[2]] + [f"{v:.3f}" for v in d])
    print(f"wrote {len(rows)} samples to {args.out}; missing samples: {gaps}, bad frames: {bad}")

    for k in range(nch):
        x = data[:, k] - data[:, k].mean()
        print(f"CH{k + 1}: offset {data[:, k].mean():+.1f} uV, ac rms {x.std():.2f} uV, "
              f"pp {np.ptp(x):.1f} uV")
    if args.plot:
        plot(data, fs)


def plot(data, fs):
    import matplotlib.pyplot as plt
    fig, (ax_t, ax_f) = plt.subplots(2, 1, figsize=(10, 7))
    t = np.arange(len(data)) / fs
    for k in range(data.shape[1]):
        x = data[:, k] - data[:, k].mean()
        ax_t.plot(t, x, lw=0.5, label=f"CH{k + 1}")
        seg = min(len(x), fs * 2)
        nseg = len(x) // seg
        win = np.hanning(seg)
        psd = np.mean([np.abs(np.fft.rfft(win * x[i * seg:(i + 1) * seg])) ** 2
                       for i in range(nseg)], axis=0) / (fs * np.sum(win ** 2))
        ax_f.semilogy(np.fft.rfftfreq(seg, 1 / fs), np.sqrt(2 * psd), lw=0.7, label=f"CH{k + 1}")
    ax_t.set(xlabel="s", ylabel="uV (mean removed)")
    ax_f.set(xlabel="Hz", ylabel="uV/sqrt(Hz)", xlim=(0, min(fs / 2, 1000)))
    for a in (ax_t, ax_f):
        a.grid(alpha=0.3)
        a.legend()
    plt.tight_layout()
    plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--port")
    r.add_argument("--seconds", type=float, default=10)
    r.add_argument("--out", default="capture.csv")
    r.add_argument("--plot", action="store_true")
    args = ap.parse_args()
    if args.cmd == "record":
        record(args)


if __name__ == "__main__":
    main()
