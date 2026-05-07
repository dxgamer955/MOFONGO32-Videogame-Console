#!/usr/bin/env python3
"""
Convert one or more FamiTracker TXT exports directly into a songs.h atlas.
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


NOTE_RE = re.compile(r"^([A-G])([#-])([0-9])$")
NOISE_RE = re.compile(r"^([0-9A-Fa-f])-\#$")
TOKEN_RE = re.compile(r"(?:[A-G][#-][0-9]|[0-9A-Fa-f]-\#|\.{3}|-{3}|={3})")
ORDER_RE = re.compile(r"^ORDER\s+([0-9A-Fa-f]{2})\s*:\s*(.+)$")
PATTERN_RE = re.compile(r"^PATTERN\s+([0-9A-Fa-f]{2})\s*$")
TRACK_RE = re.compile(r"^TRACK\s+(\d+)\s+(\d+)\s+(\d+)\s+\".*\"$")

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


def sanitize_ident(name: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not out:
        out = "song"
    if out[0].isdigit():
        out = "_" + out
    return out


def note_token_to_freq(token: str) -> Optional[float]:
    if token in ("...", "---", "==="):
        return None
    nm = NOISE_RE.fullmatch(token)
    if nm:
        # FamiTracker noise notes (e.g. 2-#, A-#): map to synthetic trigger rates.
        # Runtime noise voice only needs freq > 1 to turn voice on.
        idx = int(nm.group(1), 16)
        if idx < 0:
            idx = 0
        if idx > 15:
            idx = 15
        return 120.0 + float(idx) * 28.0
    m = NOTE_RE.fullmatch(token)
    if not m:
        return None
    name = m.group(1)
    accidental = m.group(2)
    octave = int(m.group(3))
    key = name + "#" if accidental == "#" else name
    if key not in NOTE_INDEX:
        return None
    midi = (octave + 1) * 12 + NOTE_INDEX[key]
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def parse_ft_timing(path: str) -> Optional[int]:
    machine = 0
    framerate = 0
    speed = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("MACHINE"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    machine = int(parts[1])
            elif line.startswith("FRAMERATE"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    framerate = int(parts[1])
            else:
                tm = TRACK_RE.match(line)
                if tm:
                    speed = int(tm.group(2))
                    break
    if speed <= 0:
        return None
    hz = float(framerate) if framerate > 0 else (50.0 if machine == 1 else 60.0)
    if hz <= 0.0:
        return None
    row_ms = int(round((1000.0 * float(speed)) / hz))
    return max(1, row_ms)


def parse_rows(path: str, channel: int) -> List[str]:
    # Parse using ORDER + PATTERN blocks to respect song arrangement.
    order_seq: List[List[int]] = []
    patterns: Dict[int, List[List[str]]] = {}
    current_pattern: Optional[int] = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            om = ORDER_RE.match(s)
            if om:
                cols = om.group(2).split()
                seq = []
                for c in cols:
                    try:
                        seq.append(int(c, 16))
                    except Exception:
                        seq.append(0)
                order_seq.append(seq)
                continue
            pm = PATTERN_RE.match(s)
            if pm:
                try:
                    current_pattern = int(pm.group(1), 16)
                    patterns.setdefault(current_pattern, [])
                except Exception:
                    current_pattern = None
                continue
            if not s.startswith("ROW "):
                continue
            parts = s.split(":")
            if len(parts) < 2 or current_pattern is None:
                continue
            row_tokens: List[str] = []
            for seg in parts[1:]:
                tokens = TOKEN_RE.findall(seg)
                row_tokens.append(tokens[0] if tokens else "...")
            patterns[current_pattern].append(row_tokens)

    if patterns:
        rows: List[str] = []
        if order_seq:
            for order in order_seq:
                pat = order[channel] if channel < len(order) else order[0]
                pat_rows = patterns.get(pat, [])
                for row in pat_rows:
                    rows.append(row[channel] if channel < len(row) else "...")
        else:
            for pat in sorted(patterns.keys()):
                for row in patterns[pat]:
                    rows.append(row[channel] if channel < len(row) else "...")
        if rows:
            return rows

    # Fallback parser for simplified/legacy exports.
    rows: List[str] = []
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


def parse_channel_list(value: str) -> List[int]:
    out: List[int] = []
    for p in (value or "").split(","):
        t = p.strip()
        if not t:
            continue
        ch = int(t)
        if ch < 0:
            raise ValueError("channel indexes must be >= 0")
        out.append(ch)
    if not out:
        raise ValueError("mix channel list is empty")
    return out


def rows_to_events_multi(rows_by_channel: List[List[str]], row_ms: int, hold_empty: bool) -> List[Tuple[float, int]]:
    if not rows_by_channel:
        return []
    max_rows = max((len(r) for r in rows_by_channel), default=0)
    if max_rows <= 0:
        return []

    current_freq: List[Optional[float]] = [None] * len(rows_by_channel)
    events: List[Tuple[float, int]] = []

    def emit(freq: float, dur: int) -> None:
        if dur <= 0:
            return
        if events and abs(events[-1][0] - freq) < 1e-6:
            pf, pd = events[-1]
            events[-1] = (pf, pd + dur)
        else:
            events.append((freq, dur))

    for i in range(max_rows):
        active: List[float] = []
        for ch_i, rows in enumerate(rows_by_channel):
            tok = rows[i] if i < len(rows) else "..."
            if tok == "...":
                if hold_empty:
                    freq = 0.0 if current_freq[ch_i] is None else current_freq[ch_i]
                else:
                    freq = 0.0
                    current_freq[ch_i] = None
            elif tok in ("---", "==="):
                freq = 0.0
                current_freq[ch_i] = None
            else:
                nfreq = note_token_to_freq(tok)
                if nfreq is None:
                    freq = 0.0
                    current_freq[ch_i] = None
                else:
                    freq = nfreq
                    current_freq[ch_i] = nfreq
            if freq > 1.0:
                active.append(freq)

        if not active:
            emit(0.0, row_ms)
            continue
        if len(active) == 1:
            emit(active[0], row_ms)
            continue

        n = len(active)
        step = max(1, row_ms // n)
        used = 0
        for idx, f in enumerate(active):
            if idx == (n - 1):
                dur = max(1, row_ms - used)
            else:
                dur = step
            used += dur
            emit(f, dur)

    return events


def build_header(songs: List[dict], out_path: str, settings: dict) -> str:
    out_dir = os.path.dirname(os.path.abspath(out_path))
    meta = {
        "type": "songs_atlas_v1",
        "settings": settings,
        "songs": [],
    }
    for s in songs:
        in_abs = os.path.abspath(s["input"])
        rel = os.path.relpath(in_abs, out_dir).replace("\\", "/")
        meta["songs"].append(
            {
                "name": s["name"],
                "source": s["source"],
                "input": rel,
                "row_ms": int(s.get("row_ms", 0)),
            }
        )
    meta_json = json.dumps(meta, separators=(",", ":"))

    lines: List[str] = []
    lines.append("#pragma once")
    lines.append("")
    lines.append("// Auto-generated by tools/famitracker_to_song_atlas.py")
    lines.append(f"// SONGS_ATLAS_META: {meta_json}")
    lines.append("")
    lines.append("struct SongDef")
    lines.append("{")
    lines.append("  const char *name;")
    lines.append("  const float *notes;")
    lines.append("  const unsigned short *durMs;")
    lines.append("  int len;")
    lines.append("};")
    if settings.get("export_4ch", False):
        lines.append("")
        lines.append("#define SONGS_HAS_4CH 1")
        lines.append("struct SongChannelsDef")
        lines.append("{")
        lines.append("  const float *notes[4];")
        lines.append("  const unsigned short *durMs[4];")
        lines.append("  int len[4];")
        lines.append("  unsigned char wave[4];")
        lines.append("  unsigned char channelCount;")
        lines.append("};")
    lines.append("")

    for s in songs:
        ident = s["ident"]
        notes = ", ".join("0.0f" if f == 0.0 else f"{f:.2f}f" for f, _ in s["events"])
        durs = ", ".join(str(max(1, min(65535, d))) for _, d in s["events"])
        lines.append(f"static const float {ident}Notes[] = {{{notes}}};")
        lines.append(f"static const unsigned short {ident}DurMs[] = {{{durs}}};")
        lines.append(f"static const int {ident}Len = sizeof({ident}Notes) / sizeof({ident}Notes[0]);")
        if settings.get("export_4ch", False):
            ch_events = s.get("events_ch4", [])
            for ci in range(min(4, len(ch_events))):
                ce = ch_events[ci]
                cnotes = ", ".join("0.0f" if f == 0.0 else f"{f:.2f}f" for f, _ in ce)
                cdurs = ", ".join(str(max(1, min(65535, d))) for _, d in ce)
                lines.append(f"static const float {ident}Ch{ci}Notes[] = {{{cnotes}}};")
                lines.append(f"static const unsigned short {ident}Ch{ci}DurMs[] = {{{cdurs}}};")
                lines.append(f"static const int {ident}Ch{ci}Len = sizeof({ident}Ch{ci}Notes) / sizeof({ident}Ch{ci}Notes[0]);")
        lines.append("")

    lines.append("const SongDef songs[] = {")
    for s in songs:
        ident = s["ident"]
        song_name = s["name"].replace('"', "'")
        lines.append(f'  {{"{song_name}", {ident}Notes, {ident}DurMs, {ident}Len}},')
    lines.append("};")
    lines.append("const int songsCount = sizeof(songs) / sizeof(songs[0]);")
    if settings.get("export_4ch", False):
        lines.append("")
        lines.append("const SongChannelsDef songsCh[] = {")
        for s in songs:
            ident = s["ident"]
            ch_count = min(4, len(s.get("events_ch4", [])))
            note_ptrs = []
            dur_ptrs = []
            lens = []
            waves = []
            for ci in range(4):
                if ci < ch_count:
                    note_ptrs.append(f"{ident}Ch{ci}Notes")
                    dur_ptrs.append(f"{ident}Ch{ci}DurMs")
                    lens.append(f"{ident}Ch{ci}Len")
                else:
                    note_ptrs.append("nullptr")
                    dur_ptrs.append("nullptr")
                    lens.append("0")
                # NES-style defaults: pulse1, pulse2, triangle, noise
                waves.append(str(ci))
            lines.append(
                "  {"
                + "{"
                + ", ".join(note_ptrs)
                + "}, {"
                + ", ".join(dur_ptrs)
                + "}, {"
                + ", ".join(lens)
                + "}, {"
                + ", ".join(waves)
                + "}, "
                + str(ch_count)
                + "},"
            )
        lines.append("};")
    lines.append("")
    return "\n".join(lines)


def _count_note_events(events: List[Tuple[float, int]]) -> int:
    return sum(1 for f, _ in events if f > 1.0)


def _pick_best_channel(path: str, row_ms: int, hold_empty: bool, max_channels: int = 8) -> Tuple[int, List[Tuple[float, int]]]:
    best_ch = 0
    best_events: List[Tuple[float, int]] = []
    best_count = -1
    for ch in range(max_channels):
        rows = parse_rows(path, ch)
        if not rows:
            continue
        ev = rows_to_events(rows, row_ms=row_ms, hold_empty=hold_empty)
        n = _count_note_events(ev)
        if n > best_count:
            best_count = n
            best_ch = ch
            best_events = ev
    return best_ch, best_events


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert FamiTracker TXT files into songs.h atlas")
    ap.add_argument("inputs", nargs="+", help="Input FamiTracker TXT files")
    ap.add_argument("--out", required=True, help="Output songs.h")
    ap.add_argument("--channel", type=int, default=0, help="Channel index (default 0)")
    ap.add_argument("--row-ms", type=int, default=None, help="Milliseconds per row")
    ap.add_argument("--bpm", type=float, default=150.0, help="Used when --row-ms omitted")
    ap.add_argument("--rows-per-beat", type=float, default=4.0, help="Used when --row-ms omitted")
    ap.add_argument("--ft-timing", action="store_true", help="Use FamiTracker timing (MACHINE/FRAMERATE + TRACK speed)")
    ap.add_argument("--mix-4ch", action="store_true", help="Mix multiple channels into one melodic stream (arpeggio)")
    ap.add_argument("--mix-channels", default="0,1,2,3", help="Comma-separated channels to mix (default 0,1,2,3)")
    ap.add_argument("--export-4ch", action="store_true", help="Also export per-song 4-channel tables for engine mixer")
    ap.add_argument("--channels-4ch", default="0,1,2,3", help="Comma-separated source channels for 4ch export")
    ap.add_argument("--no-hold-empty", action="store_true", help="Treat ... as rest")
    ap.add_argument("--no-auto-channel", action="store_true", help="Disable fallback channel auto-detect")
    args = ap.parse_args()

    if args.channel < 0:
        raise ValueError("--channel must be >= 0")
    mix_channels = parse_channel_list(args.mix_channels) if args.mix_4ch else []
    channels_4ch = parse_channel_list(args.channels_4ch) if args.export_4ch else []
    base_row_ms: Optional[int] = None
    if not args.ft_timing:
        if args.row_ms is not None:
            base_row_ms = args.row_ms
        else:
            if args.bpm <= 0 or args.rows_per_beat <= 0:
                raise ValueError("--bpm and --rows-per-beat must be > 0")
            base_row_ms = int(round(60000.0 / (args.bpm * args.rows_per_beat)))
        if base_row_ms <= 0:
            raise ValueError("row duration must be > 0")

    songs = []
    used = set()
    for i, p in enumerate(args.inputs):
        in_abs = os.path.abspath(p)
        if not os.path.isfile(in_abs):
            raise ValueError(f"Missing input: {p}")
        base = os.path.splitext(os.path.basename(in_abs))[0]
        name = sanitize_ident(base).lower()
        ident = name
        k = 2
        while ident in used:
            ident = f"{name}_{k}"
            k += 1
        used.add(ident)

        row_ms = base_row_ms
        if args.ft_timing:
            row_ms = parse_ft_timing(in_abs)
            if row_ms is None:
                raise ValueError(
                    f"{os.path.basename(in_abs)} has no valid TRACK speed/framerate; "
                    "use --row-ms/--bpm or fix TXT export."
                )

        if args.mix_4ch:
            rows_multi = [parse_rows(in_abs, ch) for ch in mix_channels]
            if not any(rows_multi):
                raise ValueError(f"No note rows found in {p}")
            events = rows_to_events_multi(rows_multi, row_ms=row_ms, hold_empty=not args.no_hold_empty)
        else:
            rows = parse_rows(in_abs, args.channel)
            if not rows:
                raise ValueError(f"No note rows found in {p}")
            events = rows_to_events(rows, row_ms=row_ms, hold_empty=not args.no_hold_empty)
        if not events:
            raise ValueError(f"No melody events generated for {p}")

        note_count = _count_note_events(events)
        if note_count == 0 and (not args.no_auto_channel) and (not args.mix_4ch):
            best_ch, best_events = _pick_best_channel(in_abs, row_ms=row_ms, hold_empty=not args.no_hold_empty)
            best_notes = _count_note_events(best_events)
            if best_notes > 0:
                print(f"INFO: {os.path.basename(in_abs)} channel {args.channel} has no notes; using channel {best_ch}")
                events = best_events
                note_count = best_notes

        if note_count == 0:
            raise ValueError(
                f"{os.path.basename(in_abs)} produced only silence. "
                "Choose another channel or verify the TXT export."
            )
        songs.append(
            {
                "name": ident,
                "ident": ident,
                "source": os.path.basename(in_abs),
                "input": in_abs,
                "events": events,
                "row_ms": row_ms,
                "events_ch4": [],
            }
        )
        if args.export_4ch:
            ch_events: List[List[Tuple[float, int]]] = []
            for ch in channels_4ch[:4]:
                crow = parse_rows(in_abs, ch)
                if not crow:
                    ch_events.append([(0.0, row_ms)])
                else:
                    cev = rows_to_events(crow, row_ms=row_ms, hold_empty=not args.no_hold_empty)
                    if not cev:
                        cev = [(0.0, row_ms)]
                    ch_events.append(cev)
            songs[-1]["events_ch4"] = ch_events

    out_abs = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    settings = {
        "channel": args.channel,
        "row_ms": base_row_ms,
        "ft_timing": bool(args.ft_timing),
        "mix_4ch": bool(args.mix_4ch),
        "mix_channels": mix_channels,
        "export_4ch": bool(args.export_4ch),
        "channels_4ch": channels_4ch,
        "hold_empty": (not args.no_hold_empty),
        "bpm": args.bpm,
        "rows_per_beat": args.rows_per_beat,
    }
    header = build_header(songs, out_abs, settings)
    with open(out_abs, "w", encoding="ascii") as f:
        f.write(header)

    print(f"Generated: {out_abs}")
    for i, s in enumerate(songs):
        print(f"[{i}] {s['name']} <- {s['source']} events={len(s['events'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
