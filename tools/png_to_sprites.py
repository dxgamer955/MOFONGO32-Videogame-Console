#!/usr/bin/env python3
"""
Convert one or more PNG files into a Sprites.h-compatible header.

Usage examples:
  python tools/png_to_sprites.py gfx/starman.png --out gfx/starman_sprite.h --name starman_sprites
  python tools/png_to_sprites.py gfx/a.png gfx/b.png --out gfx/my_sprites.h --name my_sprites --origin center
"""

import argparse
import json
import os
import re
import struct
import sys
import zlib
from typing import Dict, List, Optional, Tuple


PNG_SIG = b"\x89PNG\r\n\x1a\n"

# Canonical NES-like 64-color palette (RGB).
NES_PALETTE: List[Tuple[int, int, int]] = [
    (124, 124, 124), (0, 0, 252), (0, 0, 188), (68, 40, 188),
    (148, 0, 132), (168, 0, 32), (168, 16, 0), (136, 20, 0),
    (80, 48, 0), (0, 120, 0), (0, 104, 0), (0, 88, 0),
    (0, 64, 88), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (188, 188, 188), (0, 120, 248), (0, 88, 248), (104, 68, 252),
    (216, 0, 204), (228, 0, 88), (248, 56, 0), (228, 92, 16),
    (172, 124, 0), (0, 184, 0), (0, 168, 0), (0, 168, 68),
    (0, 136, 136), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (248, 248, 248), (60, 188, 252), (104, 136, 252), (152, 120, 248),
    (248, 120, 248), (248, 88, 152), (248, 120, 88), (252, 160, 68),
    (248, 184, 0), (184, 248, 24), (88, 216, 84), (88, 248, 152),
    (0, 232, 216), (120, 120, 120), (0, 0, 0), (0, 0, 0),
    (252, 252, 252), (164, 228, 252), (184, 184, 248), (216, 184, 248),
    (248, 184, 248), (248, 164, 192), (240, 208, 176), (252, 224, 168),
    (248, 216, 120), (216, 248, 120), (184, 248, 184), (184, 248, 216),
    (0, 252, 252), (248, 216, 248), (0, 0, 0), (0, 0, 0),
]


def paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def sanitize_ident(name: str) -> str:
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if not ident:
        ident = "sprites_data"
    if ident[0].isdigit():
        ident = "_" + ident
    return ident


