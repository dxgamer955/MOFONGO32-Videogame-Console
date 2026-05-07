import struct
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inspect_masa.py <path.masa>")
        return 1
    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 44:
        print("File too small")
        return 1
    header = struct.unpack("<IHHIIIIIIIII", data[:44])
    script_off = header[3]
    script_size = header[4]
    script = data[script_off:script_off + script_size]

    spawn_ops = []
    set_obj_ops = []
    input_bind_ops = []
    for i in range(0, len(script) - 8):
        if script[i] == 79:  # OP_SIGNAL_SPAWN_BULLET
            slot = script[i + 1]
            src = script[i + 2]
            bullet = script[i + 3]
            speed10 = struct.unpack("<h", script[i + 4:i + 6])[0]
            offset = struct.unpack("<h", script[i + 6:i + 8])[0]
            frame = script[i + 8]
            spawn_ops.append((slot, src, bullet, speed10, offset, frame))
        if script[i] == 6 and i + 5 < len(script):  # OP_SET_OBJ
            obj = script[i + 1]
            x = struct.unpack("<h", script[i + 2:i + 4])[0]
            y = struct.unpack("<h", script[i + 4:i + 6])[0]
            spr = script[i + 6] if i + 6 < len(script) else None
            set_obj_ops.append((obj, x, y, spr))
        if script[i] == 76 and i + 3 < len(script):  # OP_INPUT_BIND
            slot = script[i + 1]
            ev = script[i + 2]
            btn = script[i + 3]
            input_bind_ops.append((slot, ev, btn))

    print("spawn_bullet ops:", spawn_ops)
    print("set_obj ops:", set_obj_ops[:30], "count=", len(set_obj_ops))
    print("input_bind ops:", input_bind_ops)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
