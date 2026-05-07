#!/usr/bin/env python3
"""Analizador visual de paquetes .masa.

Sirve para revisar tamano de secciones, impacto aproximado en RAM y limites del runtime
antes de compilar/flashear en el ESP32.
"""

import os
import struct
import re
import tkinter as tk
from tkinter import filedialog, ttk, messagebox


HEADER_FMT = "<IHHIIIIIIIII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MASA_MAGIC = 0x4D415341  # "MASA"

PALETTE = {
    "bg": "#384F3E",
    "panel": "#5B8065",
    "doc_panel": "#1E2421",
    "accent": "#8CAD92",
    "text": "#FFFFFF",
    "editor_bg": "#1E2421",
    "editor_text": "#E6F2EA",
    "editor_comment": "#6D7A72",
    "editor_masa": "#FFD166",
    "editor_kw": "#80C7FF",
}

IMPACT_PER_UNIT = {
    "kMaxObjects": 99,
    "kMaxSignalActions": 31,
    "kMaxTextSlots": 39,
    "kMaxTextLen": 7,
    "kMaxShapeSlots": 15,
    "kMaxSignals": 7,
    "kMaxTextBoxLen": 2,
    "kMaxColliders": 3,
    "kMaxAlarms": 12,
    "kMaxInputBinds": 4,
    "kMaxChoiceLen": 2,
    "kMaxChoiceItems": 4,
    "kMaxChoiceSlots": 15,
    "kMaxTextBoxes": 12,
}


OP_NAMES = {
    0: "NOP",
    1: "DRAW_SPRITE",
    2: "MOVE_OBJECT",
    3: "PLAY_SOUND",
    4: "WAIT",
    5: "DRAW_SPRITE_XFORM",
    6: "SET_OBJECT",
    7: "SET_VEL",
    8: "SET_BOUNDS",
    9: "SET_ROT_SPEED",
    10: "SET_SCALE_PULSE",
    11: "SET_ANIM",
    12: "SET_INPUT",
    13: "TEXT_SET",
    14: "TEXT_CLEAR",
    15: "SHAPE_SET",
    16: "SHAPE_CLEAR",
    17: "SPAWN_OBJECT",
    18: "DESTROY_OBJECT",
    19: "SET_HITBOX",
    20: "COLLIDE_SIGNAL",
    21: "SIGNAL_DESTROY",
    22: "SIGNAL_SPAWN",
    23: "SIGNAL_SOUND",
    24: "TEXTBOX_SET",
    25: "TEXTBOX_CLEAR",
    26: "CHOICES_SET",
    27: "CHOICES_CLEAR",
    28: "SIGNAL_ROOM_NEXT",
    29: "SIGNAL_STOP",
    30: "SIGNAL_TEXTBOX",
    31: "SIGNAL_CHOICES",
    32: "SIGNAL_TEXTBOX_CLEAR",
    33: "SIGNAL_CHOICES_CLEAR",
    34: "SIGNAL_SET_INPUT",
    35: "INPUT_BIND",
    36: "BG_SCROLL_X",
    37: "BG_SCROLL_Y",
    38: "ALARM_START",
    39: "ALARM_STOP",
    40: "ALARM_SIGNAL",
    41: "MUSIC_SIGNAL",
    42: "PLAY_MUSIC",
    43: "STOP_MUSIC",
    44: "PAUSE_MUSIC",
    45: "SONG_LOOP",
    46: "HUD_SET",
    47: "HUD_ADD",
    48: "HUD_DRAW",
    49: "VAR_SET",
    50: "VAR_ADD",
    51: "VAR_TEXT",
    52: "VARF_SET",
    53: "VARF_ADD",
    54: "VARF_TEXT",
    55: "IF_EQ",
    56: "IF_GT",
    57: "IF_LT",
    58: "IF_EQF",
    59: "IF_GTF",
    60: "IF_LTF",
    61: "VAR_CLAMP",
    62: "VARF_CLAMP",
    63: "VAR_RAND",
    64: "VARF_LERP",
    65: "VAR_MIN",
    66: "VAR_MAX",
    67: "VARF_MIN",
    68: "VARF_MAX",
    69: "VARF_SIN",
    70: "VARF_COS",
    71: "STR_SET",
    72: "STR_TEXT",
    73: "SWITCH",
    74: "SIGNAL_ROOM_GOTO",
    75: "SET_ACCEL",
    76: "SET_ROTATE",
    77: "SET_THRUST",
    78: "SET_WRAP",
    79: "SIGNAL_SPAWN_BULLET",
    80: "SET_SPRITE",
    81: "SET_POS_X",
    82: "SET_POS_Y",
    83: "ALARM_START_OBJ",
    84: "ALARM_STOP_OBJ",
    85: "ALARM_SIGNAL_OBJ",
    86: "SET_ACTION_OWNER",
    87: "SET_NO_WRAP",
    88: "BEEP",
    89: "SIGNAL_BEEP",
    90: "SET_BOUNCE",
    91: "SET_VEL_RANDOM",
    92: "SIGNAL_HUD_ADD",
    93: "SET_GAME_OVER_UI",
    94: "SIGNAL_TEXT_SET",
    95: "SIGNAL_TEXT_CLEAR",
    96: "HUD_STYLE",
    97: "SIGNAL_TEXT_SET_EX",
    98: "SET_HITBOX_EX",
    99: "BEEP_WAVE",
    100: "SIGNAL_BEEP_WAVE",
    255: "END",
}