def parse_png(path: str) -> Tuple[int, int, List[Tuple[int, int, int, int]]]:
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 8 or data[:8] != PNG_SIG:
        raise ValueError(f"{path}: invalid PNG signature")

    pos = 8
    width = height = 0
    bit_depth = color_type = None
    interlace = 0
    palette: Optional[List[Tuple[int, int, int]]] = None
    trns: Optional[bytes] = None
    idat_parts: List[bytes] = []

    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        ctype = data[pos:pos + 4]
        pos += 4
        chunk = data[pos:pos + length]
        pos += length
        _crc = data[pos:pos + 4]
        pos += 4

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif ctype == b"PLTE":
            if len(chunk) % 3 != 0:
                raise ValueError(f"{path}: invalid PLTE chunk length")
            palette = [
                (chunk[i], chunk[i + 1], chunk[i + 2])
                for i in range(0, len(chunk), 3)
            ]
        elif ctype == b"tRNS":
            trns = chunk
        elif ctype == b"IDAT":
            idat_parts.append(chunk)
        elif ctype == b"IEND":
            break

    if not width or not height or bit_depth is None or color_type is None:
        raise ValueError(f"{path}: missing IHDR")
    if interlace != 0:
        raise ValueError(f"{path}: interlaced PNG not supported")
    if bit_depth != 8:
        raise ValueError(f"{path}: only 8-bit PNG supported")

    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError(f"{path}: unsupported color type {color_type}")

    channels = channels_by_type[color_type]
    stride = width * channels
    raw = zlib.decompress(b"".join(idat_parts))
    expected = (stride + 1) * height
    if len(raw) != expected:
        raise ValueError(f"{path}: unexpected decompressed size {len(raw)} != {expected}")

    # Defilter
    scanlines = bytearray(height * stride)
    prev = bytearray(stride)
    src_pos = 0
    dst_pos = 0
    for _y in range(height):
        ftype = raw[src_pos]
        src_pos += 1
        cur = bytearray(raw[src_pos:src_pos + stride])
        src_pos += stride

        if ftype == 0:  # None
            pass
        elif ftype == 1:  # Sub
            for i in range(channels, stride):
                cur[i] = (cur[i] + cur[i - channels]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                left = cur[i - channels] if i >= channels else 0
                up = prev[i]
                cur[i] = (cur[i] + ((left + up) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                left = cur[i - channels] if i >= channels else 0
                up = prev[i]
                up_left = prev[i - channels] if i >= channels else 0
                cur[i] = (cur[i] + paeth_predictor(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"{path}: unsupported PNG filter type {ftype}")

        scanlines[dst_pos:dst_pos + stride] = cur
        dst_pos += stride
        prev = cur

    # Expand to RGBA
    out: List[Tuple[int, int, int, int]] = []
    p = 0
    if color_type == 0:  # Gray
        for _ in range(width * height):
            g = scanlines[p]
            p += 1
            out.append((g, g, g, 255))
    elif color_type == 2:  # RGB
        for _ in range(width * height):
            r, g, b = scanlines[p], scanlines[p + 1], scanlines[p + 2]
            p += 3
            out.append((r, g, b, 255))
    elif color_type == 3:  # Indexed
        if palette is None:
            raise ValueError(f"{path}: indexed PNG without PLTE")
        for _ in range(width * height):
            idx = scanlines[p]
            p += 1
            if idx >= len(palette):
                raise ValueError(f"{path}: palette index out of range")
            r, g, b = palette[idx]
            a = 255
            if trns is not None and idx < len(trns):
                a = trns[idx]
            out.append((r, g, b, a))
    elif color_type == 4:  # Gray + Alpha
        for _ in range(width * height):
            g, a = scanlines[p], scanlines[p + 1]
            p += 2
            out.append((g, g, g, a))
    elif color_type == 6:  # RGBA
        for _ in range(width * height):
            r, g, b, a = scanlines[p], scanlines[p + 1], scanlines[p + 2], scanlines[p + 3]
            p += 4
            out.append((r, g, b, a))

    return width, height, out


def rgba_to_gray_level(r: int, g: int, b: int, levels: int) -> int:
    # BT.709 luma
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    v = int(round((y / 255.0) * levels))
    if v < 0:
        return 0
    if v > levels:
        return levels
    return v


def clamp_u8(v: float) -> int:
    if v < 0.0:
        return 0
    if v > 255.0:
        return 255
    return int(v + 0.5)


def apply_tv_safe_rgba(
    w: int,
    h: int,
    rgba: List[Tuple[int, int, int, int]],
    desat: float = 0.25,
    blur_radius: int = 1,
) -> List[Tuple[int, int, int, int]]:
    # Desaturate first to reduce chroma artifacts on composite decoders.
    sat = 1.0 - desat
    if sat < 0.0:
        sat = 0.0
    if sat > 1.0:
        sat = 1.0

    out = list(rgba)
    if sat < 0.999:
        tmp: List[Tuple[int, int, int, int]] = []
        for r, g, b, a in out:
            y = 0.2126 * r + 0.7152 * g + 0.0722 * b
            nr = clamp_u8(y + (r - y) * sat)
            ng = clamp_u8(y + (g - y) * sat)
            nb = clamp_u8(y + (b - y) * sat)
            tmp.append((nr, ng, nb, a))
        out = tmp

    # Horizontal blur simulates composite chroma bleed and removes tiny color noise.
    if blur_radius > 0:
        radius = int(blur_radius)
        if radius > 4:
            radius = 4
        src = out
        dst = list(src)
        for y in range(h):
            row = y * w
            for x in range(w):
                sum_r = 0
                sum_g = 0
                sum_b = 0
                sum_a = 0
                n = 0
                for k in range(-radius, radius + 1):
                    xx = x + k
                    if xx < 0:
                        xx = 0
                    elif xx >= w:
                        xx = w - 1
                    r, g, b, a = src[row + xx]
                    sum_r += r
                    sum_g += g
                    sum_b += b
                    sum_a += a
                    n += 1
                dst[row + x] = (sum_r // n, sum_g // n, sum_b // n, sum_a // n)
        out = dst

    return out


def _extract_hex_values(text: str) -> List[int]:
    return [int(m.group(0), 16) for m in re.finditer(r"0x[0-9A-Fa-f]{8}", text)]


def load_atari_palette_rgb() -> List[Tuple[int, int, int]]:
    # Prefer the local marciot fork palette for exact runtime parity.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    video_out = os.path.join(repo_root, "ESP32CompositeColorVideo-master", "src", "video_out.h")
    if os.path.exists(video_out):
        with open(video_out, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r"atari_palette_rgb\[256\]\s*=\s*\{(.*?)\};", text, re.S)
        if m:
            vals = _extract_hex_values(m.group(1))
            if len(vals) >= 256:
                vals = vals[:256]
                out = []
                for v in vals:
                    r = (v >> 16) & 0xFF
                    g = (v >> 8) & 0xFF
                    b = v & 0xFF
                    out.append((r, g, b))
                return out

    # Fallback: 16x16 HSV-ish ramp (best effort if palette file is missing).
    out = []
    for hue in range(16):
        for lum in range(16):
            v = int(round((lum / 15.0) * 255))
            if hue == 0:
                out.append((v, v, v))
            else:
                # Small deterministic color wheel fallback.
                phase = (hue - 1) / 15.0
                r = int(max(0, min(255, v * (0.6 + 0.4 * abs((phase * 6.0 - 3.0) - 1.5) / 1.5))))
                g = int(max(0, min(255, v * (0.6 + 0.4 * abs(((phase + 0.333) * 6.0 - 3.0) - 1.5) / 1.5))))
                b = int(max(0, min(255, v * (0.6 + 0.4 * abs(((phase + 0.666) * 6.0 - 3.0) - 1.5) / 1.5))))
                out.append((r, g, b))
    return out


class AtariQuantizer:
    def __init__(self):
        self.palette = load_atari_palette_rgb()
        self.cache: Dict[Tuple[int, int, int], int] = {}

    def rgb_to_index(self, r: int, g: int, b: int, avoid_index: Optional[int] = None) -> int:
        # 5-bit key keeps cache small but effective.
        key = (r >> 3, g >> 3, b >> 3, -1 if avoid_index is None else int(avoid_index))
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        best_i = 0
        best_d = (1 << 30)
        for i, (pr, pg, pb) in enumerate(self.palette):
            if avoid_index is not None and i == avoid_index:
                continue
            dr = r - pr
            dg = g - pg
            db = b - pb
            # Weighted RGB distance (green contributes more perceptually).
            d = 3 * dr * dr + 6 * dg * dg + 2 * db * db
            if d < best_d:
                best_d = d
                best_i = i
        self.cache[key] = best_i
        return best_i


def nearest_palette_rgb(r: int, g: int, b: int, palette: List[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    best = palette[0]
    best_d = (1 << 30)
    for pr, pg, pb in palette:
        dr = r - pr
        dg = g - pg
        db = b - pb
        d = 3 * dr * dr + 6 * dg * dg + 2 * db * db
        if d < best_d:
            best_d = d
            best = (pr, pg, pb)
    return best


class NesToAtariQuantizer:
    def __init__(self):
        self.atari = AtariQuantizer()
        self.cache: Dict[Tuple[int, int, int, int], int] = {}

    def rgb_to_index(self, r: int, g: int, b: int, avoid_index: Optional[int] = None) -> int:
        key = (r >> 3, g >> 3, b >> 3, -1 if avoid_index is None else int(avoid_index))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        nr, ng, nb = nearest_palette_rgb(r, g, b, NES_PALETTE)
        idx = self.atari.rgb_to_index(nr, ng, nb, avoid_index=avoid_index)
        self.cache[key] = idx
        return idx


def wrap_u8(values: List[int], cols: int = 32) -> str:
    chunks = []
    for i in range(0, len(values), cols):
        row = ", ".join(str(v) for v in values[i:i + cols])
        chunks.append("  " + row + ",")
    return "\n".join(chunks)


def base_stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def parse_frame_names(pngs: List[str], names_arg: Optional[str]) -> List[str]:
    if names_arg is None or names_arg.strip() == "":
        return [sanitize_ident(base_stem(p)) for p in pngs]
    names = [sanitize_ident(x.strip()) for x in names_arg.split(",")]
    if len(names) != len(pngs):
        raise ValueError("--frame-names count must match number of input PNG files")
    return names


def auto_animations(frame_names: List[str]) -> Dict[str, List[int]]:
    groups: Dict[str, List[Tuple[int, int]]] = {}
    singles: Dict[str, int] = {}
    for i, name in enumerate(frame_names):
        m = re.match(r"^(.*?)(?:[_-]?)(\d+)$", name)
        if m:
            prefix = m.group(1) if m.group(1) else "anim"
            frame_no = int(m.group(2))
            groups.setdefault(prefix, []).append((frame_no, i))
        else:
            singles[name] = i

    out: Dict[str, List[int]] = {}
    for k, arr in groups.items():
        arr.sort(key=lambda x: x[0])
        out[k] = [idx for _, idx in arr]
    for k, idx in singles.items():
        out[k] = [idx]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PNG files to Sprites.h-compatible header.")
    parser.add_argument("pngs", nargs="+", help="Input PNG file(s).")
    parser.add_argument("--out", required=True, help="Output .h path.")
    parser.add_argument("--name", default="sprites", help="Base variable name in generated header.")
    parser.add_argument(
        "--origin",
        choices=["center", "topleft"],
        default="center",
        help="Origin point for each sprite.",
    )
    parser.add_argument("--origin-x", type=int, default=None, help="Override origin X for all sprites.")
    parser.add_argument("--origin-y", type=int, default=None, help="Override origin Y for all sprites.")
    parser.add_argument("--levels", type=int, default=54, help="Max grayscale value (default: 54).")
    parser.add_argument(
        "--color-mode",
        choices=["atari", "gray", "nes"],
        default="atari",
        help="Pixel encoding mode: atari(0..255), nes(quantize via NES palette), or gray(0..levels).",
    )
    parser.add_argument("--transparency", type=int, default=255, help="Transparency color value (default: 255).")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="Alpha <= threshold becomes transparent.")
    parser.add_argument("--tv-safe", action="store_true", help="Apply TV-safe preprocessing before quantization.")
    parser.add_argument("--tv-desat", type=float, default=0.25, help="TV-safe desaturation amount [0..1].")
    parser.add_argument("--tv-blur", type=int, default=1, help="TV-safe horizontal blur radius [0..4].")
    parser.add_argument("--frame-names", default=None, help="Comma-separated frame names matching PNG order.")
    parser.add_argument("--meta-json", default=None, help="Optional metadata json output path.")
    args = parser.parse_args()

    if args.levels < 1 or args.levels > 254:
        raise ValueError("--levels must be in [1, 254]")
    if args.transparency < 0 or args.transparency > 255:
        raise ValueError("--transparency must be in [0, 255]")
    if args.tv_desat < 0.0 or args.tv_desat > 1.0:
        raise ValueError("--tv-desat must be in [0.0, 1.0]")
    if args.tv_blur < 0 or args.tv_blur > 4:
        raise ValueError("--tv-blur must be in [0, 4]")
    if args.color_mode in ("atari", "nes") and args.transparency == 255:
        print("WARNING: transparency=255 uses one Atari color index as transparent.", file=sys.stderr)

    base = sanitize_ident(args.name)
    frame_names = parse_frame_names(args.pngs, args.frame_names)
    animations = auto_animations(frame_names)

    sprites_pixels: List[int] = []
    offsets: List[int] = [0]
    point_offsets: List[int] = [0]
    resolutions: List[Tuple[int, int]] = []
    points: List[Tuple[int, int]] = []
    quant_atari = AtariQuantizer() if args.color_mode == "atari" else None
    quant_nes = NesToAtariQuantizer() if args.color_mode == "nes" else None
    avoid_index = args.transparency if args.color_mode in ("atari", "nes") else None

    for path in args.pngs:
        w, h, rgba = parse_png(path)
        if args.tv_safe:
            rgba = apply_tv_safe_rgba(w, h, rgba, desat=args.tv_desat, blur_radius=args.tv_blur)
        resolutions.append((w, h))

        if args.origin_x is not None and args.origin_y is not None:
            ox, oy = args.origin_x, args.origin_y
        elif args.origin == "center":
            ox, oy = w // 2, h // 2
        else:
            ox, oy = 0, 0
        points.append((ox, oy))
        point_offsets.append(point_offsets[-1] + 1)

        for r, g, b, a in rgba:
            if a <= args.alpha_threshold:
                sprites_pixels.append(args.transparency)
            else:
                if args.color_mode == "atari":
                    sprites_pixels.append(quant_atari.rgb_to_index(r, g, b, avoid_index=avoid_index))  # type: ignore[union-attr]
                elif args.color_mode == "nes":
                    sprites_pixels.append(quant_nes.rgb_to_index(r, g, b, avoid_index=avoid_index))  # type: ignore[union-attr]
                else:
                    sprites_pixels.append(rgba_to_gray_level(r, g, b, args.levels))

        offsets.append(len(sprites_pixels))

    lines = []
    guard = sanitize_ident(os.path.basename(args.out)).upper().replace(".", "_") + "_"
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}")
    lines.append("")
    meta = {
        "type": "sprites_project_v1",
        "pngs": [os.path.abspath(p) for p in args.pngs],
        "out": os.path.abspath(args.out),
        "name": base,
        "origin": args.origin,
        "origin_x": args.origin_x,
        "origin_y": args.origin_y,
        "levels": args.levels,
        "color_mode": args.color_mode,
        "transparency": args.transparency,
        "alpha_threshold": args.alpha_threshold,
        "tv_safe": bool(args.tv_safe),
        "tv_desat": float(args.tv_desat),
        "tv_blur": int(args.tv_blur),
        "frame_names": frame_names,
        "animations": animations,
    }
    lines.append("// ASSET_TOOL: png_to_sprites.py")
    lines.append("// ASSET_META: " + json.dumps(meta, separators=(",", ":")))
    lines.append("")
    # When headers are generated into gfx/, this avoids case-insensitive
    # collision with gfx/sprites.h on Windows.
    lines.append('#include "../Sprites.h"')
    lines.append("")

    offs = ", ".join(str(v) for v in offsets)
    poffs = ", ".join(str(v) for v in point_offsets)
    res = ", ".join(f"{{{w}, {h}}}" for w, h in resolutions)
    pts = ", ".join(f"{{{x}, {y}}}" for x, y in points)

    lines.append(f"const int {base}Offsets[] = {{{offs}, }};")
    lines.append(f"const short {base}PointOffsets[] = {{{poffs}, }};")
    lines.append(f"const unsigned short {base}Res[][2] = {{{res}, }};")
    lines.append(f"const signed short {base}Points[][2] = {{{pts}, }};")
    frame_names_c = ", ".join(f"\"{n}\"" for n in frame_names)
    lines.append(f"const char *{base}FrameNames[] = {{{frame_names_c}, }};")
    lines.append(f"const int {base}FrameCount = {len(frame_names)};")
    lines.append(f"const unsigned char {base}Pixels[] = {{")
    lines.append(wrap_u8(sprites_pixels, cols=32))
    lines.append("};")
    lines.append(
        f"Sprites {base}({len(resolutions)}, {base}Pixels, {base}Offsets, "
        f"{base}Res, {base}Points, {base}PointOffsets, {args.transparency});"
    )
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

    print(f"Generated {args.out} with {len(resolutions)} sprite(s).")
    print(f"Metadata: {meta_out}")
    for i, (w, h) in enumerate(resolutions):
        print(f"  [{i}] {args.pngs[i]} -> {w}x{h}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
