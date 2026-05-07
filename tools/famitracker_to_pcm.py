#!/usr/bin/env python3
"""
Render selected FamiTracker channels to mixed 8-bit PCM for ESP32 playback.

Outputs a header compatible with AudioSystem/Wavetable:
  <name>Samples, <name>Offsets, <name>SampleRate, <name> (Wavetable)

Example:
  python tools/famitracker_to_pcm.py tools/DK_test.txt --out gfx/dk_mix_pcm.h --name dk_mix ^
      --sq1 7 --sq2 6 --tri 5 --noi 8 --row-ms 38 --sample-rate 12000 --max-rows 512
"""

import argparse
import math
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

NOTE_RE = re.compile(r"^([A-G])([#-])([0-9])$")
NOISE_RE = re.compile(r"^([0-9A-F])([#-])$")
TOKEN_RE = re.compile(r"(?:[A-G][#-][0-9]|[0-9A-F][#-]|\.{3}|-{3}|={3})")

NOTE_INDEX = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}


def token_to_freq(tok: str) -> Optional[float]:
    if tok in ("...", "---", "==="):
        return None
    m = NOTE_RE.fullmatch(tok)
    if not m:
        return None
    n = m.group(1)
    acc = m.group(2)
    octv = int(m.group(3))
    name = n + ("#" if acc == "#" else "")
    if name not in NOTE_INDEX:
        return None
    midi = (octv + 1) * 12 + NOTE_INDEX[name]
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def noise_token_to_freq(tok: str) -> Optional[float]:
    if tok in ("...", "---", "==="):
        return None
    m = NOISE_RE.fullmatch(tok)
    if not m:
        return None
    idx = int(m.group(1), 16)
    # Simple perceptual mapping low->high for noise "pitch".
    return 120.0 + (idx * 140.0)