def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def parse_header(data: bytes):
    if len(data) < HEADER_SIZE:
        raise ValueError("File too small for MASA header")
    fields = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    out = {
        "magic": fields[0],
        "version": fields[1],
        "flags": fields[2],
        "scriptOffset": fields[3],
        "scriptSize": fields[4],
        "spritesOffset": fields[5],
        "spritesSize": fields[6],
        "tilemapOffset": fields[7],
        "tilemapSize": fields[8],
        "entryPoint": fields[9],
        "bgIndex": fields[10],
        "songHash": fields[11],
    }
    return out


def section_rows(file_size: int, h: dict):
    rows = []
    rows.append(("Header", 0, HEADER_SIZE))
    rows.append(("Script", int(h["scriptOffset"]), int(h["scriptSize"])))
    rows.append(("Sprites", int(h["spritesOffset"]), int(h["spritesSize"])))
    rows.append(("Tilemap", int(h["tilemapOffset"]), int(h["tilemapSize"])))

    # Normalize, add gaps and tail.
    real = []
    for name, off, size in rows:
        if size <= 0:
            continue
        off = max(0, off)
        end = min(file_size, off + size)
        if end > off:
            real.append((name, off, end - off))
    real.sort(key=lambda x: x[1])

    out = []
    cur = 0
    for name, off, size in real:
        if off > cur:
            out.append(("Gap/Unused", cur, off - cur))
        out.append((name, off, size))
        cur = max(cur, off + size)
    if cur < file_size:
        out.append(("Tail/Rooms/Extra", cur, file_size - cur))
    return out


def opcode_histogram(script_bytes: bytes):
    hist = {}
    for b in script_bytes:
        hist[b] = hist.get(b, 0) + 1
    rows = []
    for op, count in sorted(hist.items(), key=lambda kv: kv[1], reverse=True):
        rows.append((op, OP_NAMES.get(op, f"OP_{op}"), count))
    return rows


def _read_runtime_const(path: str, name: str, default: int) -> int:
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return default
    m = re.search(rf"\b{name}\b\s*=\s*(\d+)\s*;", txt)
    if not m:
        return default
    try:
        return int(m.group(1))
    except Exception:
        return default


def load_runtime_limits(base_dir: str):
    rt = os.path.join(base_dir, "MasaRuntime.h")
    ld = os.path.join(base_dir, "MasaLoader.h")
    return {
        "kMaxObjects": _read_runtime_const(rt, "kMaxObjects", 30),
        "kMaxCommands": _read_runtime_const(rt, "kMaxCommands", 24),
        "kMaxTextSlots": _read_runtime_const(rt, "kMaxTextSlots", 5),
        "kMaxTextLen": _read_runtime_const(rt, "kMaxTextLen", 24),
        "kMaxShapeSlots": _read_runtime_const(rt, "kMaxShapeSlots", 8),
        "kMaxSignals": _read_runtime_const(rt, "kMaxSignals", 16),
        "kMaxColliders": _read_runtime_const(rt, "kMaxColliders", 28),
        "kMaxSignalActions": _read_runtime_const(rt, "kMaxSignalActions", 30),
        "kMaxTextBoxes": _read_runtime_const(rt, "kMaxTextBoxes", 1),
        "kMaxTextBoxLen": _read_runtime_const(rt, "kMaxTextBoxLen", 40),
        "kMaxChoiceSlots": _read_runtime_const(rt, "kMaxChoiceSlots", 1),
        "kMaxChoiceItems": _read_runtime_const(rt, "kMaxChoiceItems", 4),
        "kMaxChoiceLen": _read_runtime_const(rt, "kMaxChoiceLen", 10),
        "kMaxInputBinds": _read_runtime_const(rt, "kMaxInputBinds", 14),
        "kMaxAlarms": _read_runtime_const(rt, "kMaxAlarms", 6),
        "kMaxScriptSize": _read_runtime_const(ld, "kMaxScriptSize", 8192),
        "kMaxRoomsSize": _read_runtime_const(ld, "kMaxRoomsSize", 4096),
    }


