#!/usr/bin/env python3
"""
Build songs.h by aggregating one or more melody header files.

Expected pattern per melody header:
  const float <prefix>Notes[];
  const unsigned short <prefix>DurMs[];
  const int <prefix>Len;

Example:
  python tools/melody_packager.py gfx/manny_melody.h gfx/dk_melody.h --out gfx/songs.h
"""

import argparse
import os
import re
import sys
from typing import List, Tuple


NOTES_RE = re.compile(r"\bconst\s+float\s+([A-Za-z_]\w*)Notes\s*\[\]")
DURS_RE = re.compile(r"\bconst\s+unsigned\s+short\s+([A-Za-z_]\w*)DurMs\s*\[\]")
LEN_RE = re.compile(r"\bconst\s+int\s+([A-Za-z_]\w*)Len\b")


def rel_include(from_dir: str, target_file: str) -> str:
    rel = os.path.relpath(os.path.abspath(target_file), os.path.abspath(from_dir))
    return rel.replace("\\", "/")


def parse_melody_symbols(path: str) -> Tuple[str, str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read()

    note_prefixes = set(NOTES_RE.findall(txt))
    dur_prefixes = set(DURS_RE.findall(txt))
    len_prefixes = set(LEN_RE.findall(txt))
    common = sorted(note_prefixes & dur_prefixes & len_prefixes)
    if not common:
        raise ValueError(f"{path}: no melody symbols found (<prefix>Notes/DurMs/Len)")

    prefix = common[0]
    song_name = prefix
    if song_name.endswith("_melody"):
        song_name = song_name[:-7]
    return prefix, song_name


def build_header(entries: List[Tuple[str, str, str]], out_path: str) -> str:
    out_dir = os.path.dirname(os.path.abspath(out_path))
    lines = []
    lines.append("#pragma once")
    lines.append("")

    for _, hdr_path, _ in entries:
        lines.append(f'#include "{rel_include(out_dir, hdr_path)}"')
    lines.append("")
    lines.append("struct SongDef")
    lines.append("{")
    lines.append("  const char *name;")
    lines.append("  const float *notes;")
    lines.append("  const unsigned short *durMs;")
    lines.append("  int len;")
    lines.append("};")
    lines.append("")
    lines.append("const SongDef songs[] = {")
    for prefix, _, song_name in entries:
        lines.append(f'  {{"{song_name}", {prefix}Notes, {prefix}DurMs, {prefix}Len}},')
    lines.append("};")
    lines.append("")
    lines.append("const int songsCount = sizeof(songs) / sizeof(songs[0]);")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate melody headers into songs.h")
    ap.add_argument("headers", nargs="+", help="Input melody header files")
    ap.add_argument("--out", required=True, help="Output songs.h")
    args = ap.parse_args()

    entries = []
    for h in args.headers:
        h_abs = os.path.abspath(h)
        if not os.path.isfile(h_abs):
            raise ValueError(f"Missing file: {h}")
        prefix, song_name = parse_melody_symbols(h_abs)
        entries.append((prefix, h_abs, song_name))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    header = build_header(entries, args.out)
    with open(args.out, "w", encoding="ascii") as f:
        f.write(header)

    print(f"Generated: {os.path.abspath(args.out)}")
    for i, (prefix, hdr, song_name) in enumerate(entries):
        print(f"  [{i}] {song_name} <- {os.path.basename(hdr)} ({prefix})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
