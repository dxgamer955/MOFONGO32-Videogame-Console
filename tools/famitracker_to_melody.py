#!/usr/bin/env python3
"""
Convert FamiTracker text exports into ESP32 melody arrays.

Expected note tokens in input lines:
  C-4, C#4, D-5, ... (empty), --- (note cut/off), === (halt)

Typical usage:
  python tools/famitracker_to_melody.py song.txt --out gfx/melody.h --channel 0 --row-ms 100

Or derive row duration from BPM:
  python tools/famitracker_to_melody.py song.txt --out gfx/melody.h --bpm 150 --rows-per-beat 4
"""

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple


NOTE_RE = re.compile(r"^([A-G])([#-])([0-9])$")
TOKEN_RE = re.compile(r"(?:[A-G][#-][0-9]|\.{3}|-{3}|={3})")

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


def note_token_to_freq(token: str) -> Optional[float]:
    if token in ("...", "---", "==="):
        return None
    m = NOTE_RE.fullmatch(token)
    if not m:
        return None
    name = m.group(1)
    accidental = m.group(2)
    octave = int(m.group(3))
    if accidental == "#":
        key = name + "#"
    else:
        key = name
    if key not in NOTE_INDEX:
        return None
    midi = (octave + 1) * 12 + NOTE_INDEX[key]
    # MIDI A4=69 -> 440Hz
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def parse_rows(path: str, channel: int) -> List[str]:
    rows: List[str] = []
    row_lines_found = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("ROW "):
                continue
            row_lines_found += 1
            # FamiTracker row format:
            # ROW xx : ch0 tokens : ch1 tokens : ...
            parts = line.split(":")
            if len(parts) < 2:
                continue
            channel_parts = parts[1:]  # each chunk corresponds to one channel
            if channel < len(channel_parts):
                segment = channel_parts[channel]
                tokens = TOKEN_RE.findall(segment)
                rows.append(tokens[0] if tokens else "...")
            else:
                rows.append("...")

    if row_lines_found > 0:
        return rows

    # Fallback for simplified custom text that does not include "ROW "
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            tokens = TOKEN_RE.findall(line)
            if not tokens:
                continue
            if channel < len(tokens):
                rows.append(tokens[channel])
            else:
                rows.append("...")
    return rows


def rows_to_events(rows: List[str], row_ms: int, hold_empty: bool) -> List[Tuple[float, int]]:
    # Event: (freq_hz_or_0_for_rest, duration_ms)
    events: List[Tuple[float, int]] = []
    current_freq: Optional[float] = None

    def emit(freq: float, dur: int) -> None:
        if dur <= 0:
            return
        if events and abs(events[-1][0] - freq) < 1e-6:
            prev_f, prev_d = events[-1]
            events[-1] = (prev_f, prev_d + dur)
        else:
            events.append((freq, dur))

    for tok in rows:
        if tok == "...":
            if hold_empty:
                freq = 0.0 if current_freq is None else current_freq
            else:
                freq = 0.0
                current_freq = None
        elif tok in ("---", "==="):
            freq = 0.0
            current_freq = None
        else:
            nfreq = note_token_to_freq(tok)
            if nfreq is None:
                freq = 0.0
                current_freq = None
            else:
                freq = nfreq
                current_freq = nfreq
        emit(freq, row_ms)

    return events


def events_to_c_arrays(events: List[Tuple[float, int]], prefix: str) -> str:
    notes = ", ".join(("0.0f" if e[0] == 0.0 else f"{e[0]:.2f}f") for e in events)
    durs = ", ".join(str(min(65535, max(1, e[1]))) for e in events)
    return (
        "#pragma once\n\n"
        f"const float {prefix}Notes[] = {{\n  {notes}\n}};\n"
        f"const unsigned short {prefix}DurMs[] = {{\n  {durs}\n}};\n"
        f"const int {prefix}Len = sizeof({prefix}Notes) / sizeof({prefix}Notes[0]);\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert FamiTracker text notes to ESP32 melody arrays.")
    ap.add_argument("input", help="Input text file exported from FamiTracker.")
    ap.add_argument("--out", required=True, help="Output .h file.")
    ap.add_argument("--channel", type=int, default=0, help="Note column/channel index per row (default 0).")
    ap.add_argument("--row-ms", type=int, default=None, help="Milliseconds per row.")
    ap.add_argument("--bpm", type=float, default=150.0, help="Used when --row-ms is omitted (default 150).")
    ap.add_argument("--rows-per-beat", type=float, default=4.0, help="Used when --row-ms is omitted (default 4).")
    ap.add_argument("--no-hold-empty", action="store_true", help="Treat '...' as rest instead of sustain.")
    ap.add_argument("--prefix", default="melody", help="C array variable prefix.")
    args = ap.parse_args()

    if args.channel < 0:
        raise ValueError("--channel must be >= 0")

    if args.row_ms is not None:
        row_ms = args.row_ms
    else:
        if args.bpm <= 0 or args.rows_per_beat <= 0:
            raise ValueError("--bpm and --rows-per-beat must be > 0")
        row_ms = int(round(60000.0 / (args.bpm * args.rows_per_beat)))

    if row_ms <= 0:
        raise ValueError("row duration must be > 0 ms")

    rows = parse_rows(args.input, args.channel)
    if not rows:
        raise ValueError("No note-like tokens found. Verify text export format.")

    events = rows_to_events(rows, row_ms=row_ms, hold_empty=not args.no_hold_empty)
    if not events:
        raise ValueError("No melody events generated.")

    header = events_to_c_arrays(events, args.prefix)
    out_abs = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "w", encoding="ascii") as f:
        f.write(header)

    note_count = sum(1 for f, _ in events if f > 0)
    rest_count = sum(1 for f, _ in events if f == 0)
    print(f"Generated: {out_abs}")
    print(f"Rows parsed: {len(rows)}")
    print(f"Events: {len(events)} (notes={note_count}, rests={rest_count})")
    print(f"Row duration: {row_ms} ms")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