def estimate_runtime_ram_bytes(lim: dict):
    o = int(lim["kMaxObjects"])
    c = int(lim["kMaxCommands"])
    ts = int(lim["kMaxTextSlots"])
    tl = int(lim["kMaxTextLen"])
    sh = int(lim["kMaxShapeSlots"])
    sg = int(lim["kMaxSignals"])
    co = int(lim["kMaxColliders"])
    sa = int(lim["kMaxSignalActions"])
    tb = int(lim["kMaxTextBoxes"])
    tbl = int(lim["kMaxTextBoxLen"])
    cs = int(lim["kMaxChoiceSlots"])
    ci = int(lim["kMaxChoiceItems"])
    cl = int(lim["kMaxChoiceLen"])
    ib = int(lim["kMaxInputBinds"])
    al = int(lim["kMaxAlarms"])
    script_buf = int(lim["kMaxScriptSize"])
    rooms_buf = int(lim["kMaxRoomsSize"])

    vars_per_obj = 12
    globals_count = 32

    per_obj_runtime = (
        11 * 2 +      # int16 object arrays
        6 * 4 +       # float object arrays
        13 * 1 +      # uint8/bool/int8 object arrays
        4 * 2 +       # uint16 object arrays
        1 * 4 +       # uint32 object arrays
        16 +          # anim frames per object
        vars_per_obj * 4 +                     # int vars per object
        vars_per_obj * 4 +                     # float vars per object
        vars_per_obj * (tl + 1) +              # string vars per object
        al * (1 + 1 + 2 + 4 + 1 + 2 + 1)       # alarms per object
    )
    object_block = o * per_obj_runtime

    text_block = ts * (1 + 2 + 2 + 1 + 1 + (tl + 1) + 1)
    shape_block = sh * (1 + 1 + 2 + 2 + 2 + 2 + 2 + 2 + 1)
    textbox_block = tb * (1 + 2 + 2 + 2 + 2 + 1 + 1 + (tbl + 1))
    choice_block = cs * (1 + 2 + 2 + 1 + 1 + 1 + 1 + ci + (ci * (cl + 1)) + 1 + 1 + 1 + 1)
    hitbox_block = o * 4
    collider_block = (co * 3) + 1
    signal_block = sg * 7
    action_per = 12 + (6 * 2) + (2 * 2) + ci + (tbl + 1) + (ci * (cl + 1))
    action_block = sa * action_per
    input_block = (ib * 4) + 3
    hud_text_block = (tbl + 1) + 3 * (tl + 1)
    vars_global_block = (globals_count * 4) + (globals_count * 4) + (globals_count * (tl + 1))
    var_text_block = 3 * (ts * (1 + 2 + 2 + 1 + 1 + 1 + 1 + (tl + 1)))
    render_cmd_size = 11
    text_cmd_size = tl + 6
    shape_cmd_size = 14
    queue_block = (c * render_cmd_size) + 1 + (ts * text_cmd_size) + 1 + (sh * shape_cmd_size) + 1 + 2 + 2
    packet_block = 16 + (c * render_cmd_size) + 1 + (ts * text_cmd_size) + 1 + (sh * shape_cmd_size)
    runtime_obj_block = o * 6
    loader_block = script_buf + rooms_buf
    dual_frame_block = 202
    misc_scalars = 512

    breakdown = [
        ("Runtime object/state arrays", object_block),
        ("Signal action arrays", action_block),
        ("UI/text/shape arrays", text_block + shape_block + textbox_block + choice_block),
        ("Vars + var text arrays", vars_global_block + var_text_block),
        ("Signals/colliders/input", signal_block + collider_block + input_block + hitbox_block),
        ("Runtime command queue", queue_block),
        ("SPI packet buffer", packet_block),
        ("Runtime objects struct", runtime_obj_block),
        ("MASA script/rooms buffers", loader_block),
        ("DualESP frame state", dual_frame_block),
        ("Misc runtime scalars", misc_scalars),
        ("HUD/GameOver strings", hud_text_block),
    ]
    total = sum(v for _k, v in breakdown)
    return total, breakdown