def parse_row_channels(path: str) -> List[List[str]]:
    rows: List[List[str]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("ROW "):
                continue
            parts = line.split(":")[1:]  # per-channel chunks
            row_tokens: List[str] = []
            for seg in parts:
                t = TOKEN_RE.findall(seg)
                row_tokens.append(t[0] if t else "...")
            rows.append(row_tokens)
    return rows


def build_channel_freqs(rows: List[List[str]], ch: int, hold_empty: bool = True) -> List[float]:
    out: List[float] = []
    current = 0.0
    for r in rows:
        tok = r[ch] if ch < len(r) else "..."
        if tok == "...":
            if hold_empty:
                out.append(current)
            else:
                current = 0.0
                out.append(0.0)
        elif tok in ("---", "==="):
            current = 0.0
            out.append(0.0)
        else:
            f = token_to_freq(tok)
            current = 0.0 if f is None else f
            out.append(current)
    return out


def build_noise_freqs(rows: List[List[str]], ch: int, hold_empty: bool = True) -> List[float]:
    out: List[float] = []
    current = 0.0
    for r in rows:
        tok = r[ch] if ch < len(r) else "..."
        if tok == "...":
            if hold_empty:
                out.append(current)
            else:
                current = 0.0
                out.append(0.0)
        elif tok in ("---", "==="):
            current = 0.0
            out.append(0.0)
        else:
            f = noise_token_to_freq(tok)
            current = 0.0 if f is None else f
            out.append(current)
    return out


def clip_i8(v: float) -> int:
    iv = int(round(v))
    if iv < -128:
        return -128
    if iv > 127:
        return 127
    return iv


def render_pcm(
    rows: List[List[str]],
    row_ms: float,
    sample_rate: int,
    sq1_ch: Optional[int],
    sq2_ch: Optional[int],
    tri_ch: Optional[int],
    noi_ch: Optional[int],
    sq1_shift: int,
    sq2_shift: int,
    tri_shift: int,
    max_rows: Optional[int],
) -> List[int]:
    if max_rows is not None and max_rows > 0:
        rows = rows[:max_rows]
    n_rows = len(rows)
    if n_rows == 0:
        return []

    sq1 = build_channel_freqs(rows, sq1_ch) if sq1_ch is not None else [0.0] * n_rows
    sq2 = build_channel_freqs(rows, sq2_ch) if sq2_ch is not None else [0.0] * n_rows
    tri = build_channel_freqs(rows, tri_ch) if tri_ch is not None else [0.0] * n_rows
    noi = build_noise_freqs(rows, noi_ch) if noi_ch is not None else [0.0] * n_rows

    # Optional transposition (in semitones) to separate voices when channels are in unison.
    sq1_mul = 2.0 ** (sq1_shift / 12.0)
    sq2_mul = 2.0 ** (sq2_shift / 12.0)
    tri_mul = 2.0 ** (tri_shift / 12.0)

    samples_per_row = max(1, int(round((row_ms / 1000.0) * sample_rate)))
    total = samples_per_row * n_rows

    # channel phases/state
    ph1 = 0.0
    ph2 = 0.0
    pht = 0.0
    lfsr = 0xACE1
    noise_phase = 0.0

    # conservative amplitudes to avoid clipping
    a1 = 28.0
    a2 = 24.0
    at = 22.0
    an = 14.0

    out: List[int] = [0] * total
    idx = 0
    for r in range(n_rows):
        f1 = sq1[r] * sq1_mul if sq1[r] > 0.0 else 0.0
        f2 = sq2[r] * sq2_mul if sq2[r] > 0.0 else 0.0
        ft = tri[r] * tri_mul if tri[r] > 0.0 else 0.0
        fn = noi[r]

        for _ in range(samples_per_row):
            s = 0.0

            if f1 > 0.0:
                ph1 += f1 / sample_rate
                if ph1 >= 1.0:
                    ph1 -= math.floor(ph1)
                s += a1 if ph1 < 0.5 else -a1

            if f2 > 0.0:
                ph2 += f2 / sample_rate
                if ph2 >= 1.0:
                    ph2 -= math.floor(ph2)
                # slight duty difference from sq1
                s += a2 if ph2 < 0.25 else -a2

            if ft > 0.0:
                pht += ft / sample_rate
                if pht >= 1.0:
                    pht -= math.floor(pht)
                tri_v = 4.0 * abs(pht - 0.5) - 1.0
                s += at * tri_v

            if fn > 0.0:
                noise_phase += fn / sample_rate
                if noise_phase >= 1.0:
                    steps = int(noise_phase)
                    noise_phase -= steps
                    for _ in range(steps):
                        bit = (lfsr ^ (lfsr >> 1)) & 1
                        lfsr = (lfsr >> 1) | (bit << 15)
                s += an if (lfsr & 1) else -an

            out[idx] = clip_i8(s)
            idx += 1

    return out


def wrap_i8(values: List[int], cols: int = 32) -> str:
    lines = []
    for i in range(0, len(values), cols):
        row = ", ".join(str(v) for v in values[i:i + cols])
        lines.append("  " + row + ",")
    return "\n".join(lines)


def make_header(name: str, pcm: List[int], sample_rate: int) -> str:
    offs_name = f"{name}Offsets"
    sam_name = f"{name}Samples"
    wt_name = name
    sr_name = f"{name}SampleRate"
    guard = re.sub(r"[^0-9A-Za-z_]", "_", f"{name}_pcm_h").upper()
    return (
        f"#ifndef {guard}\n#define {guard}\n\n"
        f"#include \"../AudioSystem.h\"\n\n"
        f"const int {sr_name} = {sample_rate};\n"
        f"const int {offs_name}[] = {{0, {len(pcm)}, }};\n"
        f"const signed char {sam_name}[] = {{\n{wrap_i8(pcm)}\n}};\n"
        f"Wavetable {wt_name}({sam_name}, 1, {offs_name}, {sr_name});\n\n"
        f"#endif // {guard}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Render FamiTracker channels to mixed PCM header.")
    ap.add_argument("input", help="FamiTracker text export file")
    ap.add_argument("--out", required=True, help="Output header file path")
    ap.add_argument("--name", default="ft_mix", help="Base symbol name (e.g. dk_mix)")
    ap.add_argument("--row-ms", type=float, default=38.0, help="Milliseconds per row")
    ap.add_argument("--sample-rate", type=int, default=12000, help="PCM sample rate")
    ap.add_argument("--max-rows", type=int, default=512, help="Render only first N rows")
    ap.add_argument("--sq1", type=int, default=None, help="Channel index for square 1")
    ap.add_argument("--sq2", type=int, default=None, help="Channel index for square 2")
    ap.add_argument("--tri", type=int, default=None, help="Channel index for triangle")
    ap.add_argument("--noi", type=int, default=None, help="Channel index for noise")
    ap.add_argument("--sq1-shift", type=int, default=0, help="Semitone transpose for square 1")
    ap.add_argument("--sq2-shift", type=int, default=0, help="Semitone transpose for square 2")
    ap.add_argument("--tri-shift", type=int, default=0, help="Semitone transpose for triangle")
    args = ap.parse_args()

    if args.sample_rate < 4000 or args.sample_rate > 48000:
        raise ValueError("--sample-rate must be between 4000 and 48000")
    if args.row_ms <= 0:
        raise ValueError("--row-ms must be > 0")

    rows = parse_row_channels(args.input)
    if not rows:
        raise ValueError("No ROW lines found in input")

    pcm = render_pcm(
        rows=rows,
        row_ms=args.row_ms,
        sample_rate=args.sample_rate,
        sq1_ch=args.sq1,
        sq2_ch=args.sq2,
        tri_ch=args.tri,
        noi_ch=args.noi,
        sq1_shift=args.sq1_shift,
        sq2_shift=args.sq2_shift,
        tri_shift=args.tri_shift,
        max_rows=args.max_rows,
    )
    if not pcm:
        raise ValueError("Rendered PCM is empty")

    header = make_header(args.name, pcm, args.sample_rate)
    out_abs = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "w", encoding="ascii") as f:
        f.write(header)

    print(f"Generated: {out_abs}")
    print(f"Rows used: {min(len(rows), args.max_rows if args.max_rows and args.max_rows > 0 else len(rows))}")
    print(f"Samples: {len(pcm)}")
    print(
        "Channels: "
        f"sq1={args.sq1}({args.sq1_shift}) "
        f"sq2={args.sq2}({args.sq2_shift}) "
        f"tri={args.tri}({args.tri_shift}) "
        f"noi={args.noi}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
