#!/usr/bin/env python3
import os
import struct


MAGIC = 0x4D415341
VERSION = 1

OP_DRAW_SPRITE = 1
OP_DRAW_SPRITE_XFORM = 5
OP_WAIT = 4
OP_END = 255


def build_script():
    data = bytearray()
    # Simple loop: draw sprite id 0 at two positions with rotation and scale.
    data += struct.pack("<BhhBhH", OP_DRAW_SPRITE_XFORM, 80, 100, 0, 150, 800)
    data += struct.pack("<BH", OP_WAIT, 250)
    data += struct.pack("<BhhBhH", OP_DRAW_SPRITE_XFORM, 200, 100, 0, -150, 1400)
    data += struct.pack("<BH", OP_WAIT, 250)
    data += struct.pack("<B", OP_END)
    return bytes(data)


def build_file(out_path):
    script = build_script()
    header_size = 44
    script_offset = header_size
    script_size = len(script)
    header = struct.pack(
        "<IHHIIIIIIIII",
        MAGIC,
        VERSION,
        0,
        script_offset,
        script_size,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    with open(out_path, "wb") as f:
        f.write(header)
        f.write(script)


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "game.masa")
    build_file(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