def parse_esp32_map_ram(map_text: str):
    region_total = None
    used = 0
    sec_used = 0
    found_sections = False
    overflow = 0

    # Region size from Memory Configuration table.
    m_region = re.search(
        r"(?m)^\s*dram0_0_seg\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)\b",
        map_text
    )
    if m_region:
        region_total = int(m_region.group(1), 16)

    # Exact sections in DRAM.
    sec_re = re.compile(
        r"(?m)^\s*(\.dram0\.(?:data|bss|noinit))\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)\b"
    )
    for _name, hex_size in sec_re.findall(map_text):
        sz = int(hex_size, 16)
        sec_used += sz
        found_sections = True

    if found_sections:
        used = sec_used

    # Overflow reported by linker.
    m_over = re.search(r"region `dram0_0_seg' overflowed by (\d+) bytes", map_text)
    if m_over:
        overflow = int(m_over.group(1))
        if region_total is not None:
            used = max(used, region_total + overflow)

    return {
        "region_total": region_total,
        "used": used if used > 0 else None,
        "overflow": overflow,
        "has_sections": found_sections,
    }


class MasaSizeViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MASA Size Viewer")
        self.geometry("1480x760")
        self.configure(bg=PALETTE["bg"])
        self._init_ttk_theme()

        self.file_data = None
        self.sections = []
        self.runtime_limits = load_runtime_limits(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        self.runtime_est_bytes, self.runtime_breakdown = estimate_runtime_ram_bytes(self.runtime_limits)
        self.map_info = None

        top = tk.Frame(self, bg=PALETTE["bg"])
        top.pack(fill="x", padx=10, pady=10)

        tk.Button(top, text="Load .masa", command=self.load_file, bg=PALETTE["panel"], fg=PALETTE["text"],
                  activebackground=PALETTE["accent"], activeforeground=PALETTE["text"]).pack(side="left")
        tk.Button(top, text="Load .map", command=self.load_map, bg=PALETTE["panel"], fg=PALETTE["text"],
                  activebackground=PALETTE["accent"], activeforeground=PALETTE["text"]).pack(side="left", padx=(8, 0))
        tk.Button(top, text="Calibrate from .map", command=self.calibrate_from_map, bg=PALETTE["panel"], fg=PALETTE["text"],
                  activebackground=PALETTE["accent"], activeforeground=PALETTE["text"]).pack(side="left", padx=(8, 0))
        tk.Label(top, text="ROM Capacity (KB):", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(side="left", padx=(12, 6))
        self.cap_var = tk.StringVar(value="1024")
        tk.Entry(top, textvariable=self.cap_var, width=8, bg=PALETTE["editor_bg"], fg=PALETTE["editor_text"],
                 insertbackground=PALETTE["editor_text"]).pack(side="left")
        tk.Label(top, text="RAM Capacity (KB):", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(side="left", padx=(12, 6))
        self.ram_cap_var = tk.StringVar(value="121.66")
        tk.Entry(top, textvariable=self.ram_cap_var, width=8, bg=PALETTE["editor_bg"], fg=PALETTE["editor_text"],
                 insertbackground=PALETTE["editor_text"]).pack(side="left")
        tk.Label(top, text="Other App BSS (KB):", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(side="left", padx=(12, 6))
        self.ram_overhead_var = tk.StringVar(value="64")
        tk.Entry(top, textvariable=self.ram_overhead_var, width=8, bg=PALETTE["editor_bg"], fg=PALETTE["editor_text"],
                 insertbackground=PALETTE["editor_text"]).pack(side="left")
        tk.Label(top, text="Estimate Mode:", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(side="left", padx=(12, 6))
        self.est_mode_var = tk.StringVar(value="Estimate")
        self.est_mode_combo = ttk.Combobox(
            top,
            textvariable=self.est_mode_var,
            state="readonly",
            width=13,
            values=["Estimate", "Conservative", "Worst-case"]
        )
        self.est_mode_combo.pack(side="left")
        self.est_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.redraw_chip())
        tk.Button(top, text="Recalc", command=self.redraw_chip, bg=PALETTE["accent"], fg=PALETTE["text"],
                  activebackground=PALETTE["panel"], activeforeground=PALETTE["text"]).pack(side="left", padx=6)

        self.info_var = tk.StringVar(value="No file loaded.")
        tk.Label(self, textvariable=self.info_var, bg=PALETTE["bg"], fg=PALETTE["editor_text"], anchor="w").pack(fill="x", padx=10)

        mid = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", bg=PALETTE["bg"])
        mid.pack(fill="both", expand=True, padx=10, pady=10)

        left = tk.Frame(mid, bg=PALETTE["bg"])
        right = tk.Frame(mid, bg=PALETTE["bg"])
        mid.add(left, stretch="always")
        mid.add(right, stretch="always")

        # Left side uses a vertical splitter so both left panels can be resized.
        left_split = tk.PanedWindow(left, orient="vertical", sashrelief="raised", bg=PALETTE["bg"])
        left_split.pack(fill="both", expand=True)

        sec_frame = tk.Frame(left, bg=PALETTE["bg"])
        op_frame = tk.Frame(left, bg=PALETTE["bg"])
        left_split.add(sec_frame, stretch="always")
        left_split.add(op_frame, stretch="always")

        tk.Label(sec_frame, text="Section Table", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w")
        self.tbl = ttk.Treeview(sec_frame, columns=("section", "offset", "size", "pct"), show="headings", height=16)
        self.tbl.heading("section", text="Section")
        self.tbl.heading("offset", text="Offset")
        self.tbl.heading("size", text="Size")
        self.tbl.heading("pct", text="%")
        self.tbl.column("section", width=180, anchor="w")
        self.tbl.column("offset", width=120, anchor="e")
        self.tbl.column("size", width=120, anchor="e")
        self.tbl.column("pct", width=80, anchor="e")
        self.tbl.pack(fill="both", expand=True, pady=6)

        tk.Label(op_frame, text="Top Opcode Bytes In Script", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w")
        self.op_tbl = ttk.Treeview(op_frame, columns=("op", "name", "count"), show="headings", height=10)
        self.op_tbl.heading("op", text="Op")
        self.op_tbl.heading("name", text="Name")
        self.op_tbl.heading("count", text="Count")
        self.op_tbl.column("op", width=60, anchor="e")
        self.op_tbl.column("name", width=220, anchor="w")
        self.op_tbl.column("count", width=80, anchor="e")
        self.op_tbl.pack(fill="both", expand=True, pady=6)

        tk.Label(right, text="ROM Chip Usage", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w")
        top_right = tk.Frame(right, bg=PALETTE["bg"])
        top_right.pack(fill="x", expand=False, pady=8)
        self.canvas = tk.Canvas(top_right, width=820, height=320, bg=PALETTE["doc_panel"], highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        impact_frame = tk.Frame(top_right, bg=PALETTE["bg"])
        impact_frame.pack(side="left", fill="y", padx=(8, 0))
        tk.Label(impact_frame, text="Runtime Impact Table", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w")
        self.impact_tbl = ttk.Treeview(
            impact_frame,
            columns=("const", "per", "val", "total"),
            show="headings",
            height=8
        )
        self.impact_tbl.heading("const", text="Constants")
        self.impact_tbl.heading("per", text="+1 units \u2248 bytes")
        self.impact_tbl.heading("val", text="Actual value")
        self.impact_tbl.heading("total", text="Total aprox Impact")
        self.impact_tbl.column("const", width=150, anchor="w")
        self.impact_tbl.column("per", width=110, anchor="e")
        self.impact_tbl.column("val", width=90, anchor="e")
        self.impact_tbl.column("total", width=130, anchor="e")
        self.impact_tbl.pack(fill="y", expand=False)

        tk.Label(impact_frame, text="MASA Import Summary", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w", pady=(8, 0))
        self.masa_tbl = ttk.Treeview(
            impact_frame,
            columns=("item", "value"),
            show="headings",
            height=8
        )
        self.masa_tbl.heading("item", text="Field")
        self.masa_tbl.heading("value", text="Value")
        self.masa_tbl.column("item", width=180, anchor="w")
        self.masa_tbl.column("value", width=300, anchor="w")
        self.masa_tbl.pack(fill="y", expand=False)

        tk.Label(right, text="Section Bars", bg=PALETTE["bg"], fg=PALETTE["text"]).pack(anchor="w")
        self.bars = tk.Canvas(right, width=420, height=280, bg=PALETTE["doc_panel"], highlightthickness=0)
        self.bars.pack(fill="both", expand=True, pady=8)
        self.redraw_impact_table()

    def _init_ttk_theme(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Treeview",
            background=PALETTE["panel"],
            fieldbackground=PALETTE["panel"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["accent"],
            rowheight=22,
        )
        style.configure(
            "Treeview.Heading",
            background=PALETTE["accent"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["panel"],
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", PALETTE["editor_kw"])],
            foreground=[("selected", PALETTE["doc_panel"])],
        )

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("MASA files", "*.masa"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = open(path, "rb").read()
            h = parse_header(data)
            if h["magic"] != MASA_MAGIC:
                messagebox.showwarning("Warning", "Magic is not MASA. File may be invalid.")
            self.file_data = {
                "path": path,
                "name": os.path.basename(path),
                "size": len(data),
                "header": h,
                "sections": section_rows(len(data), h),
                "script": data[h["scriptOffset"]:h["scriptOffset"] + h["scriptSize"]],
            }
            self.render()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")

    def load_map(self):
        path = filedialog.askopenfilename(filetypes=[("Map files", "*.map"), ("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            txt = open(path, "r", encoding="utf-8", errors="ignore").read()
            mi = parse_esp32_map_ram(txt)
            mi["path"] = path
            self.map_info = mi
            if mi.get("region_total") is not None:
                kb = float(mi["region_total"]) / 1024.0
                self.ram_cap_var.set(f"{kb:.2f}")
            self.redraw_chip()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load map:\n{e}")

    def calibrate_from_map(self):
        if not self.map_info or self.map_info.get("used") is None:
            messagebox.showinfo("Calibrate", "Load a .map first to calibrate.")
            return
        used = int(self.map_info.get("used", 0))
        base = int(self.runtime_est_bytes)

        # Calibrate to Estimate mode baseline (no conservative extras).
        self.est_mode_var.set("Estimate")
        other_b = max(0, used - base)
        other_kb = other_b / 1024.0
        self.ram_overhead_var.set(f"{other_kb:.2f}")

        # If map has real dram capacity, sync RAM capacity too.
        if self.map_info.get("region_total") is not None:
            cap_kb = float(self.map_info["region_total"]) / 1024.0
            self.ram_cap_var.set(f"{cap_kb:.2f}")

        self.redraw_chip()
        messagebox.showinfo(
            "Calibrate",
            f"Calibrated using loaded .map:\n"
            f"Estimate mode set.\n"
            f"Other App BSS = {other_kb:.2f} KB"
        )

    def render(self):
        if not self.file_data:
            return
        fd = self.file_data
        h = fd["header"]
        self.info_var.set(
            f"{fd['name']} | Size: {fmt_bytes(fd['size'])} | "
            f"Version: {h['version']} | Entry: {h['entryPoint']} | "
            f"BG: {h['bgIndex']} | SongHash: {h['songHash']}"
        )

        for tv in (self.tbl, self.op_tbl):
            for iid in tv.get_children():
                tv.delete(iid)

        total = max(1, int(fd["size"]))
        for name, off, size in fd["sections"]:
            pct = (size * 100.0) / total
            self.tbl.insert("", "end", values=(name, f"0x{off:08X}", fmt_bytes(size), f"{pct:.2f}%"))

        for op, name, count in opcode_histogram(fd["script"])[:16]:
            self.op_tbl.insert("", "end", values=(op, name, count))

        self.redraw_chip()
        self.redraw_bars()
        self.redraw_impact_table()
        self.redraw_masa_table()

    def redraw_impact_table(self):
        if not hasattr(self, "impact_tbl"):
            return
        for iid in self.impact_tbl.get_children():
            self.impact_tbl.delete(iid)
        order = [
            "kMaxObjects",
            "kMaxSignalActions",
            "kMaxTextSlots",
            "kMaxTextLen",
            "kMaxShapeSlots",
            "kMaxSignals",
            "kMaxTextBoxLen",
            "kMaxColliders",
            "kMaxAlarms",
            "kMaxInputBinds",
            "kMaxChoiceLen",
            "kMaxChoiceItems",
            "kMaxChoiceSlots",
            "kMaxTextBoxes",
        ]
        for k in order:
            if k not in IMPACT_PER_UNIT:
                continue
            per = int(IMPACT_PER_UNIT[k])
            val = int(self.runtime_limits.get(k, 0))
            total = per * val
            self.impact_tbl.insert("", "end", values=(k, f"{per} B", val, f"{total} B"))

    def redraw_masa_table(self):
        if not hasattr(self, "masa_tbl"):
            return
        for iid in self.masa_tbl.get_children():
            self.masa_tbl.delete(iid)
        if not self.file_data:
            self.masa_tbl.insert("", "end", values=("Status", "No .masa loaded"))
            return

        fd = self.file_data
        h = fd["header"]
        script = fd.get("script", b"")
        unique_ops = len(set(script)) if script else 0
        top = opcode_histogram(script)[:3]
        top_ops = ", ".join([f"{name}({cnt})" for _op, name, cnt in top]) if top else "-"

        rows = [
            ("File", fd["name"]),
            ("File Size", fmt_bytes(int(fd["size"]))),
            ("Version", str(h.get("version", 0))),
            ("Entry Point", str(h.get("entryPoint", 0))),
            ("BG Index", str(h.get("bgIndex", 0))),
            ("Song Hash", str(h.get("songHash", 0))),
            ("Script Offset", f"0x{int(h.get('scriptOffset', 0)):08X}"),
            ("Script Size", fmt_bytes(int(h.get("scriptSize", 0)))),
            ("Sprites Offset", f"0x{int(h.get('spritesOffset', 0)):08X}"),
            ("Sprites Size", fmt_bytes(int(h.get("spritesSize", 0)))),
            ("Tilemap Offset", f"0x{int(h.get('tilemapOffset', 0)):08X}"),
            ("Tilemap Size", fmt_bytes(int(h.get("tilemapSize", 0)))),
            ("Unique Opcodes", str(unique_ops)),
            ("Top Opcodes", top_ops),
        ]
        for k, v in rows:
            self.masa_tbl.insert("", "end", values=(k, v))

    def redraw_chip(self):
        self.canvas.delete("all")
        if not self.file_data:
            return
        size = int(self.file_data["size"])
        try:
            cap_kb = max(1, int(float(self.cap_var.get().strip())))
        except Exception:
            cap_kb = 1024
            self.cap_var.set("1024")
        cap = cap_kb * 1024
        pct = min(100.0, (size * 100.0) / max(1, cap))

        # RAM estimate: mapped data + configurable runtime overhead.
        mapped = 0
        for name, _off, sec_size in self.file_data.get("sections", []):
            if name in ("Header", "Script", "Sprites", "Tilemap"):
                mapped += int(sec_size)
        try:
            ram_cap_kb = max(1.0, float(self.ram_cap_var.get().strip()))
        except Exception:
            ram_cap_kb = 121.66
            self.ram_cap_var.set("121.66")
        try:
            ram_overhead_kb = max(0, int(float(self.ram_overhead_var.get().strip())))
        except Exception:
            ram_overhead_kb = 64
            self.ram_overhead_var.set("64")
        # Realistic RAM estimate is driven by runtime limits (static arrays),
        # plus MASA loader buffers and optional "other app BSS" margin.
        runtime_limit_based = int(self.runtime_est_bytes)
        est_mode = self.est_mode_var.get().strip() if hasattr(self, "est_mode_var") else "Estimate"
        mode_extra_kb = 0
        if est_mode == "Conservative":
            mode_extra_kb = 16
        elif est_mode == "Worst-case":
            mode_extra_kb = 32
        ram_used_est = runtime_limit_based + ((ram_overhead_kb + mode_extra_kb) * 1024)
        ram_cap = int(ram_cap_kb * 1024.0)
        ram_source = "estimate"
        ram_used = ram_used_est
        if self.map_info and self.map_info.get("used") is not None:
            ram_used = int(self.map_info["used"])
            ram_source = "map"
            if self.map_info.get("region_total") is not None:
                ram_cap = int(self.map_info["region_total"])
        ram_pct_raw = (ram_used * 100.0) / max(1, ram_cap)
        ram_pct_draw = min(100.0, ram_pct_raw)

        def draw_chip(x0, y0, x1, y1, title, used, total_cap, used_pct_label, used_pct_draw, meter_color):
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#7f8c8d", width=3, fill="#202b38")
            for i in range(8):
                py = y0 + 15 + i * 25
                self.canvas.create_rectangle(x0 - 20, py, x0, py + 8, fill="#7f8c8d", outline="")
                self.canvas.create_rectangle(x1, py, x1 + 20, py + 8, fill="#7f8c8d", outline="")
            mx0, my0, mx1, my1 = x0 + 30, y0 + 25, x1 - 30, y1 - 25
            self.canvas.create_rectangle(mx0, my0, mx1, my1, outline="#5f6f83", width=2, fill="#0f1622")
            fill_w = int((mx1 - mx0 - 2) * (used_pct_draw / 100.0))
            self.canvas.create_rectangle(mx0 + 1, my0 + 1, mx0 + 1 + fill_w, my1 - 1, outline="", fill=meter_color)
            self.canvas.create_text((x0 + x1) // 2, y0 - 12, text=title, fill=PALETTE["editor_text"], font=("Consolas", 11, "bold"))
            self.canvas.create_text((x0 + x1) // 2, (my0 + my1) // 2, text=f"{used_pct_label:.1f}%", fill="white", font=("Consolas", 18, "bold"))
            self.canvas.create_text((x0 + x1) // 2, y1 + 18, text=f"{fmt_bytes(used)} / {fmt_bytes(total_cap)}", fill=PALETTE["editor_text"], font=("Consolas", 10))

        # ROM chip (left)
        draw_chip(80, 40, 340, 260, "ROM CHIP", size, cap, pct, pct, "#2ecc71")
        # RAM chip (right)
        ram_color = "#22d3ee"
        if ram_pct_raw > 100.0:
            ram_color = "#ef4444"
        draw_chip(500, 40, 760, 260, "RAM CHIP", ram_used, ram_cap, ram_pct_raw, ram_pct_draw, ram_color)
        if ram_source == "map":
            extra = ""
            if self.map_info and self.map_info.get("overflow", 0) > 0:
                extra = f" | overflow: {self.map_info['overflow']} B"
            self.canvas.create_text(
                630, 296,
                text=f"Source: .map (dram0){extra}",
                fill=PALETTE["editor_comment"], font=("Consolas", 9)
            )
            if self.map_info and self.map_info.get("overflow", 0) > 0:
                self.canvas.create_text(
                    630, 302,
                    text=f"OVERFLOW: +{self.map_info['overflow']} B",
                    fill="#fca5a5", font=("Consolas", 10, "bold")
                )
        else:
            self.canvas.create_text(
                630, 296,
                text=(
                    f"Source: estimate [{est_mode}] "
                    f"({fmt_bytes(runtime_limit_based)} + {fmt_bytes((ram_overhead_kb + mode_extra_kb) * 1024)})"
                ),
                fill=PALETTE["editor_comment"], font=("Consolas", 9)
            )
            if ram_pct_raw > 100.0:
                over_b = max(0, int(ram_used - ram_cap))
                self.canvas.create_text(
                    630, 312,
                    text=f"OVERFLOW: +{over_b} B",
                    fill="#fca5a5", font=("Consolas", 10, "bold")
                )

    def redraw_bars(self):
        self.bars.delete("all")
        if not self.file_data:
            return
        sections = self.file_data["sections"]
        total = max(1, int(self.file_data["size"]))
        x0, y = 20, 20
        width = 360
        colors = [PALETTE["editor_kw"], "#81c784", "#ffb74d", PALETTE["editor_masa"], PALETTE["accent"], "#64b5f6"]
        for i, (name, _off, size) in enumerate(sections):
            pct = (size * 100.0) / total
            bw = max(1, int(width * pct / 100.0))
            color = colors[i % len(colors)]
            self.bars.create_rectangle(x0, y, x0 + bw, y + 18, fill=color, outline="")
            self.bars.create_text(x0 + bw + 8, y + 9, anchor="w", fill=PALETTE["editor_text"],
                                  text=f"{name}  {pct:.2f}% ({fmt_bytes(size)})", font=("Consolas", 9))
            y += 26
            if y > 250:
                break


def main():
    app = MasaSizeViewer()
    app.mainloop()


if __name__ == "__main__":
    main()
