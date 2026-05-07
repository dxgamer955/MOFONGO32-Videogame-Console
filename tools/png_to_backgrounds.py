#!/usr/bin/env python3
"""
Convert one or more 320x200 PNG files into a backgrounds header.

Usage:
  python tools/png_to_backgrounds.py gfx/bg1.png gfx/bg2.png --out gfx/backgrounds.h --name backgrounds
"""

import argparse
import json
import os
import sys
from typing import List

from png_to_sprites import (
    AtariQuantizer,
    NesToAtariQuantizer,
    apply_tv_safe_rgba,
    parse_png,
    rgba_to_gray_level,
    sanitize_ident,
    wrap_u8,
)


REQUIRED_W = 320
REQUIRED_H = 200
TRANSPARENT_RGB = (255, 0, 255)


def transparent_index_for_palette(palette):
    tr, tg, tb = TRANSPARENT_RGB
    best_i = 0
    best_d = (1 << 30)
    for i, (r, g, b) in enumerate(palette):
        dr = tr - r
        dg = tg - g
        db = tb - b
        d = 3 * dr * dr + 6 * dg * dg + 2 * db * db
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert 320x200 PNG files to backgrounds header.")
    parser.add_argument("pngs", nargs="+", help="Input PNG file(s), each must be 320x200.")
    parser.add_argument("--out", required=True, help="Output .h path.")
    parser.add_argument("--name", default="backgrounds", help="Base variable name in generated header.")
    parser.add_argument("--levels", type=int, default=54, help="Max grayscale value (default: 54).")
    parser.add_argument(
        "--color-mode",
        choices=["atari", "gray", "nes"],
        default="atari",
        help="Pixel encoding mode: atari(0..255), nes(quantize via NES palette), or gray(0..levels).",
    )
    parser.add_argument("--tv-safe", action="store_true", help="Apply TV-safe preprocessing before quantization.")
    parser.add_argument("--tv-desat", type=float, default=0.25, help="TV-safe desaturation amount [0..1].")
    parser.add_argument("--tv-blur", type=int, default=1, help="TV-safe horizontal blur radius [0..4].")
    parser.add_argument("--meta-json", default=None, help="Optional metadata json output path.")
    args = parser.parse_args()

    if args.levels < 1 or args.levels > 255:
        raise ValueError("--levels must be in [1, 255]")
    if args.tv_desat < 0.0 or args.tv_desat > 1.0:
        raise ValueError("--tv-desat must be in [0.0, 1.0]")
    if args.tv_blur < 0 or args.tv_blur > 4:
        raise ValueError("--tv-blur must be in [0, 4]")

    base = sanitize_ident(args.name)
    bg_pixels: List[int] = []
    offsets: List[int] = [0]
    quant_atari = AtariQuantizer() if args.color_mode == "atari" else None
    quant_nes = NesToAtariQuantizer() if args.color_mode == "nes" else None
    transparent_index = None
    if quant_atari is not None:
        transparent_index = transparent_index_for_palette(quant_atari.palette)
    elif quant_nes is not None:
        transparent_index = transparent_index_for_palette(quant_nes.atari.palette)

    for path in args.pngs:
        w, h, rgba = parse_png(path)
        if w != REQUIRED_W or h != REQUIRED_H:
            raise ValueError(
                f"{path}: invalid size {w}x{h}. Expected {REQUIRED_W}x{REQUIRED_H}."
            )
        if args.tv_safe:
            rgba = apply_tv_safe_rgba(w, h, rgba, desat=args.tv_desat, blur_radius=args.tv_blur)
        for r, g, b, _a in rgba:
            if (r, g, b) == TRANSPARENT_RGB and transparent_index is not None:
                bg_pixels.append(transparent_index)
                continue
            if args.color_mode == "atari":
                bg_pixels.append(quant_atari.rgb_to_index(r, g, b, avoid_index=transparent_index))  # type: ignore[union-attr]
            elif args.color_mode == "nes":
                bg_pixels.append(quant_nes.rgb_to_index(r, g, b, avoid_index=transparent_index))  # type: ignore[union-attr]
            else:
                bg_pixels.append(rgba_to_gray_level(r, g, b, args.levels))
        offsets.append(len(bg_pixels))

    lines = []
    guard = sanitize_ident(os.path.basename(args.out)).upper().replace(".", "_") + "_"
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}")
    lines.append("")
    meta = {
        "type": "backgrounds_project_v1",
        "pngs": [os.path.abspath(p) for p in args.pngs],
        "out": os.path.abspath(args.out),
        "name": base,
        "levels": args.levels,
        "color_mode": args.color_mode,
        "tv_safe": bool(args.tv_safe),
        "tv_desat": float(args.tv_desat),
        "tv_blur": int(args.tv_blur),
        "width": REQUIRED_W,
        "height": REQUIRED_H,
        "transparent_index": transparent_index,
    }
    lines.append("// ASSET_TOOL: png_to_backgrounds.py")
    lines.append("// ASSET_META: " + json.dumps(meta, separators=(",", ":")))
    lines.append("")
    lines.append(f"const int {base}Width = {REQUIRED_W};")
    lines.append(f"const int {base}Height = {REQUIRED_H};")
    lines.append(f"const int {base}Offsets[] = {{{', '.join(str(v) for v in offsets)}, }};")
    lines.append(f"const int {base}Count = {len(args.pngs)};")
    if transparent_index is not None:
        lines.append(f"const int {base}TransparentIndex = {transparent_index};")
    lines.append(f"const unsigned char {base}Pixels[] = {{")
    lines.append(wrap_u8(bg_pixels, cols=32))
    lines.append("};")
    lines.append("")
    lines.append(f"#endif // {guard}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="ascii") as f:
        f.write("\n".join(lines))

    meta_out = args.meta_json
    if not meta_out:
        root, _ext = os.path.splitext(os.path.abspath(args.out))
        meta_out = root + ".json"
    os.makedirs(os.path.dirname(os.path.abspath(meta_out)), exist_ok=True)
    with open(meta_out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Generated {args.out} with {len(args.pngs)} background(s).")
    print(f"Metadata: {meta_out}")
    print(f"Resolution enforced: {REQUIRED_W}x{REQUIRED_H}")
    for i, p in enumerate(args.pngs):
        print(f"  [{i}] {p}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
