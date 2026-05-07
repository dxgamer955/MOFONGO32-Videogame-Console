#!/usr/bin/env python3
"""
Editor principal de MOFONGO32.

Crea proyectos .ingr, maneja assets/rooms/scripts y exporta:
  generated/program_logic.h
  generated/program_logic.json
  Programs/*.masa

El header generado puede ser incluido por AudioVideoExample.ino; el .masa se carga por SPIFFS.
"""

import json
import base64
import os
import re
import struct
import zipfile
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import subprocess
import sys
import threading

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GENERATED_DIR = os.path.join(PROJECT_ROOT, "generated")
ROOM_W = 320
ROOM_H = 200
CANVAS_SCALE = 2
THEME = {
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

MAGENTA_KEY = (255, 0, 255)

TEXT_COLOR_NAMES = {
    "black": 0,
    "darkgreen": 1,
    "green": 2,
    "lightgreen": 3,
    "darkgray": 4,
    "gray": 5,
    "lightgray": 6,
    "white": 15,
    "red": 9,
    "orange": 10,
    "yellow": 11,
    "blue": 12,
    "cyan": 13,
    "magenta": 14,
}

PALETTE_HEX = {
    0: "#000000",
    1: "#1E3A27",
    2: "#2F6B3F",
    3: "#8CAD92",
    4: "#2A2A2A",
    5: "#555555",
    6: "#AAAAAA",
    7: "#FFFFFF",
    8: "#FFFFFF",
    9: "#C0392B",
    10: "#E67E22",
    11: "#F1C40F",
    12: "#2980B9",
    13: "#1ABC9C",
    14: "#9B59B6",
    15: "#FFFFFF",
}

SHAPE_TYPES = {
    "line": 1,
    "rect": 2,
    "fill_rect": 3,
    "tri": 4,
    "circle": 5,
}


def load_asset_meta(path: str, expected_type: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    elif ext == ".h":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r"// ASSET_META:\s*(\{.*\})", txt)
        if not m:
            raise ValueError("Header has no ASSET_META.")
        meta = json.loads(m.group(1))
    else:
        raise ValueError("Unsupported file type.")

    if not isinstance(meta, dict) or meta.get("type") != expected_type:
        raise ValueError(f"Invalid metadata type. Expected {expected_type}.")
    return meta


def load_songs_meta(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    elif ext == ".h":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r"// SONGS_ATLAS_META:\s*(\{.*\})", txt)
        if not m:
            raise ValueError("Header has no SONGS_ATLAS_META.")
        meta = json.loads(m.group(1))
    else:
        raise ValueError("Unsupported file type.")

    if not isinstance(meta, dict) or meta.get("type") != "songs_atlas_v1":
        raise ValueError("Invalid songs metadata type. Expected songs_atlas_v1.")
    if not isinstance(meta.get("songs", []), list):
        raise ValueError("Invalid songs metadata list.")
    return meta


def sanitize_ident(name: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not out:
        out = "obj"
    if out[0].isdigit():
        out = "_" + out
    return out


def palette_color_hex(idx: int) -> str:
    return PALETTE_HEX.get(int(idx) & 0xFF, "#000000")


def is_magenta_key(r, g, b):
    if r == 255 and g == 0 and b == 255:
        return True
    # Accept near-magenta to handle palette/PNG conversions.
    return r >= 200 and b >= 200 and g <= 80


def parse_frames(s: str):
    s = s.strip()
    if not s:
        return []
    vals = []
    for p in s.split(","):
        p = p.strip()
        if not p:
            continue
        vals.append(int(p))
    return vals


def sanitize_filename(name: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_.-]", "_", name.strip())
    return out or "file"


def masa_note_to_hz(token: str) -> int:
    s = str(token or "").strip()
    if not s:
        return 0
    if re.match(r"^\d+(\.\d+)?$", s):
        try:
            hz = int(float(s))
        except Exception:
            hz = 0
        return max(1, min(20000, hz)) if hz > 0 else 0
    m = re.match(r"^([A-Ga-g])([#bB]?)(-?\d+)$", s)
    if not m:
        return 0
    note = m.group(1).upper()
    accidental = m.group(2)
    octave = int(m.group(3))
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[note]
    if accidental == "#":
        base += 1
    elif accidental in ("b", "B"):
        base -= 1
    midi = (octave + 1) * 12 + base
    hz = int(round(440.0 * (2.0 ** ((midi - 69) / 12.0))))
    if hz <= 0:
        return 0
    return max(1, min(20000, hz))


def parse_masa_behavior(script_text: str):
    info = {
        "enabled": False,
        "vx": 1.2,
        "vy": 0.9,
        "vel_random": None,
        "bounds": (20, 300, 20, 180),
        "rot_speed": 2.5,
        "scale_base": 0.85,
        "scale_amp": 0.25,
        "scale_speed": 4.0,
        "input_speed": 0.0,
        "input_enabled": False,
        "no_wrap": None,
        "bounce": None,
    }
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_BEHAVIOR:\s*(\w+)", line)
        if m:
            info["enabled"] = True
            continue
        m = re.match(r"\s*//\s*MASA_VEL:\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["enabled"] = True
            info["vx"] = float(m.group(1))
            info["vy"] = float(m.group(2))
            continue
        m = re.match(r"\s*//\s*MASA_VEL_RANDOM:\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["enabled"] = True
            info["vel_random"] = (float(m.group(1)), float(m.group(2)))
            continue
        m = re.match(r"\s*//\s*MASA_VX:\s*([-\d.]+)", line)
        if m:
            info["enabled"] = True
            info["vx"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_VY:\s*([-\d.]+)", line)
        if m:
            info["enabled"] = True
            info["vy"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_BOUNDS:\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["bounds"] = (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            continue
        m = re.match(r"\s*//\s*MASA_ROT_SPEED:\s*([-\d.]+)", line)
        if m:
            info["rot_speed"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_SCALE:\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["scale_base"] = float(m.group(1))
            info["scale_amp"] = float(m.group(2))
            info["scale_speed"] = float(m.group(3))
            continue
        m = re.match(r"\s*//\s*MASA_ROTATE:\s*([-\d.]+)", line)
        if m:
            info["rotate_speed"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_THRUST:\s*([-\d.]+)", line)
        if m:
            info["thrust"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_WRAP:\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["wrap"] = (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            continue
        m = re.match(r"\s*//\s*MASA_NO_WRAP:\s*([01])", line)
        if m:
            info["no_wrap"] = int(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_BOUNCE:\s*([01])", line)
        if m:
            info["bounce"] = int(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_SPRITE_INDEX:\s*(\d+)", line)
        if m:
            info["sprite_index"] = int(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_IMAGE_SPEED:\s*([-\d.]+)", line)
        if m:
            info["image_speed"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_ANIMATION_FRAMES:\s*(.+)", line)
        if m:
            info["anim_frames"] = parse_frames(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_START_POS_X:\s*([-\d.]+)", line)
        if m:
            info["start_pos_x"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_START_POS_Y:\s*([-\d.]+)", line)
        if m:
            info["start_pos_y"] = float(m.group(1))
            continue
        m = re.match(r"\s*//\s*MASA_ACCEL:\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            info["accel"] = float(m.group(1))
            info["friction"] = float(m.group(2))
            continue
        m = re.match(r"\s*//\s*MASA_INPUT:\s*([-\d.]+)", line)
        if m:
            info["input_enabled"] = True
            info["input_speed"] = float(m.group(1))
            continue
    return info


def parse_masa_pool(script_text: str):
    info = {
        "reserve": 0,
        "priority": 0,
    }
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_POOL_RESERVE:\s*(\d+)", line)
        if m:
            try:
                info["reserve"] = max(0, int(m.group(1)))
            except Exception:
                info["reserve"] = 0
            continue
        m = re.match(r"\s*//\s*MASA_POOL_PRIORITY:\s*(-?\d+)", line)
        if m:
            try:
                info["priority"] = int(m.group(1))
            except Exception:
                info["priority"] = 0
            continue
    return info


def parse_masa_texts(script_text: str):
    texts = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_(TEXT_CLEAR|SHOW_TEXT_CLEAR):\s*(\d+)", line)
        if m:
            texts.append({"slot": int(m.group(2)), "clear": True})
            continue
        m = re.match(r"\s*//\s*MASA_(TEXT|SHOW_TEXT):\s*(.+)", line)
        if not m:
            continue
        payload = m.group(2).strip()
        # Format A: slot,x,y,color,text
        parts = [p.strip() for p in payload.split(",", 4)]
        if len(parts) >= 5:
            try:
                slot = int(parts[0])
            except Exception:
                slot = 0
            try:
                x = int(float(parts[1]))
            except Exception:
                x = None
            try:
                y = int(float(parts[2]))
            except Exception:
                y = None
            color_token = parts[3].strip().lower()
            if re.match(r"^\d+$", color_token):
                color = int(color_token)
            else:
                color = TEXT_COLOR_NAMES.get(color_token, 15)
            text = parts[4].strip().strip('"').strip("'")
        else:
            # Format B: just text -> defaults
            slot = 0
            x = None
            y = None
            color = 15
            text = payload.strip().strip('"').strip("'")
        if not text:
            continue
        texts.append({"slot": slot, "x": x, "y": y, "color": color, "text": text})
    return texts


def parse_masa_shapes(script_text: str):
    shapes = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_SHAPE_CLEAR:\s*(\d+)", line)
        if m:
            shapes.append({"clear": True, "slot": int(m.group(1))})
            continue
        m = re.match(r"\s*//\s*MASA_(RECT|FILL_RECT|LINE|TRI|CIRCLE):\s*(.+)", line)
        if not m:
            continue
        kind = m.group(1).lower()
        payload = m.group(2).strip()
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) < 2:
            continue
        try:
            slot = int(parts[0])
        except Exception:
            slot = 0
        color = 15
        if parts:
            color_token = parts[-1].strip().lower()
            if re.match(r"^\d+$", color_token):
                color = int(color_token)
            else:
                color = TEXT_COLOR_NAMES.get(color_token, 15)
        nums = []
        for p in parts[1:-1]:
            try:
                nums.append(int(float(p)))
            except Exception:
                nums.append(0)
        shapes.append({"type": SHAPE_TYPES.get(kind, 0), "slot": slot, "nums": nums, "color": color})
    return shapes


def parse_masa_hud(script_text: str):
    def _split_args(payload: str):
        return [p.strip() for p in re.findall(r'"[^"]*"|[^,]+', payload or "")]

    def _parse_color(token, default=15, allow_none=False):
        t = str(token or "").strip().lower()
        if allow_none and t in ("none", "off", "-1"):
            return -1
        if re.match(r"^-?\d+$", t):
            try:
                return int(t)
            except Exception:
                return default
        return TEXT_COLOR_NAMES.get(t, default)

    def _parse_align(token):
        t = str(token or "").strip().lower()
        if t in ("center", "centre", "1"):
            return 1
        if t in ("right", "2"):
            return 2
        return 0

    hud = {"draw": None, "set": None, "adds": [], "style": None}
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_HUD_SET:\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            hud["set"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            continue
        m = re.match(r"\s*//\s*MASA_HUD_ADD:\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            hud["adds"].append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_HUD:\s*(.+)", line)
        if m:
            parts = _split_args(m.group(1))
            if len(parts) < 3:
                continue
            try:
                x = int(float(parts[0]))
                y = int(float(parts[1]))
            except Exception:
                continue
            color = _parse_color(parts[2], 15)
            hud["draw"] = (x, y, color)
            align = _parse_align(parts[3]) if len(parts) >= 4 else 0
            bg_color = _parse_color(parts[4], -1, allow_none=True) if len(parts) >= 5 else -1
            try:
                pad_x = int(float(parts[5])) if len(parts) >= 6 else 2
            except Exception:
                pad_x = 2
            try:
                pad_y = int(float(parts[6])) if len(parts) >= 7 else 1
            except Exception:
                pad_y = 1
            template = "L:{LIFE} S:{SCORE} C:{COINS}"
            if len(parts) >= 8:
                template = parts[7].strip()
                if template.startswith('"') and template.endswith('"') and len(template) >= 2:
                    template = template[1:-1]
            hud["style"] = {
                "x": x,
                "y": y,
                "color": color,
                "align": align,
                "bg_color": bg_color,
                "pad_x": max(0, min(255, int(pad_x))),
                "pad_y": max(0, min(255, int(pad_y))),
                "template": template,
            }
            continue
    return hud


def parse_masa_beeps(script_text: str):
    beeps = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_BEEP(?:_(SQUARE|NOISE))?:\s*([^,]+)\s*,\s*([-\d.]+)", line)
        if not m:
            continue
        wave_tok = (m.group(1) or "").strip().lower()
        note = m.group(2).strip()
        try:
            duration = int(float(m.group(3)))
        except Exception:
            duration = 0
        if duration > 0:
            wave = 0
            if wave_tok == "noise":
                wave = 3
            beeps.append({"note": note, "duration": duration, "wave": wave})
    return beeps


MASA_BUTTONS = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "X", "Y", "START", "SELECT", "L", "R"]
MASA_DIRECTIVES = [
    "MASA_BEHAVIOR",
    "MASA_VEL",
    "MASA_VEL_RANDOM",
    "MASA_VX",
    "MASA_VY",
    "MASA_BOUNDS",
    "MASA_ROT_SPEED",
    "MASA_SCALE",
    "MASA_ACCEL",
    "MASA_ROTATE",
    "MASA_THRUST",
    "MASA_WRAP",
    "MASA_NO_WRAP",
    "MASA_BOUNCE",
    "MASA_POOL_RESERVE",
    "MASA_POOL_PRIORITY",
    "MASA_SPRITE_INDEX",
    "MASA_IMAGE_SPEED",
    "MASA_ANIMATION_FRAMES",
    "MASA_START_POS_X",
    "MASA_START_POS_Y",
    "MASA_INPUT",
    "MASA_TEXT",
    "MASA_TEXT_CLEAR",
    "MASA_SHOW_TEXT",
    "MASA_SHOW_TEXT_CLEAR",
    "MASA_TEXTBOX",
    "MASA_TEXTBOX_CLEAR",
    "MASA_CHOICES",
    "MASA_CHOICES_CLEAR",
    "MASA_RECT",
    "MASA_FILL_RECT",
    "MASA_LINE",
    "MASA_TRI",
    "MASA_CIRCLE",
    "MASA_SHAPE_CLEAR",
    "MASA_SPAWN",
    "MASA_DESTROY",
    "MASA_HITBOX",
    "MASA_COLLIDE",
    "MASA_ON_SIGNAL_DESTROY",
    "MASA_ON_SIGNAL_SPAWN",
    "MASA_ON_SIGNAL_SOUND",
    "MASA_ON_SIGNAL_BEEP",
    "MASA_ON_SIGNAL_BEEP_SQUARE",
    "MASA_ON_SIGNAL_BEEP_NOISE",
    "MASA_ON_SIGNAL_ROOM_NEXT",
    "MASA_ON_SIGNAL_ROOM_GOTO",
    "MASA_ON_SIGNAL_SPAWN_BULLET",
    "MASA_ON_SIGNAL_STOP",
    "MASA_ON_SIGNAL_TEXTBOX",
    "MASA_ON_SIGNAL_CHOICES",
    "MASA_ON_SIGNAL_TEXTBOX_CLEAR",
    "MASA_ON_SIGNAL_CHOICES_CLEAR",
    "MASA_ON_SIGNAL_SET_INPUT",
    "MASA_ON_SIGNAL_SHOW_TEXT",
    "MASA_ON_SIGNAL_SHOW_TEXT_CLEAR",
    "MASA_ON_SIGNAL_HUD_ADD",
    "MASA_BG_SCROLL_X",
    "MASA_BG_SCROLL_Y",
    "MASA_START_ALARM",
    "MASA_STOP_ALARM",
    "IF_MASA_ALARM_RINGS",
    "MASA_PLAY_MUSIC",
    "MASA_STOP_MUSIC",
    "MASA_PAUSE_MUSIC",
    "MASA_SONG_LOOP",
    "MASA_BEEP",
    "MASA_BEEP_SQUARE",
    "MASA_BEEP_NOISE",
    "MASA_IF_MUSIC_IS_PLAYING",
    "MASA_HUD",
    "MASA_HUD_SET",
    "MASA_HUD_ADD",
    "MASA_VAR_SET",
    "MASA_VAR_ADD",
    "MASA_VAR_TEXT",
    "MASA_VARF_SET",
    "MASA_VARF_ADD",
    "MASA_VARF_TEXT",
    "MASA_INC",
    "MASA_DEC",
    "MASA_IF_EQ",
    "MASA_IF_GT",
    "MASA_IF_LT",
    "MASA_IF_EQF",
    "MASA_IF_GTF",
    "MASA_IF_LTF",
    "MASA_VAR_CLAMP",
    "MASA_VARF_CLAMP",
    "MASA_VAR_RAND",
    "MASA_VARF_LERP",
    "MASA_VAR_MIN",
    "MASA_VAR_MAX",
    "MASA_VARF_MIN",
    "MASA_VARF_MAX",
    "MASA_VARF_SIN",
    "MASA_VARF_COS",
    "MASA_STR_SET",
    "MASA_STR_TEXT",
    "MASA_SWITCH",
]
for _btn in MASA_BUTTONS:
    MASA_DIRECTIVES.append(f"MASA_PRESS_BTN_{_btn}")
    MASA_DIRECTIVES.append(f"MASA_PRESSED_BTN_{_btn}")
    MASA_DIRECTIVES.append(f"MASA_RELEASED_BTN_{_btn}")


def parse_masa_spawns(script_text: str):
    ops = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_SPAWN:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 4:
                try:
                    obj_id = int(parts[0])
                    x = int(float(parts[1]))
                    y = int(float(parts[2]))
                    frame = int(parts[3])
                    ops.append(("spawn", obj_id, x, y, frame))
                except Exception:
                    pass
            continue
        m = re.match(r"\s*//\s*MASA_DESTROY:\s*(\d+)", line)
        if m:
            ops.append(("destroy", int(m.group(1))))
    return ops


def parse_masa_signals(script_text: str):
    info = {
        "hitbox": None,
        "colliders": [],
        "actions": [],
    }
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_HITBOX:\s*(.+)", line)
        if m:
            try:
                parts = [p.strip() for p in m.group(1).split(",")]
                if len(parts) >= 2:
                    w = int(float(parts[0]))
                    h = int(float(parts[1]))
                    if len(parts) >= 4:
                        off_x = int(float(parts[2]))
                        off_y = int(float(parts[3]))
                        info["hitbox"] = (max(1, w), max(1, h), off_x, off_y)
                    else:
                        info["hitbox"] = (max(1, w), max(1, h))
            except Exception:
                pass
            continue
        m = re.match(r"\s*//\s*MASA_COLLIDE:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                other = parts[1]
                info["colliders"].append({"slot": slot, "other": other})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_DESTROY:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if parts:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                target = parts[1] if len(parts) > 1 else "self"
                info["actions"].append({"slot": slot, "type": "destroy", "target": target})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SPAWN:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 4:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                info["actions"].append({
                    "slot": slot,
                    "type": "spawn",
                    "obj": parts[1],
                    "x": parts[2],
                    "y": parts[3],
                    "frame": parts[4] if len(parts) > 4 else None,
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SPAWN_BULLET:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 3:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                speed = parts[2] if len(parts) > 2 else "0"
                offset = parts[3] if len(parts) > 3 else "0"
                info["actions"].append({
                    "slot": slot,
                    "type": "spawn_bullet",
                    "obj": parts[1],
                    "speed": speed,
                    "offset": offset,
                    "frame": parts[4] if len(parts) > 4 else None,
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SOUND:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                info["actions"].append({
                    "slot": slot,
                    "type": "sound",
                    "sound": parts[1],
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_BEEP:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 3:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                info["actions"].append({
                    "slot": slot,
                    "type": "beep",
                    "note": parts[1],
                    "duration": parts[2],
                    "wave": "square",
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_BEEP_(SQUARE|NOISE):\s*(.+)", line)
        if m:
            wave_tok = (m.group(1) or "").strip().lower()
            parts = [p.strip() for p in m.group(2).split(",")]
            if len(parts) >= 3:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                info["actions"].append({
                    "slot": slot,
                    "type": "beep",
                    "note": parts[1],
                    "duration": parts[2],
                    "wave": wave_tok,
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_ROOM_NEXT:\s*(\d+)", line)
        if m:
            info["actions"].append({"slot": int(m.group(1)), "type": "room_next"})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_ROOM_GOTO:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                    room = int(parts[1])
                except Exception:
                    slot = 0
                    room = 0
                info["actions"].append({"slot": slot, "type": "room_goto", "room": room})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_STOP:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if parts:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                target = parts[1] if len(parts) > 1 else "self"
                info["actions"].append({"slot": slot, "type": "stop", "target": target})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_TEXTBOX:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",", 8)]
            if len(parts) >= 8:
                try:
                    slot = int(parts[0])
                    box_slot = int(parts[1])
                    x = int(float(parts[2]))
                    y = int(float(parts[3]))
                    w = int(float(parts[4]))
                    h = int(float(parts[5]))
                except Exception:
                    slot = 0
                    box_slot = 0
                    x = y = w = h = 0
                color_token = parts[6].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                text = parts[7].strip().strip('"').strip("'")
                info["actions"].append({
                    "slot": slot,
                    "type": "textbox",
                    "box": box_slot,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "color": color,
                    "text": text,
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_CHOICES:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",", 6)]
            if len(parts) >= 6:
                try:
                    slot = int(parts[0])
                    choice_slot = int(parts[1])
                    x = int(float(parts[2]))
                    y = int(float(parts[3]))
                except Exception:
                    slot = 0
                    choice_slot = 0
                    x = y = 0
                color_token = parts[4].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                try:
                    base_signal = int(parts[5])
                except Exception:
                    base_signal = 0
                text = parts[6].strip().strip('"').strip("'") if len(parts) > 6 else ""
                items = [p.strip() for p in text.split("|") if p.strip()]
                info["actions"].append({
                    "slot": slot,
                    "type": "choices",
                    "choice": choice_slot,
                    "x": x,
                    "y": y,
                    "color": color,
                    "base_signal": base_signal,
                    "items": items,
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_TEXTBOX_CLEAR:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                    box_slot = int(parts[1])
                except Exception:
                    slot = 0
                    box_slot = 0
                info["actions"].append({"slot": slot, "type": "textbox_clear", "box": box_slot})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_CHOICES_CLEAR:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                    choice_slot = int(parts[1])
                except Exception:
                    slot = 0
                    choice_slot = 0
                info["actions"].append({"slot": slot, "type": "choices_clear", "choice": choice_slot})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SET_INPUT:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 3:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                target = parts[1]
                try:
                    speed = float(parts[2])
                except Exception:
                    speed = 0.0
                info["actions"].append({"slot": slot, "type": "set_input", "target": target, "speed": speed})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SHOW_TEXT:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in re.findall(r'"[^"]*"|[^,]+', m.group(1))]
            if len(parts) >= 6:
                try:
                    slot = int(parts[0]); text_slot = int(parts[1]); x = int(float(parts[2])); y = int(float(parts[3]))
                except Exception:
                    slot = 0; text_slot = 0; x = 0; y = 0
                color_token = parts[4].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                align = 0
                text_idx = 5
                if len(parts) >= 7:
                    a = parts[5].strip().lower()
                    if a in ("center", "centre"):
                        align = 1
                    elif a == "right":
                        align = 2
                    elif re.match(r"^\d+$", a):
                        try:
                            align = max(0, min(2, int(a)))
                        except Exception:
                            align = 0
                    else:
                        align = 0
                    text_idx = 6
                text = parts[text_idx].strip().strip('"').strip("'")
                info["actions"].append({
                    "slot": slot, "type": "show_text", "text_slot": text_slot,
                    "x": x, "y": y, "color": color, "align": align, "text": text
                })
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_SHOW_TEXT_CLEAR:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0]); text_slot = int(parts[1])
                except Exception:
                    slot = 0; text_slot = 0
                info["actions"].append({"slot": slot, "type": "show_text_clear", "text_slot": text_slot})
            continue
        m = re.match(r"\s*//\s*MASA_ON_SIGNAL_HUD_ADD:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 4:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                try:
                    life = int(float(parts[1]))
                except Exception:
                    life = 0
                try:
                    score = int(float(parts[2]))
                except Exception:
                    score = 0
                try:
                    coins = int(float(parts[3]))
                except Exception:
                    coins = 0
                info["actions"].append({
                    "slot": slot,
                    "type": "hud_add",
                    "life": life,
                    "score": score,
                    "coins": coins,
                })
    return info


def parse_masa_textboxes(script_text: str):
    boxes = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_TEXTBOX_CLEAR:\s*(\d+)", line)
        if m:
            boxes.append({"clear": True, "slot": int(m.group(1))})
            continue
        m = re.match(r"\s*//\s*MASA_TEXTBOX:\s*(.+)", line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split(",", 6)]
        if len(parts) < 7:
            continue
        try:
            slot = int(parts[0])
            x = int(float(parts[1]))
            y = int(float(parts[2]))
            w = int(float(parts[3]))
            h = int(float(parts[4]))
        except Exception:
            continue
        color_token = parts[5].strip().lower()
        if re.match(r"^\d+$", color_token):
            color = int(color_token)
        else:
            color = TEXT_COLOR_NAMES.get(color_token, 15)
        text = parts[6].strip().strip('"').strip("'")
        boxes.append({
            "slot": slot,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "color": color,
            "text": text,
        })
    return boxes


def parse_masa_choices(script_text: str):
    choices = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_CHOICES_CLEAR:\s*(\d+)", line)
        if m:
            choices.append({"clear": True, "slot": int(m.group(1))})
            continue
        m = re.match(r"\s*//\s*MASA_CHOICES:\s*(.+)", line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split(",", 5)]
        if len(parts) < 6:
            continue
        try:
            slot = int(parts[0])
            x = int(float(parts[1]))
            y = int(float(parts[2]))
        except Exception:
            continue
        color_token = parts[3].strip().lower()
        if re.match(r"^\d+$", color_token):
            color = int(color_token)
        else:
            color = TEXT_COLOR_NAMES.get(color_token, 15)
        try:
            base_signal = int(parts[4])
        except Exception:
            base_signal = 0
        text = parts[5].strip().strip('"').strip("'")
        items = [p.strip() for p in text.split("|") if p.strip()]
        choices.append({
            "slot": slot,
            "x": x,
            "y": y,
            "color": color,
            "base_signal": base_signal,
            "items": items,
        })
    return choices


def parse_masa_input_binds(script_text: str):
    binds = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_(PRESS|PRESSED|RELEASED)_BTN_([A-Z]+):\s*(\d+)", line)
        if not m:
            continue
        ev_name = m.group(1)
        btn = m.group(2)
        slot = int(m.group(3))
        # Event mapping (GameMaker-like): PRESSED = just pressed, PRESS = held.
        ev = 0
        if ev_name == "PRESSED":
            ev = 1
        elif ev_name == "PRESS":
            ev = 0
        elif ev_name == "RELEASED":
            ev = 2
        btn_map = {
            "UP": 0,
            "DOWN": 1,
            "LEFT": 2,
            "RIGHT": 3,
            "A": 4,
            "B": 5,
            "X": 6,
            "Y": 7,
            "START": 8,
            "SELECT": 9,
            "L": 10,
            "R": 11,
        }
        if btn not in btn_map:
            continue
        binds.append({"slot": slot, "ev": ev, "btn": btn_map[btn]})
    return binds


def parse_masa_bg_scroll(script_text: str):
    scroll_x = None
    scroll_y = None
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_BG_SCROLL_X:\s*([-\d.]+)", line)
        if m:
            try:
                scroll_x = float(m.group(1))
            except Exception:
                pass
        m = re.match(r"\s*//\s*MASA_BG_SCROLL_Y:\s*([-\d.]+)", line)
        if m:
            try:
                scroll_y = float(m.group(1))
            except Exception:
                pass
    return scroll_x, scroll_y


def parse_masa_alarm(script_text: str):
    alarms = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_START_ALARM:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                    ms = int(float(parts[1]))
                except Exception:
                    continue
                repeat = 1 if (len(parts) > 2 and parts[2].strip().lower() in ("1", "true", "yes", "repeat")) else 0
                alarms.append({"type": "start", "slot": slot, "ms": ms, "repeat": repeat})
            continue
        m = re.match(r"\s*//\s*MASA_STOP_ALARM:\s*(\d+)", line)
        if m:
            alarms.append({"type": "stop", "slot": int(m.group(1))})
            continue
        m = re.match(r"\s*//\s*IF_MASA_ALARM_RINGS:\s*(.+)", line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) >= 2:
                try:
                    slot = int(parts[0])
                    signal = int(parts[1])
                except Exception:
                    continue
                alarms.append({"type": "signal", "slot": slot, "signal": signal})
    return alarms


def parse_masa_music(script_text: str):
    music = []
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_PLAY_MUSIC:\s*(.+)", line)
        if m:
            music.append({"type": "play", "value": m.group(1).strip()})
            continue
        m = re.match(r"\s*//\s*MASA_STOP_MUSIC\s*$", line)
        if m:
            music.append({"type": "stop"})
            continue
        m = re.match(r"\s*//\s*MASA_PAUSE_MUSIC\s*$", line)
        if m:
            music.append({"type": "pause"})
            continue
        m = re.match(r"\s*//\s*MASA_SONG_LOOP:\s*([01]|true|false|yes|no)", line, re.IGNORECASE)
        if m:
            token = m.group(1).strip().lower()
            loop = 1 if token in ("1", "true", "yes") else 0
            music.append({"type": "loop", "value": loop})
            continue
        m = re.match(r"\s*//\s*MASA_IF_MUSIC_IS_PLAYING:\s*(\d+)", line)
        if m:
            music.append({"type": "signal", "value": int(m.group(1))})
    return music


def parse_masa_vars(script_text: str):
    out = {"set": [], "add": [], "text": [], "setf": [], "addf": [], "textf": [], "ifs": [], "ifsf": [], "clamp": [], "clampf": [], "rand": [], "lerp": [], "min": [], "max": [], "minf": [], "maxf": [], "sin": [], "cos": [], "str_set": [], "str_text": [], "switch": []}
    for line in (script_text or "").splitlines():
        m = re.match(r"\s*//\s*MASA_VAR_SET:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["set"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_ADD:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["add"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_SET:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["setf"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_ADD:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["addf"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_TEXT:\s*(.+)", line)
        if m:
            payload = m.group(1).strip()
            parts = [p.strip() for p in payload.split(",", 6)]
            if len(parts) >= 6:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                try:
                    x = int(float(parts[1]))
                except Exception:
                    x = 0
                try:
                    y = int(float(parts[2]))
                except Exception:
                    y = 0
                color_token = parts[3].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                target = parts[4].strip()
                try:
                    idx = int(parts[5])
                except Exception:
                    idx = 0
                label = ""
                if len(parts) >= 7:
                    label = parts[6].strip().strip('"').strip("'")
                out["text"].append((slot, x, y, color, target, idx, label))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_TEXT:\s*(.+)", line)
        if m:
            payload = m.group(1).strip()
            parts = [p.strip() for p in payload.split(",", 6)]
            if len(parts) >= 6:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                try:
                    x = int(float(parts[1]))
                except Exception:
                    x = 0
                try:
                    y = int(float(parts[2]))
                except Exception:
                    y = 0
                color_token = parts[3].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                target = parts[4].strip()
                try:
                    idx = int(parts[5])
                except Exception:
                    idx = 0
                label = ""
                if len(parts) >= 7:
                    label = parts[6].strip().strip('"').strip("'")
                out["textf"].append((slot, x, y, color, target, idx, label))
            continue
        m = re.match(r"\s*//\s*MASA_INC:\s*([^,]+)\s*,\s*([-\d]+)(?:\s*,\s*([-\d]+))?", line)
        if m:
            amt = int(m.group(3)) if m.group(3) is not None else 1
            out["add"].append((m.group(1).strip(), int(m.group(2)), amt))
            continue
        m = re.match(r"\s*//\s*MASA_DEC:\s*([^,]+)\s*,\s*([-\d]+)(?:\s*,\s*([-\d]+))?", line)
        if m:
            amt = int(m.group(3)) if m.group(3) is not None else 1
            out["add"].append((m.group(1).strip(), int(m.group(2)), -amt))
            continue
        m = re.match(r"\s*//\s*MASA_IF_(EQ|GT|LT):\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*(\d+)", line)
        if m:
            out["ifs"].append((m.group(1), m.group(2).strip(), int(m.group(3)), int(m.group(4)), int(m.group(5))))
            continue
        m = re.match(r"\s*//\s*MASA_IF_(EQF|GTF|LTF):\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)\s*,\s*(\d+)", line)
        if m:
            out["ifsf"].append((m.group(1), m.group(2).strip(), int(m.group(3)), float(m.group(4)), int(m.group(5))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_CLAMP:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["clamp"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_CLAMP:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["clampf"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3)), float(m.group(4))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_RAND:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["rand"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_LERP:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["lerp"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_MIN:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["min"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VAR_MAX:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)", line)
        if m:
            out["max"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_MIN:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["minf"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_MAX:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["maxf"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_SIN:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["sin"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_VARF_COS:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d.]+)", line)
        if m:
            out["cos"].append((m.group(1).strip(), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"\s*//\s*MASA_STR_SET:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*\"(.*)\"", line)
        if m:
            out["str_set"].append((m.group(1).strip(), int(m.group(2)), m.group(3)))
            continue
        m = re.match(r"\s*//\s*MASA_STR_TEXT:\s*(.+)", line)
        if m:
            payload = m.group(1).strip()
            parts = [p.strip() for p in payload.split(",", 6)]
            if len(parts) >= 6:
                try:
                    slot = int(parts[0])
                except Exception:
                    slot = 0
                try:
                    x = int(float(parts[1]))
                except Exception:
                    x = 0
                try:
                    y = int(float(parts[2]))
                except Exception:
                    y = 0
                color_token = parts[3].strip().lower()
                if re.match(r"^\d+$", color_token):
                    color = int(color_token)
                else:
                    color = TEXT_COLOR_NAMES.get(color_token, 15)
                target = parts[4].strip()
                try:
                    idx = int(parts[5])
                except Exception:
                    idx = 0
                label = ""
                if len(parts) >= 7:
                    label = parts[6].strip().strip('"').strip("'")
                out["str_text"].append((slot, x, y, color, target, idx, label))
            continue
        m = re.match(r"\s*//\s*MASA_SWITCH:\s*([^,]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*(\d+)", line)
        if m:
            out["switch"].append((m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4))))
            continue
    return out


class GameEngineGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MOFONGO32 Engine")
        self.geometry("1920x1080")
        self.minsize(1180, 700)
        self.configure(bg=THEME["bg"])
        self.option_add("*Background", THEME["bg"])
        self.option_add("*Foreground", THEME["text"])
        self.option_add("*Button.Background", THEME["panel"])
        self.option_add("*Button.Foreground", THEME["text"])
        self.option_add("*Entry.Background", THEME["accent"])
        self.option_add("*Entry.Foreground", THEME["text"])
        self.option_add("*Listbox.Background", THEME["panel"])
        self.option_add("*Listbox.Foreground", THEME["text"])
        self.option_add("*Label.Background", THEME["bg"])
        self.option_add("*Label.Foreground", THEME["text"])

        self.sprites_meta = None
        self.backgrounds_meta = None
        self.songs_meta = None
        self.sprite_images = []
        self.sprite_images_pil = []
        self.bg_images = []
        self.bg_images_pil = []
        self.canvas_bg = None
        self.canvas_sprites = []
        self.project = {
            "name": "game_project",
            "background_index": 0,
            "background_color": 12,
            "objects": [],
            "rooms": [],
            "active_room": 0,
            "tilemaps": [],
        }
        self.selected_obj = None
        self.selected_room_obj = None
        self.room_tilemap_index = tk.StringVar(value="none")
        self.dragging = False
        self.test_proc = None
        self.test_reader = None
        self.tilemap_window = None
        self.tilemap_selected = None
        self.tilemap_layer = "back"
        self.tilemap_show_grid = tk.BooleanVar(value=True)
        self.tilemap_tileset_index = -1
        self.tilemap_tile_size = 16
        self.tilemap_sel_rect = None
        self.tilemap_sel = {"w": 1, "h": 1, "tiles": [1]}
        self.tilemap_tileset_img = None
        self.tilemap_tileset_photo = None
        self.tilemap_tileset_cache = {}

        self._build_ui()
        self._update_status_line()

    def _build_ui(self):
        self.option_add("*Menu.Background", THEME["bg"])
        self.option_add("*Menu.Foreground", THEME["text"])
        self.option_add("*Menu.activeBackground", THEME["panel"])
        self.option_add("*Menu.activeForeground", THEME["text"])
        menubar = tk.Menu(self, bg=THEME["bg"], fg=THEME["text"], activebackground=THEME["panel"], activeforeground=THEME["text"], tearoff=0)
        load_menu = tk.Menu(menubar, tearoff=0)
        load_menu.add_command(label="Load Project", command=self.load_project)
        load_menu.add_separator()
        load_menu.add_command(label="Load Sprites", command=self.load_sprites)
        load_menu.add_command(label="Load Backgrounds", command=self.load_backgrounds)
        load_menu.add_command(label="Load Songs", command=self.load_songs)
        load_menu.add_separator()
        load_menu.add_command(label="Load Room JSON", command=self.load_room_json)
        load_menu.add_command(label="Load Rooms.h", command=self.load_rooms_header)
        load_menu.add_command(label="Load Tilemaps.h", command=self.load_tilemaps_header)

        save_menu = tk.Menu(menubar, tearoff=0)
        save_menu.add_command(label="Save Project", command=self.save_project)
        save_menu.add_command(label="Save Room JSON", command=self.save_room_json)

        export_menu = tk.Menu(menubar, tearoff=0)
        export_menu.add_command(label="Export Rooms.h", command=self.export_rooms_header)
        export_menu.add_command(label="Export Program (.masa)", command=self.export_program)
        export_menu.add_command(label="Export Tilemaps.h", command=self.export_tilemaps_header)

        project_menu = tk.Menu(menubar, tearoff=0)
        project_menu.add_command(label="New Project", command=self.new_project)

        docs_menu = tk.Menu(menubar, tearoff=0)
        docs_menu.add_command(label="MASA API", command=self.show_masa_text_docs)

        templates_menu = tk.Menu(menubar, tearoff=0)
        templates_menu.add_command(label="Mover + Rebotar", command=lambda: self.insert_template("bounce"))
        templates_menu.add_command(label="Rotar + Escalar", command=lambda: self.insert_template("rotate_scale"))
        templates_menu.add_command(label="Texto + HUD", command=lambda: self.insert_template("hud_text"))
        templates_menu.add_command(label="Input Control", command=lambda: self.insert_template("input"))
        templates_menu.add_command(label="Colision + Señal", command=lambda: self.insert_template("collision_signal"))
        templates_menu.add_command(label="RPG Textbox", command=lambda: self.insert_template("rpg_text"))
        templates_menu.add_command(label="Alarma (Timer)", command=lambda: self.insert_template("alarm"))
        templates_menu.add_command(label="Room Especifico", command=lambda: self.insert_template("room_goto"))
        templates_menu.add_command(label="Boton -> Accion", command=lambda: self.insert_template("button_action"))
        templates_menu.add_command(label="Input + Room + Textbox", command=lambda: self.insert_template("input_room_textbox"))
        templates_menu.add_command(label="Alarma + Spawn", command=lambda: self.insert_template("alarm_spawn"))
        templates_menu.add_command(label="Aceleracion / Desaceleracion", command=lambda: self.insert_template("accel_decel"))
        templates_menu.add_command(label="Destruir Objeto", command=lambda: self.insert_template("destroy_object"))

        menubar.add_cascade(label="Project", menu=project_menu)
        menubar.add_cascade(label="Load", menu=load_menu)
        menubar.add_cascade(label="Save", menu=save_menu)
        menubar.add_cascade(label="Export", menu=export_menu)
        menubar.add_cascade(label="Docs", menu=docs_menu)
        menubar.add_cascade(label="Templates", menu=templates_menu)
        menubar.add_command(label="TileMap Editor", command=self.open_tilemap_editor)
        self.config(menu=menubar)

        header = tk.Frame(self, bg=THEME["bg"])
        header.pack(fill="x", padx=8, pady=(6, 0))
        self.logo_image = None
        logo_path = os.path.join(PROJECT_ROOT, "mofongo_logo.png")
        if os.path.isfile(logo_path):
            try:
                self.logo_image = tk.PhotoImage(file=logo_path)
            except Exception:
                self.logo_image = None
        if self.logo_image:
            tk.Label(header, image=self.logo_image, bg=THEME["bg"]).pack(side="left")
            try:
                self.iconphoto(False, self.logo_image)
            except Exception:
                pass
        tk.Label(
            header,
            text="MOFONGO32 Engine",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=("Helvetica", 14, "bold"),
        ).pack(side="left", padx=8)
        tk.Button(header, text="Flash Game", command=self.open_flash_game).pack(side="right", padx=6)
        tk.Button(header, text="Test", command=self.run_test).pack(side="right", padx=6)
        tk.Button(header, text="Stop", command=self.stop_test).pack(side="right", padx=6)

        main = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", bg=THEME["bg"])
        main.pack(fill="both", expand=True, padx=8, pady=6)

        left = tk.Frame(main, bg=THEME["bg"])
        main.add(left, width=360)

        right = tk.Frame(main, bg=THEME["bg"])
        main.add(right)

        # Left: project/object controls
        tk.Label(left, text="Project Name").pack(anchor="w")
        self.project_name = tk.StringVar(value=self.project["name"])
        tk.Entry(left, textvariable=self.project_name).pack(fill="x", pady=(0, 6))

        tk.Label(left, text="Background Index").pack(anchor="w")
        self.bg_index = tk.StringVar(value=str(self.project["background_index"]))
        self.bg_color_var = tk.StringVar(value=str(self.project.get("background_color", 12)))
        tk.Entry(left, textvariable=self.bg_index).pack(fill="x", pady=(0, 10))

        row = tk.Frame(left, bg=THEME["bg"])
        row.pack(fill="x")
        tk.Button(row, text="Add Object", command=self.add_object).pack(side="left")
        tk.Button(row, text="Delete Object", command=self.delete_object).pack(side="left", padx=6)

        tk.Label(left, text="Objects").pack(anchor="w", pady=(8, 2))
        self.obj_list = tk.Listbox(left, height=15, exportselection=False)
        self.obj_list.pack(fill="both", expand=False)
        self.obj_list.bind("<<ListboxSelect>>", lambda _e: self.select_object())

        props = tk.LabelFrame(left, text="Object Properties", bg=THEME["bg"], fg=THEME["text"])
        props.pack(fill="both", expand=True, pady=(8, 0))

        self.obj_name = tk.StringVar()
        self.obj_x = tk.StringVar()
        self.obj_y = tk.StringVar()
        self.obj_mode = tk.StringVar(value="normal")
        self.idle_frames = tk.StringVar()
        self.walk_frames = tk.StringVar()
        self.run_frames = tk.StringVar()
        self.jump_frames = tk.StringVar()
        self.idle_fps = tk.StringVar(value="8")
        self.walk_fps = tk.StringVar(value="8")
        self.run_fps = tk.StringVar(value="10")
        self.jump_fps = tk.StringVar(value="8")
        self.start_state = tk.StringVar(value="idle")
        self.angle = tk.StringVar(value="0")
        self.scale = tk.StringVar(value="1.0")
        self.obj_persistent = tk.BooleanVar(value=False)

        self._row(props, "Name", self.obj_name)
        self._row(props, "X", self.obj_x)
        self._row(props, "Y", self.obj_y)
        self._row(props, "Draw Mode", self.obj_mode, combo=["normal", "rotated", "scaled"])
        self._row(props, "Start State", self.start_state, combo=["idle", "walk", "run", "jump"])
        self._row(props, "Idle Frames", self.idle_frames)
        self._row(props, "Walk Frames", self.walk_frames)
        self._row(props, "Run Frames", self.run_frames)
        self._row(props, "Jump Frames", self.jump_frames)
        self._row(props, "Idle FPS", self.idle_fps)
        self._row(props, "Walk FPS", self.walk_fps)
        self._row(props, "Run FPS", self.run_fps)
        self._row(props, "Jump FPS", self.jump_fps)
        self._row(props, "Angle", self.angle)
        self._row(props, "Scale", self.scale)
        tk.Checkbutton(props, text="Persistent", variable=self.obj_persistent).pack(anchor="w", padx=6, pady=(4, 0))
        tk.Button(props, text="Apply Object Props", command=self.apply_object_props).pack(anchor="w", padx=6, pady=6)

        # Right: helper views, script editor, and integrated room editor
        right_split = tk.PanedWindow(right, orient="vertical", sashrelief="raised", bg=THEME["bg"])
        right_split.pack(fill="both", expand=True)

        top_right = tk.PanedWindow(right_split, orient="horizontal", sashrelief="raised", bg=THEME["bg"])
        right_split.add(top_right, height=320)

        frame_view = tk.LabelFrame(top_right, text="Sprite Frames", bg=THEME["bg"], fg=THEME["text"])
        top_right.add(frame_view, width=300)
        self.frames_list = tk.Listbox(frame_view, exportselection=False)
        self.frames_list.pack(fill="both", expand=True, padx=6, pady=6)

        script_view = tk.LabelFrame(top_right, text="Object Script (C++ snippet, update phase)", bg=THEME["bg"], fg=THEME["text"])
        top_right.add(script_view)
        self.script_text = tk.Text(
            script_view,
            bg=THEME["editor_bg"],
            fg=THEME["editor_text"],
            insertbackground=THEME["editor_text"]
        )
        self.script_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.script_text.bind("<<Modified>>", self.on_script_modified)
        self.script_text.bind("<KeyRelease>", self._on_script_keyrelease)
        self.script_text.bind("<Escape>", lambda _e: self._hide_autocomplete())
        self.script_text.bind("<Button-1>", lambda _e: self._hide_autocomplete())
        tk.Label(
            script_view,
            text="Use: obj.x / obj.y / obj.vx / obj.vy / obj.angle / obj.scale / obj.state",
            anchor="w"
        ).pack(fill="x", padx=6, pady=(0, 6))
        self.script_hint = tk.Label(script_view, text="Script: OK", bg=THEME["bg"], fg=THEME["text"], anchor="w")
        self.script_hint.pack(fill="x", padx=6, pady=(0, 6))
        self._init_autocomplete(script_view)
        self._init_script_highlight()

        console_view = tk.LabelFrame(top_right, text="Console", bg=THEME["bg"], fg=THEME["text"])
        top_right.add(console_view, width=260)
        self.console = tk.Text(console_view, height=10, bg="#000000", fg="#FFFFFF", insertbackground="#FFFFFF")
        self.console.pack(fill="both", expand=True, padx=6, pady=6)

        room_view = tk.LabelFrame(right_split, text="Room Editor (Integrated)", bg=THEME["bg"], fg=THEME["text"])
        right_split.add(room_view)

        room_controls = tk.Frame(room_view, bg=THEME["bg"])
        room_controls.pack(fill="x", padx=6, pady=4)

        tk.Label(room_controls, text="Room").grid(row=0, column=0, sticky="w")
        self.room_pick_var = tk.StringVar(value="0: room0")
        self.room_pick = ttk.Combobox(room_controls, textvariable=self.room_pick_var, state="readonly", width=18)
        self.room_pick.grid(row=0, column=1, sticky="w", padx=(6, 4))
        self.room_pick.bind("<<ComboboxSelected>>", lambda _e: self.on_room_pick_change())
        tk.Button(room_controls, text="+", width=3, command=self.add_room).grid(row=0, column=2, padx=2)
        tk.Button(room_controls, text="-", width=3, command=self.delete_room).grid(row=0, column=3, padx=2)
        tk.Button(room_controls, text="Rename", width=7, command=self.rename_room).grid(row=0, column=4, padx=(2, 8))

        tk.Label(room_controls, text="Background").grid(row=0, column=5, sticky="w", padx=(12, 0))
        self.bg_combo_var = tk.StringVar(value="none")
        self.bg_combo = ttk.Combobox(room_controls, textvariable=self.bg_combo_var, state="readonly", width=26)
        self.bg_combo.grid(row=0, column=6, sticky="w", padx=(6, 6))
        self.bg_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_bg_combo_change())

        tk.Label(room_controls, text="BG Color").grid(row=0, column=7, sticky="w")
        self.bg_color_combo = ttk.Combobox(room_controls, textvariable=self.bg_color_var, state="readonly", width=14)
        self.bg_color_combo.grid(row=0, column=8, sticky="w", padx=(6, 12))
        self.bg_color_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_bg_color_change())

        self.room_song_var = tk.StringVar(value="none")
        tk.Label(room_controls, text="Song").grid(row=0, column=9, sticky="w")
        self.song_combo = ttk.Combobox(room_controls, textvariable=self.room_song_var, state="readonly", width=20)
        self.song_combo.grid(row=0, column=10, sticky="w", padx=(6, 12))
        self.song_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_song_combo_change())

        tk.Label(room_controls, text="Room Object Props").grid(row=0, column=11, sticky="w")
        self.room_x = tk.StringVar(value="0")
        self.room_y = tk.StringVar(value="0")
        self.room_frame = tk.StringVar(value="0")
        self.room_mode = tk.StringVar(value="normal")
        self.room_angle = tk.StringVar(value="0")
        self.room_scale = tk.StringVar(value="1.0")
        tk.Entry(room_controls, textvariable=self.room_x, width=5).grid(row=0, column=12, padx=(6, 2))
        tk.Entry(room_controls, textvariable=self.room_y, width=5).grid(row=0, column=13, padx=2)
        tk.Entry(room_controls, textvariable=self.room_frame, width=5).grid(row=0, column=14, padx=2)
        ttk.Combobox(room_controls, textvariable=self.room_mode, values=["normal", "rotated", "scaled"], state="readonly", width=9).grid(row=0, column=15, padx=2)
        tk.Entry(room_controls, textvariable=self.room_angle, width=6).grid(row=0, column=16, padx=2)
        tk.Entry(room_controls, textvariable=self.room_scale, width=6).grid(row=0, column=17, padx=2)
        tk.Button(room_controls, text="Apply Room Props", command=self.apply_room_props).grid(row=0, column=18, padx=(8, 0))

        tk.Label(room_controls, text="Tilemap").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.room_tilemap_combo = ttk.Combobox(room_controls, textvariable=self.room_tilemap_index, state="readonly", width=26)
        self.room_tilemap_combo.grid(row=1, column=1, columnspan=4, sticky="w", padx=(6, 4), pady=(6, 0))
        self.room_tilemap_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_room_tilemap_change())

        room_body = tk.PanedWindow(room_view, orient="horizontal", sashrelief="raised", bg=THEME["bg"])
        room_body.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        room_objs = tk.LabelFrame(room_body, text="Room Objects", bg=THEME["bg"], fg=THEME["text"])
        room_body.add(room_objs, width=280)
        self.room_obj_list = tk.Listbox(room_objs, exportselection=False)
        self.room_obj_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.room_obj_list.bind("<<ListboxSelect>>", lambda _e: self.select_room_object())
        room_btns = tk.Frame(room_objs, bg=THEME["bg"])
        room_btns.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(room_btns, text="Add Selected", command=self.add_selected_object_to_room).pack(side="left")
        tk.Button(room_btns, text="Remove From Room", command=self.remove_selected_room_object).pack(side="left", padx=(6, 0))

        room_canvas_wrap = tk.LabelFrame(room_body, text="Canvas 320x200", bg=THEME["bg"], fg=THEME["text"])
        room_body.add(room_canvas_wrap)
        self.room_canvas = tk.Canvas(
            room_canvas_wrap,
            width=ROOM_W * CANVAS_SCALE,
            height=ROOM_H * CANVAS_SCALE,
            bg=THEME["panel"],
            highlightthickness=0,
        )
        self.room_canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.room_canvas.bind("<Button-1>", self.on_canvas_down)
        self.room_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.room_canvas.bind("<ButtonRelease-1>", self.on_canvas_up)

        self.status = tk.Label(self, text="Load sprites and backgrounds metadata to start.", bg=THEME["bg"], fg=THEME["text"])
        self.status.pack(fill="x", padx=8, pady=(0, 8))
        self.status2 = tk.Label(self, text="", bg=THEME["bg"], fg=THEME["text"])
        self.status2.pack(fill="x", padx=8, pady=(0, 8))
        self._ensure_rooms()
        self._load_room_to_fields(int(self.project.get("active_room", 0)))
        self.refresh_room_picker()
        self.refresh_bg_combo()
        self.refresh_song_combo()
        self.refresh_room_object_list()
        self.redraw_room_canvas()
        self._update_status_line()

    def show_masa_text_docs(self):
        win = tk.Toplevel(self)
        win.title("MASA API")
        win.configure(bg=THEME["bg"])
        win.geometry("720x520")
        win.minsize(520, 360)
        txt = tk.Text(
            win,
            bg=THEME["doc_panel"],
            fg=THEME["text"],
            wrap="word",
            insertbackground=THEME["text"],
            font=("Consolas", 10),
        )
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.tag_configure("title", foreground="#f4d35e", font=("Consolas", 12, "bold"))
        txt.tag_configure("section", foreground="#9ad1ff", font=("Consolas", 10, "bold"))
        txt.tag_configure("directive", foreground="#7CFCB2")
        txt.tag_configure("directive_name", foreground="#47e5bc", font=("Consolas", 10, "bold"))
        txt.tag_configure("note", foreground="#ffcf99")
        txt.tag_configure("muted", foreground="#b8c0cc")
        doc = (
            "MASA API (Object Script)\n"
            "\n"
            "Directives are parsed from the object script and exported to MASA.\n"
            "They render on top of the game, on the video board.\n"
            "\n"
            "Quick reference (common gameplay directives):\n"
            "  // MASA_ON_SIGNAL_STOP: signalSlot, target\n"
            "     Stops target movement when signalSlot is fired.\n"
            "  // MASA_ON_SIGNAL_SPAWN: signalSlot, obj, x, y, sprite\n"
            "     Spawns/enables obj on signalSlot at x,y with sprite.\n"
            "  // MASA_ON_SIGNAL_HUD_ADD: signalSlot, lifeDelta, scoreDelta, coinsDelta\n"
            "     Adds (or subtracts) HUD values when signalSlot is fired.\n"
            "  // MASA_COLLIDE: signalSlot, otherObject\n"
            "     Fires signalSlot when this object collides with otherObject.\n"
            "  // MASA_ON_SIGNAL_SHOW_TEXT: signalSlot, textSlot, x, y, color, [align], \"text\"\n"
            "     align: left(0), center(1), right(2)\n"
            "     Shows text on screen when signalSlot is fired.\n"
            "  // MASA_HUD_SET: life, score, coins\n"
            "     Initializes HUD counters.\n"
            "  // MASA_HUD: x, y, color\n"
            "  // MASA_HUD: x, y, color, align, bgColor, padX, padY, \"template\"\n"
            "     Enables and draws HUD at x,y (align: left/center/right).\n"
            "     template supports: {LIFE}, {SCORE}, {COINS}\n"
            "\n"
            "1) Simple text at the object's position:\n"
            "   // MASA_TEXT: \"Hello World\"\n"
            "\n"
            "2) Text with slot, position, color, and text:\n"
            "   // MASA_TEXT: 0, 12, 8, white, \"SCORE: 0000\"\n"
            "\n"
            "3) Text that follows the object (same position):\n"
            "   // MASA_TEXT: 1, x, y, yellow, \"HP: 10\"\n"
            "   // MASA_TEXT: \"HP: 10\"   (uses object position automatically)\n"
            "\n"
            "4) Clear a text slot:\n"
            "   // MASA_TEXT_CLEAR: 0\n"
            "\n"
            "RPG TextBox (single box, optional 2 lines with |):\n"
            "   // MASA_TEXTBOX: 0, 20, 130, 280, 60, darkgreen, \"Hello|Select an option\"\n"
            "   // MASA_TEXTBOX_CLEAR: 0\n"
            "\n"
            "Choices (use UP/DOWN + A/START to confirm):\n"
            "   // MASA_CHOICES: 0, 40, 160, yellow, 0, \"Yes|No|Maybe\"\n"
            "   // MASA_CHOICES_CLEAR: 0\n"
            "   // MASA_ON_SIGNAL_SOUND: 0, 1   (choice 0)\n"
            "   // MASA_ON_SIGNAL_SOUND: 1, 2   (choice 1)\n"
            "   // MASA_ON_SIGNAL_SOUND: 2, 3   (choice 2)\n"
            "   (baseSignal + choice index triggers signals)\n"
            "\n"
            "Slots:\n"
            "  - 0..3 (max 4 text entries)\n"
            "  - Reusing a slot replaces the previous text.\n"
            "\n"
            "Colors (name -> index):\n"
            "  black=0, darkgreen=1, green=2, lightgreen=3,\n"
            "  darkgray=4, gray=5, lightgray=6, white=15,\n"
            "  red=9, orange=10, yellow=11, blue=12,\n"
            "  cyan=13, magenta=14\n"
            "\n"
            "Limits:\n"
            "  - Max text length: 24 characters\n"
            "  - Coordinates are in 320x200 pixels\n"
            "\n"
            "Other MASA Script Directives (behavior):\n"
            "\n"
            "Enable default behavior block:\n"
            "  // MASA_BEHAVIOR: bounce_rotate_scale\n"
            "\n"
            "Velocity (pixels per frame @ 60fps):\n"
            "  // MASA_VEL: 1.2, 0.9\n"
            "  // MASA_VX: 1.2\n"
            "  // MASA_VY: 0.9\n"
            "\n"
            "Exporter pool hints:\n"
            "  // MASA_POOL_RESERVE: 12   (minimum exported clone count for this type)\n"
            "  // MASA_POOL_PRIORITY: 10  (higher types get pool budget first)\n"
            "\n"
            "Bounds (minX, maxX, minY, maxY):\n"
            "  // MASA_BOUNDS: 20, 300, 20, 180\n"
            "\n"
            "Rotation speed (degrees per frame @ 60fps):\n"
            "  // MASA_ROT_SPEED: 2.5\n"
            "\n"
            "Scale pulse (base, amplitude, speed):\n"
            "  // MASA_SCALE: 0.85, 0.25, 4.0\n"
            "\n"
            "Enable input movement (speed in pixels per frame @ 60fps):\n"
            "  // MASA_INPUT: 1.6\n"
            "\n"
            "Input signals (bind signals to button events):\n"
            "  // MASA_PRESSED_BTN_A: 0      (just pressed)\n"
            "  // MASA_PRESS_BTN_A: 1        (held)\n"
            "  // MASA_RELEASED_BTN_A: 2     (released)\n"
            "Buttons: UP, DOWN, LEFT, RIGHT, A, B, X, Y, START, SELECT, L, R\n"
            "\n"
            "Background scroll:\n"
            "  // MASA_BG_SCROLL_X: 0.5   (pixels per frame @ 60fps)\n"
            "  // MASA_BG_SCROLL_Y: 0.0\n"
            "\n"
            "HUD (life/score/coins):\n"
            "  // MASA_HUD: 8, 8, white\n"
            "  // MASA_HUD: 160, 8, white, center, darkgray, 3, 2, \"L:{LIFE}  S:{SCORE}\"\n"
            "  // MASA_HUD_SET: 3, 0, 0   (life, score, coins)\n"
            "  // MASA_HUD_ADD: 0, 100, 1 (add score/coins)\n"
            "\n"
            "Runtime SFX (no FamiTracker required):\n"
            "  // MASA_BEEP_SQUARE: C6, 80\n"
            "  // MASA_BEEP_NOISE: C3, 60\n"
            "  // MASA_ON_SIGNAL_BEEP_SQUARE: 0, C6, 80\n"
            "  // MASA_ON_SIGNAL_BEEP_NOISE: 1, C3, 60\n"
            "\n"
            "Variables (32 per object, 64 global):\n"
            "  // MASA_VAR_SET: global, 0, 100\n"
            "  // MASA_VAR_ADD: global, 0, 5\n"
            "  // MASA_VAR_SET: self, 1, 10\n"
            "  // MASA_VAR_TEXT: 0, 8, 20, white, global, 0, \"SCORE: \"\n"
            "  // MASA_VARF_SET: global, 1, 3.14\n"
            "  // MASA_VARF_ADD: global, 1, 0.05\n"
            "  // MASA_VARF_TEXT: 1, 8, 32, yellow, global, 1, \"SPD: \"\n"
            "  // MASA_INC: global, 0\n"
            "  // MASA_DEC: self, 1, 2\n"
            "  // MASA_IF_EQ: global, 0, 100, 3\n"
            "  // MASA_IF_GTF: global, 1, 2.5, 4\n"
            "  // MASA_VAR_CLAMP: global, 0, 0, 9999\n"
            "  // MASA_VARF_CLAMP: global, 1, 0.0, 10.0\n"
            "  // MASA_VAR_RAND: global, 2, 0, 10\n"
            "  // MASA_VARF_LERP: global, 3, 0.0, 1.0, 0.5\n"
            "  // MASA_VAR_MIN: global, 0, 500\n"
            "  // MASA_VAR_MAX: global, 0, 999\n"
            "  // MASA_VARF_MIN: global, 1, 2.0\n"
            "  // MASA_VARF_MAX: global, 1, 8.0\n"
            "  // MASA_VARF_SIN: global, 4, 45.0\n"
            "  // MASA_VARF_COS: global, 5, 90.0\n"
            "  // MASA_STR_SET: global, 0, \"HELLO\"\n"
            "  // MASA_STR_TEXT: 2, 8, 44, white, global, 0, \"MSG: \"\n"
            "  // MASA_SWITCH: global, 0, 7, 5\n"
            "\n"
            "Alarms:\n"
            "  // MASA_START_ALARM: 0, 1000, repeat\n"
            "  // MASA_STOP_ALARM: 0\n"
            "  // IF_MASA_ALARM_RINGS: 0, 3   (fires signal 3)\n"
            "\n"
            "Music:\n"
            "  // MASA_PLAY_MUSIC: 0\n"
            "  // MASA_PLAY_MUSIC: my_song_name\n"
            "  // MASA_STOP_MUSIC\n"
            "  // MASA_PAUSE_MUSIC\n"
            "  // MASA_SONG_LOOP: 1\n"
            "  // MASA_IF_MUSIC_IS_PLAYING: 2   (fires signal 2)\n"
            "\n"
            "Animation (uses Idle Frames + Idle FPS):\n"
            "  - Add Idle Frames list (e.g. 0,1,2,3)\n"
            "  - Set Idle FPS to control animation speed\n"
            "\n"
            "Shapes (persistent, drawn every frame):\n"
            "  // MASA_RECT: 0, 10, 10, 60, 30, white\n"
            "  // MASA_FILL_RECT: 1, 80, 10, 40, 20, green\n"
            "  // MASA_LINE: 2, 0, 0, 319, 199, yellow\n"
            "  // MASA_TRI: 3, 160, 20, 120, 80, 200, 80, red\n"
            "  // MASA_CIRCLE: 4, 160, 120, 30, blue\n"
            "  // MASA_SHAPE_CLEAR: 0\n"
            "\n"
            "Spawn / Destroy (immediate):\n"
            "  // MASA_SPAWN: objId, x, y, frame\n"
            "  // MASA_DESTROY: objId\n"
            "\n"
            "Collisions + Signals:\n"
            "  // MASA_HITBOX: 32, 32                (optional, defaults 16x16 centered)\n"
            "  // MASA_HITBOX: 32, 32, 0, -6         (optional offset x,y from sprite center)\n"
            "  // MASA_COLLIDE: 0, obj_enemy   (signal slot 0 when colliding)\n"
            "  // MASA_ON_SIGNAL_DESTROY: 0, self\n"
            "  // MASA_ON_SIGNAL_DESTROY: 0, obj_enemy\n"
            "  // MASA_ON_SIGNAL_SPAWN: 0, 3, 100, 100, 5\n"
            "  // MASA_ON_SIGNAL_SOUND: 0, 2\n"
            "  // MASA_ON_SIGNAL_STOP: 0, self\n"
            "  // MASA_ON_SIGNAL_ROOM_NEXT: 0\n"
            "  // MASA_ON_SIGNAL_TEXTBOX: signalSlot, boxSlot, x, y, w, h, color, \"Text|Line2\"\n"
            "  // MASA_ON_SIGNAL_CHOICES: signalSlot, choiceSlot, x, y, color, baseSignal, \"Yes|No\"\n"
            "  // MASA_ON_SIGNAL_TEXTBOX_CLEAR: signalSlot, boxSlot\n"
            "  // MASA_ON_SIGNAL_CHOICES_CLEAR: signalSlot, choiceSlot\n"
            "  // MASA_ON_SIGNAL_SET_INPUT: signalSlot, target, speed\n"
            "\n"
            "Rooms (high level):\n"
            "  - Use the Room Editor to place objects per room\n"
            "  - Use Song dropdown per room to assign music\n"
            "  - Use Background dropdown per room to set background\n"
            "\n"
            "Audio (MASA):\n"
            "  - Room Song is auto-played when the room is active\n"
            "  - Use exported songs.h and select in Room Editor\n"
            "\n"
            "Persistence:\n"
            "  - Check 'Persistent' on an object to keep it across rooms\n"
            "  - Non-persistent objects are removed on room switch\n"
        )
        txt.insert("1.0", doc)

        txt.tag_add("title", "1.0", "1.end")
        for line_idx, line in enumerate(doc.splitlines(), start=1):
            start = f"{line_idx}.0"
            end = f"{line_idx}.end"
            if not line.strip():
                continue
            if line.endswith(":") and not line.lstrip().startswith("//"):
                txt.tag_add("section", start, end)
            if line.lstrip().startswith("//"):
                txt.tag_add("directive", start, end)
                m = re.search(r"//\s*((?:IF_)?MASA_[A-Z0-9_]+):", line)
                if m:
                    name_start = f"{line_idx}.{m.start(1)}"
                    name_end = f"{line_idx}.{m.end(1)}"
                    txt.tag_add("directive_name", name_start, name_end)
            elif line.lstrip().startswith("- ") or "Defaults" in line or "optional" in line:
                txt.tag_add("muted", start, end)
            elif "Fires" in line or "Adds" in line or "Stops" in line or "Spawns" in line or "Shows" in line or "Enables" in line or "Initializes" in line:
                txt.tag_add("note", start, end)

        txt.configure(state="disabled")

    def _row(self, parent, label, var, combo=None):
        row = tk.Frame(parent, bg=THEME["bg"])
        row.pack(fill="x", padx=6, pady=2)
        tk.Label(row, text=label, width=11, anchor="w").pack(side="left")
        if combo:
            cb = ttk.Combobox(row, textvariable=var, values=combo, state="readonly")
            cb.pack(side="left", fill="x", expand=True)
        else:
            tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    def set_status(self, s):
        self.status.configure(text=s)

    def log(self, msg: str):
        try:
            self.console.insert("end", msg + "\n")
            self.console.see("end")
        except Exception:
            pass

    def _init_autocomplete(self, parent):
        self.ac_box = tk.Listbox(parent, height=6, bg=THEME["panel"], fg=THEME["text"], selectbackground=THEME["accent"])
        self.ac_box.place_forget()
        self.ac_visible = False
        self.ac_items = []
        self.ac_box.bind("<Return>", self._insert_autocomplete)
        self.ac_box.bind("<Double-Button-1>", self._insert_autocomplete)

    def _init_script_highlight(self):
        self.script_text.tag_configure("comment", foreground=THEME["editor_comment"])
        self.script_text.tag_configure("masa", foreground=THEME["editor_masa"])
        self.script_text.tag_configure("kw", foreground=THEME["editor_kw"])

    def _apply_script_highlight(self):
        try:
            text = self.script_text.get("1.0", "end-1c")
        except Exception:
            return
        for tag in ("comment", "masa", "kw"):
            self.script_text.tag_remove(tag, "1.0", "end")

        for li, line in enumerate(text.splitlines(), start=1):
            base = f"{li}.0"
            # Comments
            cidx = line.find("//")
            if cidx >= 0:
                self.script_text.tag_add("comment", f"{base}+{cidx}c", f"{base}+{len(line)}c")
            # MASA directives (highlight even inside comments)
            for m in re.finditer(r"MASA_[A-Z0-9_]+", line):
                self.script_text.tag_add("masa", f"{base}+{m.start()}c", f"{base}+{m.end()}c")
            # Keywords
            for m in re.finditer(r"\bobj\.(x|y|vx|vy|angle|scale|state)\b", line):
                self.script_text.tag_add("kw", f"{base}+{m.start()}c", f"{base}+{m.end()}c")
            for m in re.finditer(r"\broom_(cycle_next|set)\b", line):
                self.script_text.tag_add("kw", f"{base}+{m.start()}c", f"{base}+{m.end()}c")
        self.script_text.tag_raise("masa")

    def _on_script_keyrelease(self, event):
        if event.keysym in ("Escape", "Up", "Down", "Return", "Tab"):
            return
        if event.char == "" and event.keysym not in ("BackSpace", "Delete"):
            return
        self._update_autocomplete()

    def _get_masa_prefix(self):
        try:
            line = self.script_text.get("insert linestart", "insert")
        except Exception:
            return None, None
        m = re.search(r"(MASA_[A-Z0-9_]*)$", line)
        if not m:
            return None, None
        return m.group(1), m.start(1)

    def _update_autocomplete(self):
        prefix, start_idx = self._get_masa_prefix()
        if not prefix:
            self._hide_autocomplete()
            return
        matches = [d for d in MASA_DIRECTIVES if d.startswith(prefix)]
        if not matches:
            self._hide_autocomplete()
            return
        self.ac_box.delete(0, "end")
        for item in matches[:24]:
            self.ac_box.insert("end", item)
        self.ac_items = matches[:24]
        self.ac_box.selection_clear(0, "end")
        self.ac_box.selection_set(0)
        self._show_autocomplete()

    def _resolve_var_target(self, token, self_id, obj_name_to_id):
        t = str(token).strip().lower()
        if t in ("g", "global", "globals"):
            return 0, 0
        if t in ("self", "me", "this"):
            return 1, int(self_id)
        if t.isdigit() or (t.startswith("-") and t[1:].isdigit()):
            try:
                return 1, int(t) & 0xFF
            except Exception:
                return 1, int(self_id)
        return 1, int(obj_name_to_id.get(str(token), self_id))

    def _show_autocomplete(self):
        try:
            bbox = self.script_text.bbox("insert")
        except Exception:
            bbox = None
        if not bbox:
            self._hide_autocomplete()
            return
        x, y, w, h = bbox
        self.ac_box.place(x=x + 6, y=y + h + 6)
        self.ac_visible = True

    def _hide_autocomplete(self):
        if hasattr(self, "ac_box"):
            self.ac_box.place_forget()
        self.ac_visible = False

    def _insert_autocomplete(self, _event=None):
        if not self.ac_visible:
            return "break"
        try:
            sel = self.ac_box.curselection()
            if not sel:
                return "break"
            choice = self.ac_box.get(sel[0])
        except Exception:
            return "break"
        prefix, start_idx = self._get_masa_prefix()
        if prefix is None:
            return "break"
        try:
            line_start = self.script_text.index("insert linestart")
            start = f"{line_start}+{start_idx}c"
            self.script_text.delete(start, "insert")
            self.script_text.insert(start, choice)
        except Exception:
            pass
        self._hide_autocomplete()
        return "break"

    def run_test(self):
        if self.test_proc and self.test_proc.poll() is None:
            self.log("Test already running.")
            return
        try:
            self._commit_ui_state()
            self._save_current_room_fields()
            self._ensure_rooms()
            out_dir = os.path.join(PROJECT_ROOT, "Programs")
            os.makedirs(out_dir, exist_ok=True)
            masa_path = os.path.join(out_dir, f"{self.project.get('name','game')}_test.masa")
            ingr_path = os.path.splitext(masa_path)[0] + ".ingr"
            try:
                self._save_ingr(ingr_path)
                self.log(f"Saved test project: {os.path.basename(ingr_path)}")
            except Exception as e:
                self.log(f"Save test .ingr failed: {e}")
            if not self._export_program_to(masa_path, silent=True):
                return
            emu_path = os.path.join(PROJECT_ROOT, "tools", "mofongo_emulator.py")
            cmd = [sys.executable, emu_path, ingr_path, masa_path]
            self.test_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.log(f"Running emulator: {os.path.basename(masa_path)}")
            self._start_test_reader()
        except Exception as e:
            self.log(f"Test failed: {e}")

    def _start_test_reader(self):
        if not self.test_proc or self.test_proc.stdout is None:
            return

        def _reader():
            try:
                for line in self.test_proc.stdout:
                    self.log(line.rstrip())
            except Exception:
                pass

        self.test_reader = threading.Thread(target=_reader, daemon=True)
        self.test_reader.start()

    def open_flash_game(self):
        try:
            tools_dir = os.path.join(PROJECT_ROOT, "tools")
            bat_path = os.path.join(tools_dir, "run_spiffs_builder.bat")
            gui_path = os.path.join(tools_dir, "spiffs_builder_gui.py")
            if os.path.isfile(bat_path):
                subprocess.Popen([bat_path], cwd=tools_dir)
                self.log("Opening SPIFFS Builder (Flash Game)...")
                return
            if os.path.isfile(gui_path):
                subprocess.Popen([sys.executable, gui_path], cwd=tools_dir)
                self.log("Opening SPIFFS Builder (Flash Game)...")
                return
            self.log("Flash Game failed: tools/spiffs_builder_gui.py not found.")
        except Exception as e:
            self.log(f"Flash Game failed: {e}")

    def stop_test(self):
        if self.test_proc and self.test_proc.poll() is None:
            try:
                self.test_proc.terminate()
                self.log("Test stopped.")
            except Exception:
                pass
        self.test_proc = None

    def insert_template(self, name: str):
        templates = {
            "bounce": (
                "// MASA_BEHAVIOR: bounce_rotate_scale\n"
                "// MASA_VEL: 1.2,0.9\n"
                "// MASA_BOUNDS: 20,300,20,180\n"
            ),
            "rotate_scale": (
                "// MASA_ROT_SPEED: 2.5\n"
                "// MASA_SCALE: 0.85,0.25,4.0\n"
            ),
            "hud_text": (
                "// MASA_HUD_SET: 3, 0, 0\n"
                "// MASA_HUD: 160, 8, white, center, darkgray, 3, 2, \"L:{LIFE}  S:{SCORE}  C:{COINS}\"\n"
                "// MASA_HUD_ADD: 0, 100, 0\n"
            ),
            "input": (
                "// MASA_INPUT: 1.6\n"
            ),
            "collision_signal": (
                "// MASA_HITBOX: 32, 32\n"
                "// MASA_COLLIDE: 0, obj_enemy\n"
                "// MASA_ON_SIGNAL_DESTROY: 0, self\n"
            ),
            "rpg_text": (
                "// MASA_TEXTBOX: 0, 20, 130, 280, 60, darkgreen, \"Hello|Choose an option\"\n"
                "// MASA_CHOICES: 0, 40, 160, yellow, 0, \"Yes|No|Maybe\"\n"
                "// MASA_ON_SIGNAL_SOUND: 0, 1\n"
                "// MASA_ON_SIGNAL_SOUND: 1, 2\n"
                "// MASA_ON_SIGNAL_SOUND: 2, 3\n"
            ),
            "alarm": (
                "// MASA_START_ALARM: 0, 1500, repeat\n"
                "// IF_MASA_ALARM_RINGS: 0, 3\n"
                "// MASA_ON_SIGNAL_SOUND: 3, 1\n"
            ),
            "room_goto": (
                "// MASA_COLLIDE: 0, obj_portal\n"
                "// MASA_ON_SIGNAL_ROOM_GOTO: 0, 1\n"
            ),
            "button_action": (
                "// MASA_PRESSED_BTN_A: 1\n"
                "// MASA_ON_SIGNAL_SOUND: 1, 2\n"
            ),
            "input_room_textbox": (
                "// MASA_INPUT: 1.6\n"
                "// MASA_HITBOX: 32, 32\n"
                "// MASA_COLLIDE: 0, obj_portal\n"
                "// MASA_ON_SIGNAL_TEXTBOX: 0, 0, 0, 0, 320, 60, black, \"Enter next room?\"\n"
                "// MASA_ON_SIGNAL_CHOICES: 0, 0, 40, 40, white, 1, \"Yes|No\"\n"
                "// MASA_ON_SIGNAL_ROOM_GOTO: 1, 1\n"
                "// MASA_ON_SIGNAL_TEXTBOX_CLEAR: 1, 0\n"
                "// MASA_ON_SIGNAL_CHOICES_CLEAR: 1, 0\n"
                "// MASA_ON_SIGNAL_TEXTBOX_CLEAR: 2, 0\n"
                "// MASA_ON_SIGNAL_CHOICES_CLEAR: 2, 0\n"
            ),
            "alarm_spawn": (
                "// MASA_START_ALARM: 0, 1500, repeat\n"
                "// IF_MASA_ALARM_RINGS: 0, 3\n"
                "// MASA_ON_SIGNAL_SPAWN: 3, obj_fx, 160, 100, 5\n"
            ),
            "accel_decel": (
                "// MASA_ACCEL: 0.08, 0.92\n"
                "// MASA_BOUNDS: 20,300,20,180\n"
                "// MASA_TEXT: 0, 8, 8, white, \"ACCEL\"\n"
            ),
            "destroy_object": (
                "// MASA_ON_SIGNAL_DESTROY: 0, self\n"
                "// MASA_ON_SIGNAL_SOUND: 0, 1\n"
            ),
        }
        snippet = templates.get(name, "")
        if not snippet:
            return
        try:
            current = self.script_text.get("1.0", "end-1c").strip()
            if current:
                self.script_text.insert("end", "\n\n" + snippet)
            else:
                self.script_text.insert("1.0", snippet)
            self.script_text.edit_modified(True)
        except Exception:
            pass

    def on_script_modified(self, _event=None):
        if not self.script_text.edit_modified():
            return
        try:
            script = self.script_text.get("1.0", "end-1c")
            issues = self._validate_script_text(script)
            if issues:
                msg = "Script warnings: " + "; ".join(issues[:3])
                self.script_hint.config(text=msg)
            else:
                self.script_hint.config(text="Script: OK")
            self._apply_script_highlight()
        finally:
            self.script_text.edit_modified(False)

    def _validate_script_text(self, script_text: str):
        issues = []
        for line in (script_text or "").splitlines():
            line = line.strip()
            if not line.startswith("//"):
                continue
            if line.startswith("// MASA_VEL:"):
                if not re.search(r"//\s*MASA_VEL:\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VEL needs two numbers")
            elif line.startswith("// MASA_VEL_RANDOM:"):
                if not re.search(r"//\s*MASA_VEL_RANDOM:\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VEL_RANDOM needs min,max")
            elif line.startswith("// MASA_VX:"):
                if not re.search(r"//\s*MASA_VX:\s*[-\d.]+", line):
                    issues.append("MASA_VX needs one number")
            elif line.startswith("// MASA_VY:"):
                if not re.search(r"//\s*MASA_VY:\s*[-\d.]+", line):
                    issues.append("MASA_VY needs one number")
            elif line.startswith("// MASA_BOUNDS:"):
                if not re.search(r"//\s*MASA_BOUNDS:\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_BOUNDS needs four numbers")
            elif line.startswith("// MASA_ROT_SPEED:"):
                if not re.search(r"//\s*MASA_ROT_SPEED:\s*[-\d.]+", line):
                    issues.append("MASA_ROT_SPEED needs one number")
            elif line.startswith("// MASA_SCALE:"):
                if not re.search(r"//\s*MASA_SCALE:\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_SCALE needs three numbers")
            elif line.startswith("// MASA_ROTATE:"):
                if not re.search(r"//\s*MASA_ROTATE:\s*[-\d.]+", line):
                    issues.append("MASA_ROTATE needs one number")
            elif line.startswith("// MASA_THRUST:"):
                if not re.search(r"//\s*MASA_THRUST:\s*[-\d.]+", line):
                    issues.append("MASA_THRUST needs one number")
            elif line.startswith("// MASA_WRAP:"):
                if not re.search(r"//\s*MASA_WRAP:\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_WRAP needs four numbers")
            elif line.startswith("// MASA_NO_WRAP:"):
                if not re.search(r"//\s*MASA_NO_WRAP:\s*[01]", line):
                    issues.append("MASA_NO_WRAP needs 0 or 1")
            elif line.startswith("// MASA_BOUNCE:"):
                if not re.search(r"//\s*MASA_BOUNCE:\s*[01]", line):
                    issues.append("MASA_BOUNCE needs 0 or 1")
            elif line.startswith("// MASA_POOL_RESERVE:"):
                if not re.search(r"//\s*MASA_POOL_RESERVE:\s*\d+", line):
                    issues.append("MASA_POOL_RESERVE needs one integer")
            elif line.startswith("// MASA_POOL_PRIORITY:"):
                if not re.search(r"//\s*MASA_POOL_PRIORITY:\s*-?\d+", line):
                    issues.append("MASA_POOL_PRIORITY needs one integer")
            elif line.startswith("// MASA_SPRITE_INDEX:"):
                if not re.search(r"//\s*MASA_SPRITE_INDEX:\s*\d+", line):
                    issues.append("MASA_SPRITE_INDEX needs one number")
            elif line.startswith("// MASA_IMAGE_SPEED:"):
                if not re.search(r"//\s*MASA_IMAGE_SPEED:\s*[-\d.]+", line):
                    issues.append("MASA_IMAGE_SPEED needs one number")
            elif line.startswith("// MASA_ANIMATION_FRAMES:"):
                if not re.search(r"//\s*MASA_ANIMATION_FRAMES:\s*.+", line):
                    issues.append("MASA_ANIMATION_FRAMES needs list")
            elif line.startswith("// MASA_START_POS_X:"):
                if not re.search(r"//\s*MASA_START_POS_X:\s*[-\d.]+", line):
                    issues.append("MASA_START_POS_X needs number")
            elif line.startswith("// MASA_START_POS_Y:"):
                if not re.search(r"//\s*MASA_START_POS_Y:\s*[-\d.]+", line):
                    issues.append("MASA_START_POS_Y needs number")
            elif line.startswith("// MASA_ACCEL:"):
                if not re.search(r"//\s*MASA_ACCEL:\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_ACCEL needs accel,friction")
            elif line.startswith("// MASA_INPUT:"):
                if not re.search(r"//\s*MASA_INPUT:\s*[-\d.]+", line):
                    issues.append("MASA_INPUT needs one number")
            elif line.startswith("// MASA_TEXT_CLEAR:"):
                if not re.search(r"//\s*MASA_TEXT_CLEAR:\s*\d+", line):
                    issues.append("MASA_TEXT_CLEAR needs slot 0..3")
            elif line.startswith("// MASA_SHOW_TEXT_CLEAR:"):
                if not re.search(r"//\s*MASA_SHOW_TEXT_CLEAR:\s*\d+", line):
                    issues.append("MASA_SHOW_TEXT_CLEAR needs slot 0..3")
            elif line.startswith("// MASA_TEXT:"):
                # Allow either simple text or full params.
                if re.search(r"//\s*MASA_TEXT:\s*\".*\"", line):
                    pass
                elif re.search(r"//\s*MASA_TEXT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*.+", line):
                    pass
                else:
                    issues.append("MASA_TEXT format invalid")
            elif line.startswith("// MASA_SHOW_TEXT:"):
                if re.search(r"//\s*MASA_SHOW_TEXT:\s*\".*\"", line):
                    pass
                elif re.search(r"//\s*MASA_SHOW_TEXT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*.+", line):
                    pass
                else:
                    issues.append("MASA_SHOW_TEXT format invalid")
            elif line.startswith("// MASA_HITBOX:"):
                if not re.search(r"//\s*MASA_HITBOX:\s*[-\d.]+\s*,\s*[-\d.]+(\s*,\s*[-\d.]+\s*,\s*[-\d.]+)?", line):
                    issues.append("MASA_HITBOX needs width,height[,offsetX,offsetY]")
            elif line.startswith("// MASA_COLLIDE:"):
                if not re.search(r"//\s*MASA_COLLIDE:\s*\d+\s*,\s*.+", line):
                    issues.append("MASA_COLLIDE needs slot, other_object")
            elif line.startswith("// MASA_ON_SIGNAL_DESTROY:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_DESTROY:\s*\d+(\s*,\s*.+)?", line):
                    issues.append("MASA_ON_SIGNAL_DESTROY needs slot[, target]")
            elif line.startswith("// MASA_ON_SIGNAL_SPAWN:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SPAWN:\s*\d+\s*,\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_SPAWN needs slot,obj,x,y[,frame]")
            elif line.startswith("// MASA_ON_SIGNAL_SOUND:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SOUND:\s*\d+\s*,\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_SOUND needs slot,soundId")
            elif line.startswith("// MASA_ON_SIGNAL_BEEP:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_BEEP:\s*\d+\s*,\s*[^,]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_ON_SIGNAL_BEEP needs slot,note,timeMs")
            elif line.startswith("// MASA_ON_SIGNAL_BEEP_SQUARE:") or line.startswith("// MASA_ON_SIGNAL_BEEP_NOISE:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_BEEP_(?:SQUARE|NOISE):\s*\d+\s*,\s*[^,]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_ON_SIGNAL_BEEP_SQUARE/NOISE needs slot,note,timeMs")
            elif line.startswith("// MASA_ON_SIGNAL_ROOM_NEXT:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_ROOM_NEXT:\s*\d+", line):
                    issues.append("MASA_ON_SIGNAL_ROOM_NEXT needs slot")
            elif line.startswith("// MASA_ON_SIGNAL_ROOM_GOTO:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_ROOM_GOTO:\s*\d+\s*,\s*\d+", line):
                    issues.append("MASA_ON_SIGNAL_ROOM_GOTO needs slot,room")
            elif line.startswith("// MASA_ON_SIGNAL_SPAWN_BULLET:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SPAWN_BULLET:\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_SPAWN_BULLET needs slot,obj,speed,offset")
            elif line.startswith("// MASA_BEEP:"):
                if not re.search(r"//\s*MASA_BEEP:\s*[^,]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_BEEP needs note,timeMs")
            elif line.startswith("// MASA_BEEP_SQUARE:") or line.startswith("// MASA_BEEP_NOISE:"):
                if not re.search(r"//\s*MASA_BEEP_(?:SQUARE|NOISE):\s*[^,]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_BEEP_SQUARE/NOISE needs note,timeMs")
            elif line.startswith("// MASA_ON_SIGNAL_STOP:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_STOP:\s*\d+(\s*,\s*.+)?", line):
                    issues.append("MASA_ON_SIGNAL_STOP needs slot[, target]")
            elif line.startswith("// MASA_ON_SIGNAL_TEXTBOX:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_TEXTBOX:\s*\d+\s*,\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_TEXTBOX needs slot,box,x,y,w,h,color,text")
            elif line.startswith("// MASA_ON_SIGNAL_CHOICES:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_CHOICES:\s*\d+\s*,\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*\d+\s*,\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_CHOICES needs slot,choice,x,y,color,baseSignal,text")
            elif line.startswith("// MASA_ON_SIGNAL_TEXTBOX_CLEAR:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_TEXTBOX_CLEAR:\s*\d+\s*,\s*\d+", line):
                    issues.append("MASA_ON_SIGNAL_TEXTBOX_CLEAR needs slot,box")
            elif line.startswith("// MASA_ON_SIGNAL_CHOICES_CLEAR:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_CHOICES_CLEAR:\s*\d+\s*,\s*\d+", line):
                    issues.append("MASA_ON_SIGNAL_CHOICES_CLEAR needs slot,choice")
            elif line.startswith("// MASA_ON_SIGNAL_SET_INPUT:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SET_INPUT:\s*\d+\s*,\s*.+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_ON_SIGNAL_SET_INPUT needs slot,target,speed")
            elif line.startswith("// MASA_ON_SIGNAL_SHOW_TEXT:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SHOW_TEXT:\s*\d+\s*,\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*.+", line):
                    issues.append("MASA_ON_SIGNAL_SHOW_TEXT needs slot,textSlot,x,y,color[,align],text")
            elif line.startswith("// MASA_ON_SIGNAL_SHOW_TEXT_CLEAR:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_SHOW_TEXT_CLEAR:\s*\d+\s*,\s*\d+", line):
                    issues.append("MASA_ON_SIGNAL_SHOW_TEXT_CLEAR needs slot,textSlot")
            elif line.startswith("// MASA_ON_SIGNAL_HUD_ADD:"):
                if not re.search(r"//\s*MASA_ON_SIGNAL_HUD_ADD:\s*\d+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_ON_SIGNAL_HUD_ADD needs slot,lifeDelta,scoreDelta,coinsDelta")
            elif line.startswith("// MASA_PRESS_BTN_") or line.startswith("// MASA_PRESSED_BTN_") or line.startswith("// MASA_RELEASED_BTN_"):
                if not re.search(r"//\s*MASA_(PRESS|PRESSED|RELEASED)_BTN_[A-Z]+:\s*\d+", line):
                    issues.append("MASA_PRESS/RELEASED needs : slot")
            elif line.startswith("// MASA_BG_SCROLL_X:"):
                if not re.search(r"//\s*MASA_BG_SCROLL_X:\s*[-\d.]+", line):
                    issues.append("MASA_BG_SCROLL_X needs one number")
            elif line.startswith("// MASA_BG_SCROLL_Y:"):
                if not re.search(r"//\s*MASA_BG_SCROLL_Y:\s*[-\d.]+", line):
                    issues.append("MASA_BG_SCROLL_Y needs one number")
            elif line.startswith("// MASA_HUD:"):
                if not re.search(r"//\s*MASA_HUD:\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+", line):
                    issues.append("MASA_HUD needs x,y,color[,align,bgColor,padX,padY,template]")
            elif line.startswith("// MASA_HUD_SET:"):
                if not re.search(r"//\s*MASA_HUD_SET:\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_HUD_SET needs life,score,coins")
            elif line.startswith("// MASA_HUD_ADD:"):
                if not re.search(r"//\s*MASA_HUD_ADD:\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_HUD_ADD needs life,score,coins")
            elif line.startswith("// MASA_VAR_SET:"):
                if not re.search(r"//\s*MASA_VAR_SET:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_SET needs target,index,value")
            elif line.startswith("// MASA_VAR_ADD:"):
                if not re.search(r"//\s*MASA_VAR_ADD:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_ADD needs target,index,delta")
            elif line.startswith("// MASA_VAR_TEXT:"):
                if not re.search(r"//\s*MASA_VAR_TEXT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+\s*,\s*[^,]+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_TEXT needs slot,x,y,color,target,index[,label]")
            elif line.startswith("// MASA_VARF_SET:"):
                if not re.search(r"//\s*MASA_VARF_SET:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_SET needs target,index,value")
            elif line.startswith("// MASA_VARF_ADD:"):
                if not re.search(r"//\s*MASA_VARF_ADD:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_ADD needs target,index,delta")
            elif line.startswith("// MASA_VARF_TEXT:"):
                if not re.search(r"//\s*MASA_VARF_TEXT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+\s*,\s*[^,]+\s*,\s*-?\d+", line):
                    issues.append("MASA_VARF_TEXT needs slot,x,y,color,target,index[,label]")
            elif line.startswith("// MASA_INC:"):
                if not re.search(r"//\s*MASA_INC:\s*[^,]+\s*,\s*-?\d+(\s*,\s*-?\d+)?", line):
                    issues.append("MASA_INC needs target,index[,amount]")
            elif line.startswith("// MASA_DEC:"):
                if not re.search(r"//\s*MASA_DEC:\s*[^,]+\s*,\s*-?\d+(\s*,\s*-?\d+)?", line):
                    issues.append("MASA_DEC needs target,index[,amount]")
            elif line.startswith("// MASA_IF_"):
                if not re.search(r"//\s*MASA_IF_(EQ|GT|LT|EQF|GTF|LTF):\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+\s*,\s*\d+", line):
                    issues.append("MASA_IF_* needs target,index,value,signal")
            elif line.startswith("// MASA_VAR_CLAMP:"):
                if not re.search(r"//\s*MASA_VAR_CLAMP:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_CLAMP needs target,index,min,max")
            elif line.startswith("// MASA_VARF_CLAMP:"):
                if not re.search(r"//\s*MASA_VARF_CLAMP:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_CLAMP needs target,index,min,max")
            elif line.startswith("// MASA_VAR_RAND:"):
                if not re.search(r"//\s*MASA_VAR_RAND:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_RAND needs target,index,min,max")
            elif line.startswith("// MASA_VARF_LERP:"):
                if not re.search(r"//\s*MASA_VARF_LERP:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_LERP needs target,index,a,b,t")
            elif line.startswith("// MASA_VAR_MIN:"):
                if not re.search(r"//\s*MASA_VAR_MIN:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_MIN needs target,index,value")
            elif line.startswith("// MASA_VAR_MAX:"):
                if not re.search(r"//\s*MASA_VAR_MAX:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+", line):
                    issues.append("MASA_VAR_MAX needs target,index,value")
            elif line.startswith("// MASA_VARF_MIN:"):
                if not re.search(r"//\s*MASA_VARF_MIN:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_MIN needs target,index,value")
            elif line.startswith("// MASA_VARF_MAX:"):
                if not re.search(r"//\s*MASA_VARF_MAX:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_MAX needs target,index,value")
            elif line.startswith("// MASA_VARF_SIN:"):
                if not re.search(r"//\s*MASA_VARF_SIN:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_SIN needs target,index,angle_deg")
            elif line.startswith("// MASA_VARF_COS:"):
                if not re.search(r"//\s*MASA_VARF_COS:\s*[^,]+\s*,\s*-?\d+\s*,\s*[-\d.]+", line):
                    issues.append("MASA_VARF_COS needs target,index,angle_deg")
            elif line.startswith("// MASA_STR_SET:"):
                if not re.search(r"//\s*MASA_STR_SET:\s*[^,]+\s*,\s*-?\d+\s*,\s*\".*\"", line):
                    issues.append("MASA_STR_SET needs target,index,\"text\"")
            elif line.startswith("// MASA_STR_TEXT:"):
                if not re.search(r"//\s*MASA_STR_TEXT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+\s*,\s*[^,]+\s*,\s*-?\d+", line):
                    issues.append("MASA_STR_TEXT needs slot,x,y,color,target,index[,label]")
            elif line.startswith("// MASA_SWITCH:"):
                if not re.search(r"//\s*MASA_SWITCH:\s*[^,]+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*\d+", line):
                    issues.append("MASA_SWITCH needs target,index,value,signal")
            elif line.startswith("// MASA_START_ALARM:"):
                if not re.search(r"//\s*MASA_START_ALARM:\s*\d+\s*,\s*\d+", line):
                    issues.append("MASA_START_ALARM needs slot,ms[,repeat]")
            elif line.startswith("// MASA_STOP_ALARM:"):
                if not re.search(r"//\s*MASA_STOP_ALARM:\s*\d+", line):
                    issues.append("MASA_STOP_ALARM needs slot")
            elif line.startswith("// IF_MASA_ALARM_RINGS:"):
                if not re.search(r"//\s*IF_MASA_ALARM_RINGS:\s*\d+\s*,\s*\d+", line):
                    issues.append("IF_MASA_ALARM_RINGS needs alarmSlot, signalSlot")
            elif line.startswith("// MASA_PLAY_MUSIC:"):
                if not re.search(r"//\s*MASA_PLAY_MUSIC:\s*.+", line):
                    issues.append("MASA_PLAY_MUSIC needs song id or name")
            elif line.startswith("// MASA_STOP_MUSIC"):
                pass
            elif line.startswith("// MASA_PAUSE_MUSIC"):
                pass
            elif line.startswith("// MASA_SONG_LOOP:"):
                if not re.search(r"//\s*MASA_SONG_LOOP:\s*(0|1|true|false|yes|no)", line, re.IGNORECASE):
                    issues.append("MASA_SONG_LOOP needs 0/1")
            elif line.startswith("// MASA_IF_MUSIC_IS_PLAYING:"):
                if not re.search(r"//\s*MASA_IF_MUSIC_IS_PLAYING:\s*\d+", line):
                    issues.append("MASA_IF_MUSIC_IS_PLAYING needs signal slot")
            elif line.startswith("// MASA_TEXTBOX_CLEAR:"):
                if not re.search(r"//\s*MASA_TEXTBOX_CLEAR:\s*\d+", line):
                    issues.append("MASA_TEXTBOX_CLEAR needs slot 0..1")
            elif line.startswith("// MASA_TEXTBOX:"):
                if not re.search(r"//\s*MASA_TEXTBOX:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*.+", line):
                    issues.append("MASA_TEXTBOX needs slot,x,y,w,h,color,text")
            elif line.startswith("// MASA_CHOICES_CLEAR:"):
                if not re.search(r"//\s*MASA_CHOICES_CLEAR:\s*\d+", line):
                    issues.append("MASA_CHOICES_CLEAR needs slot 0..1")
            elif line.startswith("// MASA_CHOICES:"):
                if not re.search(r"//\s*MASA_CHOICES:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+,\s*\d+\s*,\s*.+", line):
                    issues.append("MASA_CHOICES needs slot,x,y,color,baseSignal,text")
            elif line.startswith("// MASA_SHAPE_CLEAR:"):
                if not re.search(r"//\s*MASA_SHAPE_CLEAR:\s*\d+", line):
                    issues.append("MASA_SHAPE_CLEAR needs slot 0..7")
            elif line.startswith("// MASA_RECT:") or line.startswith("// MASA_FILL_RECT:"):
                if not re.search(r"//\s*MASA_(FILL_)?RECT:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+", line):
                    issues.append("MASA_RECT needs slot,x,y,w,h,color")
            elif line.startswith("// MASA_LINE:"):
                if not re.search(r"//\s*MASA_LINE:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+", line):
                    issues.append("MASA_LINE needs slot,x1,y1,x2,y2,color")
            elif line.startswith("// MASA_TRI:"):
                if not re.search(r"//\s*MASA_TRI:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+", line):
                    issues.append("MASA_TRI needs slot,x1,y1,x2,y2,x3,y3,color")
            elif line.startswith("// MASA_CIRCLE:"):
                if not re.search(r"//\s*MASA_CIRCLE:\s*\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*[^,]+", line):
                    issues.append("MASA_CIRCLE needs slot,x,y,r,color")
        return issues

    def _default_room(self, name="room0"):
        return {
            "name": name,
            "width": ROOM_W,
            "height": ROOM_H,
            "background_index": 0,
            "background_color": int(self.project.get("background_color", 12)),
            "song": "",
            "objects": [],
        }

    def _selected_song_name(self):
        v = self.room_song_var.get().strip()
        if not v or v == "none":
            return ""
        return v

    def set_room_song(self, name: str):
        name = (name or "").strip()
        vals = list(self.song_combo.cget("values")) if hasattr(self, "song_combo") else []
        if not vals:
            self.room_song_var.set("none")
            return
        if name and name in vals:
            self.room_song_var.set(name)
        else:
            self.room_song_var.set("none")

    def _room_from_project_fields(self, name="room0"):
        return {
            "name": name,
            "width": ROOM_W,
            "height": ROOM_H,
            "background_index": int(self.project.get("background_index", 0)),
            "background_color": int(self.project.get("background_color", 12)),
            "song": self._selected_song_name(),
            "objects": [dict(o) for o in self.project.get("objects", [])],
            "tilemap_index": -1,
        }

    def _ensure_rooms(self):
        rooms = self.project.get("rooms")
        if not isinstance(rooms, list):
            rooms = []
            self.project["rooms"] = rooms

        if not rooms:
            if isinstance(self.project.get("objects"), list):
                rooms.append(
                    self._room_from_project_fields(
                        self.project.get("name", "room0")
                    )
                )
            else:
                rooms.append(self._default_room("room0"))

        try:
            idx = int(self.project.get("active_room", 0))
        except Exception:
            idx = 0
        if idx < 0:
            idx = 0
        if idx >= len(rooms):
            idx = len(rooms) - 1
        self.project["active_room"] = idx

    def _default_tilemap(self, name="map0"):
        tile_size = 16
        w = max(1, ROOM_W // tile_size)
        h = max(1, ROOM_H // tile_size)
        empty = [0] * (w * h)
        return {
            "name": name,
            "tile_size": tile_size,
            "tileset_index": 0,
            "width": w,
            "height": h,
            "layers": {
                "back": list(empty),
                "mid": list(empty),
                "front": list(empty),
            },
        }

    def _ensure_tilemaps(self):
        tilemaps = self.project.get("tilemaps")
        if not isinstance(tilemaps, list):
            tilemaps = []
            self.project["tilemaps"] = tilemaps
        if not tilemaps:
            tilemaps.append(self._default_tilemap("map0"))
        if self.tilemap_selected is None or self.tilemap_selected >= len(tilemaps):
            self.tilemap_selected = 0

    def _active_tilemap(self):
        self._ensure_tilemaps()
        if self.tilemap_selected is None:
            self.tilemap_selected = 0
        tilemaps = self.project.get("tilemaps", [])
        if not tilemaps:
            return None
        idx = self.tilemap_selected
        if idx < 0 or idx >= len(tilemaps):
            idx = 0
            self.tilemap_selected = 0
        return tilemaps[idx]

    def _active_room(self):
        self._ensure_rooms()
        idx = int(self.project.get("active_room", 0))
        rooms = self.project["rooms"]
        if idx < 0 or idx >= len(rooms):
            idx = 0
        room = rooms[idx]
        if "objects" not in room or not isinstance(room.get("objects"), list):
            room["objects"] = []
        if "tilemap_index" not in room:
            room["tilemap_index"] = -1
        return room

    def _active_room_objects(self):
        return self._active_room().get("objects", [])

    def _rebuild_objects_from_rooms(self):
        if self.project.get("objects"):
            return
        obj_map = {}
        for room in self.project.get("rooms", []):
            room_objs = room.get("objects", [])
            if not isinstance(room_objs, list):
                continue
            for ro in room_objs:
                name = str(ro.get("name", "obj"))
                if name not in obj_map:
                    obj_map[name] = dict(ro)
        self.project["objects"] = list(obj_map.values())

    def _sync_objects_from_rooms(self):
        rooms = self.project.get("rooms", [])
        obj_by_name = {}
        order = []

        def _canonical_obj_name(name, known_names):
            tok = str(name or "").strip()
            m = re.match(r"^(.+?)_(\d+)$", tok)
            if m and m.group(1) in known_names:
                return m.group(1)
            return tok

        known_names = set()
        for o in self.project.get("objects", []):
            nm = str(o.get("name", "")).strip()
            if nm:
                known_names.add(nm)
        for room in rooms:
            room_objs = room.get("objects", [])
            if not isinstance(room_objs, list):
                continue
            for ro in room_objs:
                nm = str(ro.get("name", "")).strip()
                if nm:
                    known_names.add(nm)

        # Start with existing objects so we keep scripts/props if rooms are missing fields.
        for o in self.project.get("objects", []):
            name = _canonical_obj_name(str(o.get("name", "")).strip(), known_names)
            if not name:
                continue
            o = dict(o)
            o["name"] = name
            obj_by_name[name] = dict(o)

        def _merge(base, src):
            for key in ("draw_mode", "start_state", "idle_frames", "walk_frames", "run_frames", "jump_frames",
                        "idle_fps", "walk_fps", "run_fps", "jump_fps", "angle", "scale", "persistent", "script_update"):
                if key not in base or str(base.get(key, "")).strip() == "":
                    if key in src:
                        base[key] = src.get(key)
            for key in ("x", "y", "name"):
                if key in src:
                    base[key] = src.get(key)
            return base

        for room in rooms:
            room_objs = room.get("objects", [])
            if not isinstance(room_objs, list):
                continue
            for ro in room_objs:
                name = _canonical_obj_name(str(ro.get("name", "")).strip(), known_names)
                if not name:
                    continue
                ro["name"] = name
                if name not in obj_by_name:
                    obj_by_name[name] = dict(ro)
                else:
                    obj_by_name[name] = _merge(obj_by_name[name], ro)
                if name not in order:
                    order.append(name)

        # Preserve any global objects that are not placed in rooms.
        for name in obj_by_name.keys():
            if name not in order:
                order.append(name)

        self.project["objects"] = [dict(obj_by_name[name]) for name in order]

    def _save_current_room_fields(self):
        self._ensure_rooms()
        idx = int(self.project.get("active_room", 0))
        rooms = self.project["rooms"]
        if idx < 0 or idx >= len(rooms):
            return
        room = rooms[idx]
        current_name = str(room.get("name", f"room{idx}")) or f"room{idx}"
        room["name"] = current_name
        room["width"] = ROOM_W
        room["height"] = ROOM_H
        room["background_index"] = int(self.project.get("background_index", 0))
        room["background_color"] = int(self.project.get("background_color", 12))
        room["song"] = self._selected_song_name()
        try:
            tm_val = self.room_tilemap_index.get()
            if tm_val == "none":
                room["tilemap_index"] = -1
            else:
                room["tilemap_index"] = int(tm_val.split(":")[0])
        except Exception:
            room["tilemap_index"] = int(room.get("tilemap_index", -1))
        if "objects" not in room or not isinstance(room.get("objects"), list):
            room["objects"] = []
        rooms[idx] = room

    def _load_room_to_fields(self, idx):
        self._ensure_rooms()
        rooms = self.project["rooms"]
        if idx < 0 or idx >= len(rooms):
            return
        room = rooms[idx]
        self.project["active_room"] = idx
        self.project["background_index"] = int(room.get("background_index", 0))
        self.project["background_color"] = int(room.get("background_color", self.project.get("background_color", 12)))
        room_song = str(room.get("song", "") or "")

        self.selected_room_obj = None
        self.bg_index.set(str(self.project["background_index"]))
        self.bg_color_var.set(str(self.project.get("background_color", 12)))
        self.set_room_song(room_song)
        self.refresh_bg_combo()
        self.refresh_song_combo()
        self.refresh_tilemap_combo()
        self.refresh_room_picker()
        self.refresh_object_list()
        self.redraw_room_canvas()

    def refresh_room_picker(self):
        if not hasattr(self, "room_pick"):
            return
        self._ensure_rooms()
        vals = []
        for i, r in enumerate(self.project["rooms"]):
            vals.append(f"{i}: {r.get('name', f'room{i}')}")
        self.room_pick["values"] = vals
        idx = int(self.project.get("active_room", 0))
        if vals and 0 <= idx < len(vals):
            self.room_pick_var.set(vals[idx])
        elif vals:
            self.room_pick_var.set(vals[0])
        else:
            self.room_pick_var.set("")

    def on_room_pick_change(self):
        v = self.room_pick_var.get().strip()
        if not v:
            return
        try:
            new_idx = int(v.split(":", 1)[0].strip())
        except Exception:
            return
        self._save_current_room_fields()
        self._load_room_to_fields(new_idx)

    def add_room(self):
        self._save_current_room_fields()
        self._ensure_rooms()
        rooms = self.project["rooms"]
        idx = len(rooms)
        rooms.append(self._default_room(f"room{idx}"))
        self._load_room_to_fields(idx)
        self.set_status(f"Added room{idx}")

    def delete_room(self):
        self._save_current_room_fields()
        self._ensure_rooms()
        rooms = self.project["rooms"]
        if len(rooms) <= 1:
            messagebox.showwarning("Cannot delete", "At least one room is required.")
            return
        idx = int(self.project.get("active_room", 0))
        del rooms[idx]
        if idx >= len(rooms):
            idx = len(rooms) - 1
        self._load_room_to_fields(idx)
        self.set_status(f"Deleted room. Active room: {idx}")

    def rename_room(self):
        self._save_current_room_fields()
        self._ensure_rooms()
        idx = int(self.project.get("active_room", 0))
        rooms = self.project["rooms"]
        if idx < 0 or idx >= len(rooms):
            return
        current = str(rooms[idx].get("name", f"room{idx}")) or f"room{idx}"
        new_name = simpledialog.askstring("Rename Room", "Room name:", initialvalue=current, parent=self)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning("Invalid name", "Room name cannot be empty.")
            return
        rooms[idx]["name"] = new_name
        self.refresh_room_picker()
        self.set_status(f"Renamed room to: {new_name}")

    def _apply_sprites_meta(self, meta, source_name=""):
        self.sprites_meta = meta
        # Remap missing PNG paths to local tools/ folder by basename.
        if isinstance(self.sprites_meta.get("pngs"), list):
            remapped = []
            for p in self.sprites_meta.get("pngs", []):
                if p and os.path.isfile(p):
                    remapped.append(p)
                    continue
                base = os.path.basename(p)
                cand = os.path.join(PROJECT_ROOT, "tools", base)
                remapped.append(cand)
            self.sprites_meta["pngs"] = remapped
        self.sprite_images = []
        self.sprite_images_pil = []
        for p in self.sprites_meta.get("pngs", []):
            try:
                self.sprite_images.append(tk.PhotoImage(file=p))
            except Exception:
                self.sprite_images.append(None)
            if PIL_AVAILABLE:
                try:
                    self.sprite_images_pil.append(Image.open(p).convert("RGBA"))
                except Exception:
                    self.sprite_images_pil.append(None)
            else:
                self.sprite_images_pil.append(None)
        self.refresh_frames()
        self.refresh_room_object_list()
        self.redraw_room_canvas()
        self._update_status_line()
        if source_name:
            self.set_status(f"Loaded sprites: {source_name}")

    def _apply_backgrounds_meta(self, meta, source_name=""):
        self.backgrounds_meta = meta
        if isinstance(self.backgrounds_meta.get("pngs"), list):
            remapped = []
            for p in self.backgrounds_meta.get("pngs", []):
                if p and os.path.isfile(p):
                    remapped.append(p)
                    continue
                base = os.path.basename(p)
                cand = os.path.join(PROJECT_ROOT, "tools", base)
                remapped.append(cand)
            self.backgrounds_meta["pngs"] = remapped
        self.bg_images = []
        self.bg_images_pil = []
        for p in self.backgrounds_meta.get("pngs", []):
            try:
                self.bg_images.append(tk.PhotoImage(file=p))
            except Exception:
                self.bg_images.append(None)
            if PIL_AVAILABLE:
                try:
                    self.bg_images_pil.append(Image.open(p).convert("RGBA"))
                except Exception:
                    self.bg_images_pil.append(None)
            else:
                self.bg_images_pil.append(None)
        self.refresh_bg_combo()
        self.redraw_room_canvas()
        self._update_status_line()
        if source_name:
            self.set_status(f"Loaded backgrounds: {source_name}")

    def _apply_songs_meta(self, meta, source_name=""):
        self.songs_meta = meta
        self.refresh_song_combo()
        self._update_status_line()
        if source_name:
            self.set_status(f"Loaded songs: {source_name}")

    def _update_status_line(self):
        if not hasattr(self, "status2"):
            return
        spr = len(self.sprite_images) if self.sprite_images else 0
        bg = len(self.bg_images) if self.bg_images else 0
        pil = "OK" if PIL_AVAILABLE else "MISSING"
        self.status2.config(text=f"Pillow: {pil} | Sprites: {spr} | Backgrounds: {bg}")

    def _apply_rooms_meta(self, meta, source_name=""):
        rooms = meta.get("rooms", [])
        if not isinstance(rooms, list) or not rooms:
            raise ValueError("Rooms atlas has no rooms.")
        self._save_current_room_fields()
        self.project["name"] = str(meta.get("project_name", self.project.get("name", "game_project"))) or "game_project"
        self.project_name.set(self.project["name"])
        self.project["rooms"] = rooms
        self.project["active_room"] = int(meta.get("active_room", 0))
        self._ensure_rooms()
        self._load_room_to_fields(int(self.project.get("active_room", 0)))
        if source_name:
            self.set_status(f"Loaded rooms atlas: {source_name}")

    def _parse_rooms_header_text(self, txt):
        m = re.search(r"// ROOMS_ATLAS_META:\s*(\{.*\})", txt)
        if not m:
            raise ValueError("Header has no ROOMS_ATLAS_META comment.")
        meta = json.loads(m.group(1))
        if not isinstance(meta, dict) or meta.get("type") != "rooms_atlas_v1":
            raise ValueError("Invalid rooms atlas metadata type.")
        return meta

    def _load_rooms_header_path(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        meta = self._parse_rooms_header_text(txt)
        self._apply_rooms_meta(meta, os.path.basename(path))

    def load_sprites(self):
        path = filedialog.askopenfilename(
            title="Load sprites metadata (.json/.h)",
            filetypes=[("Supported", "*.json *.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meta = load_asset_meta(path, "sprites_project_v1")
            self._apply_sprites_meta(meta, os.path.basename(path))
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def load_backgrounds(self):
        path = filedialog.askopenfilename(
            title="Load backgrounds metadata (.json/.h)",
            filetypes=[("Supported", "*.json *.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meta = load_asset_meta(path, "backgrounds_project_v1")
            self._apply_backgrounds_meta(meta, os.path.basename(path))
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def load_songs(self):
        path = filedialog.askopenfilename(
            title="Load songs atlas (.json/.h)",
            filetypes=[("Supported", "*.json *.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meta = load_songs_meta(path)
            self._apply_songs_meta(meta, os.path.basename(path))
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def refresh_frames(self):
        self.frames_list.delete(0, tk.END)
        if not self.sprites_meta:
            return
        names = self.sprites_meta.get("frame_names", [])
        for i, n in enumerate(names):
            self.frames_list.insert(tk.END, f"[{i}] {n}")

    def new_project(self):
        self.project = {
            "name": "game_project",
            "background_index": 0,
            "background_color": 12,
            "objects": [],
            "rooms": [self._default_room("room0")],
            "active_room": 0,
            "songs_meta": None,
        }
        self.songs_meta = None
        self.project_name.set("game_project")
        self.bg_index.set("0")
        self.bg_color_var.set("12")
        self.selected_obj = None
        self.obj_list.delete(0, tk.END)
        self.script_text.delete("1.0", tk.END)
        self.refresh_room_picker()
        self._load_room_to_fields(0)
        self.refresh_bg_combo()
        self.refresh_song_combo()
        self.refresh_room_object_list()
        self.redraw_room_canvas()
        self.set_status("New project.")

    def _commit_ui_state(self):
        # Best-effort: apply any pending edits without requiring button clicks.
        try:
            self.apply_object_props()
        except Exception:
            pass
        try:
            self.apply_room_props()
        except Exception:
            pass

    def _zip_dir(self, zf, path):
        if not path.endswith("/"):
            path = path + "/"
        zf.writestr(path, "")

    def _zip_add_file(self, zf, src_path, arc_path):
        if not src_path or not os.path.isfile(src_path):
            return False
        zf.write(src_path, arc_path)
        return True

    def _save_ingr(self, out_path):
        self._commit_ui_state()
        self._save_current_room_fields()
        self._sync_objects_from_rooms()
        self.project["name"] = self.project_name.get().strip() or "game_project"
        self.project["songs_meta"] = self.songs_meta
        try:
            self.project["background_index"] = int(self.bg_index.get().strip())
        except Exception:
            self.project["background_index"] = 0

        obj_list = [dict(o) for o in self.project.get("objects", [])]
        rooms_list = [dict(r) for r in self.project.get("rooms", [])]
        meta = {
            "name": self.project.get("name", "game_project"),
            "active_room": int(self.project.get("active_room", 0)),
        }

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in ["sprites", "objects", "scripts", "rooms", "sounds", "tilemaps", "fonts", "assets", "assets/metadata", "assets/sprites", "assets/backgrounds", "assets/sounds", "assets/headers"]:
                self._zip_dir(zf, p)

            zf.writestr("project.json", json.dumps(self.project, indent=2))
            zf.writestr("objects/objects.json", json.dumps(obj_list, indent=2))
            zf.writestr("rooms/rooms.json", json.dumps(rooms_list, indent=2))
            zf.writestr("manifest.json", json.dumps(meta, indent=2))
            if isinstance(self.project.get("tilemaps"), list):
                zf.writestr("tilemaps/tilemaps.json", json.dumps(self.project.get("tilemaps", []), indent=2))

            for i, o in enumerate(obj_list):
                name = sanitize_filename(str(o.get("name", f"obj_{i}")))
                script = str(o.get("script_update", "") or "")
                zf.writestr(f"scripts/{i:02d}_{name}.txt", script)

            if self.sprites_meta:
                zf.writestr("assets/metadata/sprites.json", json.dumps(self.sprites_meta, indent=2))
                for p in self.sprites_meta.get("pngs", []):
                    base = os.path.basename(p)
                    self._zip_add_file(zf, p, f"assets/sprites/{base}")

            if self.backgrounds_meta:
                zf.writestr("assets/metadata/backgrounds.json", json.dumps(self.backgrounds_meta, indent=2))
                for p in self.backgrounds_meta.get("pngs", []):
                    base = os.path.basename(p)
                    self._zip_add_file(zf, p, f"assets/backgrounds/{base}")

            if self.songs_meta:
                zf.writestr("assets/metadata/songs.json", json.dumps(self.songs_meta, indent=2))
                for s in self.songs_meta.get("songs", []):
                    p = str(s.get("input", "") or s.get("source", ""))
                    if p:
                        base = os.path.basename(p)
                        self._zip_add_file(zf, p, f"assets/sounds/{base}")

            sprites_out = ""
            backgrounds_out = ""
            songs_out = ""
            if self.sprites_meta:
                sprites_out = str(self.sprites_meta.get("out", ""))
            if self.backgrounds_meta:
                backgrounds_out = str(self.backgrounds_meta.get("out", ""))
            if self.songs_meta:
                songs_out = str(self.songs_meta.get("out", ""))
            if sprites_out:
                self._zip_add_file(zf, sprites_out, "assets/headers/my_sprites.h")
            if backgrounds_out:
                self._zip_add_file(zf, backgrounds_out, "assets/headers/backgrounds.h")
            if songs_out and os.path.isfile(songs_out):
                self._zip_add_file(zf, songs_out, "assets/headers/songs.h")
            else:
                fallback_songs = os.path.join(PROJECT_ROOT, "gfx", "songs.h")
                if os.path.isfile(fallback_songs):
                    self._zip_add_file(zf, fallback_songs, "assets/headers/songs.h")
            # Rooms/songs are saved in JSON/metadata to avoid stale global headers.

    def _extract_ingr_assets(self, zf, base_dir):
        os.makedirs(base_dir, exist_ok=True)
        assets = {}
        for name in zf.namelist():
            if not name.startswith("assets/"):
                continue
            out = os.path.join(base_dir, name.replace("/", os.sep))
            if name.endswith("/"):
                os.makedirs(out, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(zf.read(name))
            assets[name] = out
        return assets

    def _load_ingr(self, path):
        with zipfile.ZipFile(path, "r") as zf:
            if "project.json" not in zf.namelist():
                raise ValueError("Missing project.json in .ingr")
            self.project = json.loads(zf.read("project.json").decode("utf-8"))
            if "rooms/rooms.json" in zf.namelist():
                try:
                    self.project["rooms"] = json.loads(zf.read("rooms/rooms.json").decode("utf-8"))
                except Exception:
                    pass
            if "tilemaps/tilemaps.json" in zf.namelist():
                try:
                    self.project["tilemaps"] = json.loads(zf.read("tilemaps/tilemaps.json").decode("utf-8"))
                except Exception:
                    pass
            if "objects/objects.json" in zf.namelist():
                try:
                    self.project["objects"] = json.loads(zf.read("objects/objects.json").decode("utf-8"))
                except Exception:
                    pass

            # Rehydrate object scripts from scripts/*.txt when available.
            # Some project variants store authoritative scripts there.
            script_by_index = {}
            script_by_name = {}
            for n in zf.namelist():
                if not n.startswith("scripts/") or not n.endswith(".txt"):
                    continue
                base = os.path.basename(n)
                m = re.match(r"^(\d+)_([^.]+)\.txt$", base)
                text = zf.read(n).decode("utf-8", errors="ignore")
                if m:
                    idx = int(m.group(1))
                    nm = str(m.group(2))
                    script_by_index[idx] = text
                    script_by_name[nm] = text
                else:
                    nm = os.path.splitext(base)[0]
                    script_by_name[nm] = text
            if isinstance(self.project.get("objects"), list):
                for i, o in enumerate(self.project.get("objects", [])):
                    if not isinstance(o, dict):
                        continue
                    nm = sanitize_filename(str(o.get("name", "")))
                    txt = script_by_index.get(i, script_by_name.get(nm))
                    if txt is not None:
                        o["script_update"] = txt

                # Drop internal transient keys if present in imported data.
                for o in self.project.get("objects", []):
                    if not isinstance(o, dict):
                        continue
                    o.pop("_type_name", None)
                    o.pop("_instance_name", None)
                for r in self.project.get("rooms", []):
                    if not isinstance(r, dict):
                        continue
                    objs = r.get("objects", [])
                    if not isinstance(objs, list):
                        continue
                    for ro in objs:
                        if not isinstance(ro, dict):
                            continue
                        ro.pop("_type_name", None)
                        ro.pop("_instance_name", None)

            sprites_meta = None
            backgrounds_meta = None
            songs_meta = None
            if "assets/metadata/sprites.json" in zf.namelist():
                sprites_meta = json.loads(zf.read("assets/metadata/sprites.json").decode("utf-8"))
            if "assets/metadata/backgrounds.json" in zf.namelist():
                backgrounds_meta = json.loads(zf.read("assets/metadata/backgrounds.json").decode("utf-8"))
            if "assets/metadata/songs.json" in zf.namelist():
                songs_meta = json.loads(zf.read("assets/metadata/songs.json").decode("utf-8"))

            sig = f"{path}|{os.path.getsize(path)}|{os.path.getmtime(path)}"
            cache_id = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:10]
            cache_root = os.path.join(PROJECT_ROOT, "ingr_cache", f"{sanitize_filename(self.project.get('name', 'game_project'))}_{cache_id}")
            assets = self._extract_ingr_assets(zf, cache_root)

            if sprites_meta and isinstance(sprites_meta.get("pngs"), list):
                sprites_meta["pngs"] = [assets.get(f"assets/sprites/{os.path.basename(p)}", p) for p in sprites_meta.get("pngs", [])]
            if backgrounds_meta and isinstance(backgrounds_meta.get("pngs"), list):
                backgrounds_meta["pngs"] = [assets.get(f"assets/backgrounds/{os.path.basename(p)}", p) for p in backgrounds_meta.get("pngs", [])]
            if songs_meta and isinstance(songs_meta.get("songs"), list):
                for s in songs_meta.get("songs", []):
                    p = str(s.get("input", "") or s.get("source", ""))
                    base = os.path.basename(p)
                    if base:
                        s["input"] = assets.get(f"assets/sounds/{base}", p)

            headers_root = os.path.join(cache_root, "assets", "headers")
            sprites_h = os.path.join(headers_root, "my_sprites.h")
            backgrounds_h = os.path.join(headers_root, "backgrounds.h")
            songs_h = os.path.join(headers_root, "songs.h")
            rooms_h = os.path.join(headers_root, "rooms.h")

            if os.path.isfile(sprites_h):
                try:
                    sprites_meta = load_asset_meta(sprites_h, "sprites_project_v1")
                    if isinstance(sprites_meta.get("pngs"), list):
                        sprites_meta["pngs"] = [assets.get(f"assets/sprites/{os.path.basename(p)}", p) for p in sprites_meta.get("pngs", [])]
                except Exception:
                    pass
            if os.path.isfile(backgrounds_h):
                try:
                    backgrounds_meta = load_asset_meta(backgrounds_h, "backgrounds_project_v1")
                    if isinstance(backgrounds_meta.get("pngs"), list):
                        backgrounds_meta["pngs"] = [assets.get(f"assets/backgrounds/{os.path.basename(p)}", p) for p in backgrounds_meta.get("pngs", [])]
                except Exception:
                    pass
            # Prefer JSON/metadata from the .ingr; only use headers if project data is missing.
            if (not songs_meta) and os.path.isfile(songs_h):
                try:
                    songs_meta = load_songs_meta(songs_h)
                except Exception:
                    pass
            if (not self.project.get("rooms")) and os.path.isfile(rooms_h):
                try:
                    self._load_rooms_header_path(rooms_h)
                except Exception:
                    pass

            if sprites_meta:
                self._apply_sprites_meta(sprites_meta)
            if backgrounds_meta:
                self._apply_backgrounds_meta(backgrounds_meta)
            if songs_meta:
                self._apply_songs_meta(songs_meta)

    def _auto_load_local_assets(self):
        if not self.sprites_meta:
            p = os.path.join(PROJECT_ROOT, "gfx", "my_sprites.h")
            if os.path.isfile(p):
                try:
                    self._apply_sprites_meta(load_asset_meta(p, "sprites_project_v1"))
                except Exception:
                    pass
        if not self.backgrounds_meta:
            p = os.path.join(PROJECT_ROOT, "gfx", "backgrounds.h")
            if os.path.isfile(p):
                try:
                    self._apply_backgrounds_meta(load_asset_meta(p, "backgrounds_project_v1"))
                except Exception:
                    pass
        if not self.songs_meta:
            p = os.path.join(PROJECT_ROOT, "gfx", "songs.h")
            if os.path.isfile(p):
                try:
                    self._apply_songs_meta(load_songs_meta(p))
                except Exception:
                    pass
        if not self.project.get("rooms"):
            p = os.path.join(PROJECT_ROOT, "gfx", "rooms.h")
            if os.path.isfile(p):
                try:
                    self._load_rooms_header_path(p)
                except Exception:
                    pass

    def save_project(self):
        out = filedialog.asksaveasfilename(
            title="Save project (.ingr)",
            defaultextension=".ingr",
            filetypes=[("Mofongo project", "*.ingr"), ("All files", "*.*")],
            initialfile=f"{self.project_name.get().strip() or 'game_project'}.ingr",
        )
        if not out:
            return
        try:
            self._save_ingr(out)
            self.set_status(f"Saved project: {out}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def load_project(self):
        path = filedialog.askopenfilename(
            title="Load project (.ingr or .json)",
            filetypes=[("Mofongo project", "*.ingr"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".ingr"):
                self._load_ingr(path)
            else:
                with open(path, "r", encoding="utf-8") as f:
                    self.project = json.load(f)
            self.project.setdefault("name", "game_project")
            self.project.setdefault("background_index", 0)
            self.project.setdefault("background_color", 12)
            self.project.setdefault("objects", [])
            self.project.setdefault("rooms", [])
            self.project.setdefault("active_room", 0)
            self.project.setdefault("songs_meta", None)
            if not path.lower().endswith(".ingr"):
                self.songs_meta = self.project.get("songs_meta", None)
            self.project_name.set(self.project["name"])
            self.bg_index.set(str(self.project["background_index"]))
            self.bg_color_var.set(str(self.project.get("background_color", 12)))
            self._ensure_rooms()
            self._rebuild_objects_from_rooms()
            self._load_room_to_fields(int(self.project.get("active_room", 0)))
            self.refresh_room_picker()
            self._auto_load_local_assets()
            self.refresh_bg_combo()
            self.refresh_song_combo()
            self.refresh_object_list()
            self.set_status(f"Loaded project: {path}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def load_room_json(self):
        path = filedialog.askopenfilename(
            title="Load room JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                room = json.load(f)

            if not isinstance(room, dict):
                raise ValueError("Invalid room JSON.")

            objects = room.get("objects", [])
            if not isinstance(objects, list):
                raise ValueError("Room JSON has invalid objects list.")

            self._save_current_room_fields()
            self._ensure_rooms()
            idx = int(self.project.get("active_room", 0))
            self.project["rooms"][idx] = {
                "name": str(room.get("name", f"room{idx}")) or f"room{idx}",
                "width": ROOM_W,
                "height": ROOM_H,
                "background_index": int(room.get("background_index", 0)),
                "background_color": int(room.get("background_color", self.project.get("background_color", 12))),
                "song": str(room.get("song", "") or ""),
                "objects": objects,
            }
            self._load_room_to_fields(idx)
            self.set_status(f"Loaded room into atlas: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def save_room_json(self):
        self._save_current_room_fields()
        self._ensure_rooms()
        idx = int(self.project.get("active_room", 0))
        room = self.build_room_dict()
        room["name"] = str(self.project["rooms"][idx].get("name", room.get("name", f"room{idx}")))
        out = filedialog.asksaveasfilename(
            title="Save room JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{room['name']}.json",
        )
        if not out:
            return
        with open(out, "w", encoding="utf-8") as f:
            json.dump(room, f, indent=2)
        self.set_status(f"Saved room: {out}")

    def load_rooms_header(self):
        path = filedialog.askopenfilename(
            title="Load rooms atlas header (.h)",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._load_rooms_header_path(path)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def load_tilemaps_header(self):
        path = filedialog.askopenfilename(
            title="Load tilemaps header (.h)",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            m = re.search(r"TILEMAPS_JSON:\s*([A-Za-z0-9+/=]+)", txt)
            if not m:
                raise ValueError("No TILEMAPS_JSON found in header.")
            blob = base64.b64decode(m.group(1).encode("utf-8")).decode("utf-8")
            meta = json.loads(blob)
            if not isinstance(meta, dict) or meta.get("type") != "tilemaps_v1":
                raise ValueError("Invalid tilemaps metadata type.")
            self.project["tilemaps"] = meta.get("tilemaps", [])
            self._ensure_tilemaps()
            self._refresh_tilemap_ui()
            self.set_status(f"Loaded tilemaps: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def export_rooms_header(self):
        self._save_current_room_fields()
        self._ensure_rooms()
        out = filedialog.asksaveasfilename(
            title="Export rooms atlas header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile="rooms.h",
        )
        if not out:
            return

        atlas = {
            "type": "rooms_atlas_v1",
            "project_name": self.project_name.get().strip() or "game_project",
            "active_room": int(self.project.get("active_room", 0)),
            "rooms": self.project.get("rooms", []),
        }
        meta_json = json.dumps(atlas, separators=(",", ":"))

        guard = re.sub(r"[^0-9A-Za-z_]", "_", os.path.basename(out)).upper() + "_"
        lines = []
        lines.append(f"#ifndef {guard}")
        lines.append(f"#define {guard}")
        lines.append("#define ROOMS_ATLAS_V2 1")
        lines.append("#define ROOMS_ATLAS_V3 1")
        lines.append("")
        lines.append("// Auto-generated by tools/game_engine_gui.py")
        lines.append(f"// ROOMS_ATLAS_META: {meta_json}")
        lines.append("")
        lines.append("struct RoomsAtlasObject")
        lines.append("{")
        lines.append("  const char *name;")
        lines.append("  int frame;")
        lines.append("  int state; // 0=idle,1=walk,2=run,3=jump")
        lines.append("  int x;")
        lines.append("  int y;")
        lines.append("  int mode; // 0=normal,1=rotated,2=scaled")
        lines.append("  float angle;")
        lines.append("  float scale;")
        lines.append("  int persistent; // 0/1")
        lines.append("};")
        lines.append("")
        lines.append("struct RoomsAtlasRoom")
        lines.append("{")
        lines.append("  const char *name;")
        lines.append("  int background_index;")
        lines.append("  const char *song;")
        lines.append("  const RoomsAtlasObject *objects;")
        lines.append("  int object_count;")
        lines.append("};")
        lines.append("")

        mode_map = {"normal": 0, "rotated": 1, "scaled": 2}
        state_map = {"idle": 0, "walk": 1, "run": 2, "jump": 3}
        for ri, room in enumerate(self.project["rooms"]):
            room_name = sanitize_ident(str(room.get("name", f"room{ri}")))
            obj_arr = f"roomsAtlas_{room_name}_objects"
            lines.append(f"static const RoomsAtlasObject {obj_arr}[] = {{")
            obj_persist_map = {}
            for oo in self.project.get("objects", []):
                obj_persist_map[str(oo.get("name", ""))] = bool(oo.get("persistent", False))

            for o in room.get("objects", []):
                  # Supports both room-json style (mode/frame) and engine style (draw_mode/idle_frames).
                  if "frame" in o:
                      frame = int(o.get("frame", 0))
                  else:
                      frame = self._obj_preview_frame(o)
                  mode_key = str(o.get("mode", o.get("draw_mode", "normal")))
                  mode = mode_map.get(mode_key, 0)
                  state_key = str(o.get("start_state", "idle"))
                  state = state_map.get(state_key, 0)
            obj_name = str(o.get("name", "obj")).replace('"', "'")
            persist = int(o.get("persistent", obj_persist_map.get(obj_name, False)))
            lines.append(
                f"  {{\"{obj_name}\", {frame}, {state}, {int(o.get('x', 0))}, {int(o.get('y', 0))}, {mode}, "
                f"{float(o.get('angle', 0.0)):.3f}f, {float(o.get('scale', 1.0)):.3f}f, {persist}}},"
            )
            lines.append("};")
            lines.append(
                f"static const int roomsAtlas_{room_name}_object_count = "
                f"sizeof({obj_arr}) / sizeof({obj_arr}[0]);"
            )
            lines.append("")

        lines.append("static const RoomsAtlasRoom roomsAtlas[] = {")
        for ri, room in enumerate(self.project["rooms"]):
            room_name = sanitize_ident(str(room.get("name", f"room{ri}")))
            obj_arr = f"roomsAtlas_{room_name}_objects"
            room_label = str(room.get("name", f"room{ri}")).replace('"', "'")
            song_label = str(room.get("song", "")).replace('"', "'")
            lines.append(
                f"  {{\"{room_label}\", {int(room.get('background_index', 0))}, \"{song_label}\", "
                f"{obj_arr}, (int)(sizeof({obj_arr}) / sizeof({obj_arr}[0]))}},"
            )
        lines.append("};")
        lines.append("static const int roomsAtlasCount = sizeof(roomsAtlas) / sizeof(roomsAtlas[0]);")
        lines.append("")
        lines.append(f"#endif // {guard}")

        with open(out, "w", encoding="ascii") as f:
            f.write("\n".join(lines) + "\n")
        self.set_status(f"Exported rooms atlas: {out}")

    def export_tilemaps_header(self):
        self._ensure_tilemaps()
        out = filedialog.asksaveasfilename(
            title="Export tilemaps header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile="tilemaps.h",
        )
        if not out:
            return
        tilemaps = self.project.get("tilemaps", [])
        meta = {"type": "tilemaps_v1", "tilemaps": tilemaps}
        meta_json = json.dumps(meta, separators=(",", ":")).encode("utf-8")
        meta_b64 = base64.b64encode(meta_json).decode("utf-8")

        guard = re.sub(r"[^0-9A-Za-z_]", "_", os.path.basename(out)).upper() + "_"
        lines = []
        lines.append(f"#ifndef {guard}")
        lines.append(f"#define {guard}")
        lines.append("")
        lines.append("// Auto-generated by tools/game_engine_gui.py")
        lines.append(f"// TILEMAPS_JSON: {meta_b64}")
        lines.append("")
        lines.append("struct TilemapDef")
        lines.append("{")
        lines.append("  unsigned short width;")
        lines.append("  unsigned short height;")
        lines.append("  unsigned char tileSize;")
        lines.append("  unsigned char tilesetIndex;")
        lines.append("  const unsigned short *back;")
        lines.append("  const unsigned short *mid;")
        lines.append("  const unsigned char *front; // collisions")
        lines.append("};")
        lines.append("")
        for i, tm in enumerate(tilemaps):
            name = sanitize_ident(str(tm.get("name", f"map{i}")))
            w = int(tm.get("width", 1))
            h = int(tm.get("height", 1))
            size = int(tm.get("tile_size", 16))
            tileset = int(tm.get("tileset_index", 0))
            layers = tm.get("layers", {}) if isinstance(tm.get("layers"), dict) else {}
            back = layers.get("back", [])
            mid = layers.get("mid", [])
            front = layers.get("front", [])
            if len(back) != w * h:
                back = [0] * (w * h)
            if len(mid) != w * h:
                mid = [0] * (w * h)
            if len(front) != w * h:
                front = [0] * (w * h)
            lines.append(f"static const unsigned short {name}_back[] = " + "{ " + ", ".join(str(int(v)) for v in back) + " };")
            lines.append(f"static const unsigned short {name}_mid[] = " + "{ " + ", ".join(str(int(v)) for v in mid) + " };")
            lines.append(f"static const unsigned char {name}_front[] = " + "{ " + ", ".join(str(int(v)) for v in front) + " };")
            lines.append("")
        lines.append(f"static const unsigned int tilemapsCount = {len(tilemaps)};")
        lines.append("static const TilemapDef tilemaps[] = {")
        for i, tm in enumerate(tilemaps):
            name = sanitize_ident(str(tm.get("name", f"map{i}")))
            w = int(tm.get("width", 1))
            h = int(tm.get("height", 1))
            size = int(tm.get("tile_size", 16))
            tileset = int(tm.get("tileset_index", 0))
            lines.append(f"  {{{w}, {h}, {size}, {tileset}, {name}_back, {name}_mid, {name}_front}},")
        lines.append("};")
        lines.append("")
        lines.append(f"#endif // {guard}")

        with open(out, "w", encoding="ascii") as f:
            f.write("\n".join(lines) + "\n")
        self.set_status(f"Exported tilemaps: {out}")

    def refresh_object_list(self):
        self._rebuild_objects_from_rooms()
        self.obj_list.delete(0, tk.END)
        obj_list = self.project.get("objects", [])
        for i, o in enumerate(obj_list):
            self.obj_list.insert(tk.END, f"[{i}] {o.get('name','obj')} ({o.get('x',0)},{o.get('y',0)})")
        self.refresh_room_object_list()

    def add_object(self):
        obj_list = self.project.get("objects", [])
        idx = len(obj_list)
        o = {
            "name": f"obj_{idx}",
            "x": ROOM_W // 2 if "ROOM_W" in globals() else 160,
            "y": ROOM_H // 2 if "ROOM_H" in globals() else 100,
            "draw_mode": "normal",
            "start_state": "idle",
            "idle_frames": "0",
            "walk_frames": "",
            "run_frames": "",
            "jump_frames": "",
            "idle_fps": 8,
            "walk_fps": 8,
            "run_fps": 10,
            "jump_fps": 8,
              "angle": 0.0,
              "scale": 1.0,
              "persistent": False,
              "script_update": "",
        }
        self.project.setdefault("objects", []).append(dict(o))
        self.refresh_object_list()
        self.selected_obj = len(self.project.get("objects", [])) - 1
        self.obj_list.selection_clear(0, tk.END)
        self.obj_list.selection_set(self.selected_obj)
        self.select_object()

    def delete_object(self):
        sel = list(self.obj_list.curselection())
        if not sel:
            return
        idx = sel[0]
        obj_list = self.project.get("objects", [])
        if idx < 0 or idx >= len(obj_list):
            return
        obj_name = str(obj_list[idx].get("name", ""))
        del obj_list[idx]
        for room in self.project.get("rooms", []):
            room_objs = room.get("objects", [])
            if not isinstance(room_objs, list):
                continue
            room["objects"] = [dict(o) for o in room_objs if str(o.get("name", "")) != obj_name]
        self.project["objects"] = [dict(o) for o in self.project.get("objects", []) if str(o.get("name", "")) != obj_name]
        self.selected_obj = None
        self.refresh_object_list()
        self.redraw_room_canvas()

    def select_object(self):
        sel = list(self.obj_list.curselection())
        if not sel:
            return
        i = sel[0]
        obj_list = self.project.get("objects", [])
        if i >= len(obj_list):
            return
        self.selected_obj = i
        o = obj_list[i]
        self.obj_name.set(str(o.get("name", "")))
        self.obj_x.set(str(o.get("x", 0)))
        self.obj_y.set(str(o.get("y", 0)))
        self.obj_mode.set(str(o.get("draw_mode", "normal")))
        self.obj_persistent.set(bool(o.get("persistent", False)))
        self.start_state.set(str(o.get("start_state", "idle")))
        self.idle_frames.set(str(o.get("idle_frames", "")))
        self.walk_frames.set(str(o.get("walk_frames", "")))
        self.run_frames.set(str(o.get("run_frames", "")))
        self.jump_frames.set(str(o.get("jump_frames", "")))
        self.idle_fps.set(str(o.get("idle_fps", 8)))
        self.walk_fps.set(str(o.get("walk_fps", 8)))
        self.run_fps.set(str(o.get("run_fps", 10)))
        self.jump_fps.set(str(o.get("jump_fps", 8)))
        self.angle.set(str(o.get("angle", 0.0)))
        self.scale.set(str(o.get("scale", 1.0)))
        self.script_text.delete("1.0", tk.END)
        self.script_text.insert("1.0", str(o.get("script_update", "")))
        self.selected_room_obj = None
        room_objs = self._active_room_objects()
        for ri, ro in enumerate(room_objs):
            if str(ro.get("name", "")) == str(o.get("name", "")):
                self.selected_room_obj = ri
                break
        self.load_room_props_from_selected()
        self.sync_room_selection()

    def apply_object_props(self):
        if self.selected_obj is None:
            return
        obj_list = self.project.get("objects", [])
        if self.selected_obj < 0 or self.selected_obj >= len(obj_list):
            return
        o = obj_list[self.selected_obj]
        try:
            old_name = str(o.get("name", ""))
            new_name = self.obj_name.get().strip() or o["name"]
            o["name"] = new_name
            o["x"] = int(self.obj_x.get())
            o["y"] = int(self.obj_y.get())
            o["draw_mode"] = self.obj_mode.get()
            o["start_state"] = self.start_state.get()
            o["idle_frames"] = self.idle_frames.get().strip()
            o["walk_frames"] = self.walk_frames.get().strip()
            o["run_frames"] = self.run_frames.get().strip()
            o["jump_frames"] = self.jump_frames.get().strip()
            o["idle_fps"] = int(self.idle_fps.get())
            o["walk_fps"] = int(self.walk_fps.get())
            o["run_fps"] = int(self.run_fps.get())
            o["jump_fps"] = int(self.jump_fps.get())
            o["angle"] = float(self.angle.get())
            o["scale"] = float(self.scale.get())
            o["persistent"] = bool(self.obj_persistent.get())
            o["script_update"] = self.script_text.get("1.0", tk.END).rstrip()
            # Sync global object list by name.
            updated = False
            for go in self.project.get("objects", []):
                if str(go.get("name", "")) == old_name:
                    go.update(dict(o))
                    go["name"] = new_name
                    updated = True
                    break
            if not updated:
                self.project.setdefault("objects", []).append(dict(o))
            for room in self.project.get("rooms", []):
                room_objs = room.get("objects", [])
                if not isinstance(room_objs, list):
                    continue
                for ro in room_objs:
                    if str(ro.get("name", "")) == old_name:
                        ro["name"] = new_name
                        ro["start_state"] = o["start_state"]
                        ro["idle_frames"] = o["idle_frames"]
                        ro["walk_frames"] = o["walk_frames"]
                        ro["run_frames"] = o["run_frames"]
                        ro["jump_frames"] = o["jump_frames"]
                        ro["idle_fps"] = o["idle_fps"]
                        ro["walk_fps"] = o["walk_fps"]
                        ro["run_fps"] = o["run_fps"]
                        ro["jump_fps"] = o["jump_fps"]
                        ro["persistent"] = o["persistent"]
                        ro["script_update"] = o["script_update"]
            self.refresh_object_list()
            self.redraw_room_canvas()
        except Exception as e:
            messagebox.showerror("Invalid object props", str(e))

    def _obj_preview_frame(self, o):
        frames = parse_frames(str(o.get("idle_frames", "0")))
        if not frames:
            return 0
        return int(frames[0])

    def build_room_dict(self):
        self.project["name"] = self.project_name.get().strip() or "game_project"
        try:
            self.project["background_index"] = int(self.bg_index.get().strip())
        except Exception:
            self.project["background_index"] = 0
        room_name = f"room{int(self.project.get('active_room', 0))}"
        if isinstance(self.project.get("rooms"), list):
            idx = int(self.project.get("active_room", 0))
            if 0 <= idx < len(self.project["rooms"]):
                room_name = str(self.project["rooms"][idx].get("name", room_name))
        mode_map = {"normal": "normal", "rotated": "rotated", "scaled": "scaled"}
        objects = []
        for i, o in enumerate(self.project["objects"]):
            objects.append(
                {
                    "id": i + 1,
                    "name": str(o.get("name", f"obj_{i}")),
                    "frame": self._obj_preview_frame(o),
                    "x": int(o.get("x", 160)),
                    "y": int(o.get("y", 100)),
                    "mode": mode_map.get(str(o.get("draw_mode", "normal")), "normal"),
                    "angle": float(o.get("angle", 0.0)),
                    "scale": float(o.get("scale", 1.0)),
                    "visible": True,
                }
            )
        return {
            "name": room_name,
            "width": ROOM_W,
            "height": ROOM_H,
            "background_index": int(self.project.get("background_index", 0)),
            "background_color": int(self.project.get("background_color", 12)),
            "song": self._selected_song_name(),
            "objects": objects,
        }

    def refresh_bg_combo(self):
        vals = ["none"]
        if self.backgrounds_meta:
            for i, p in enumerate(self.backgrounds_meta.get("pngs", [])):
                vals.append(f"{i}: {os.path.basename(p)}")
        self.bg_combo["values"] = vals
        idx = int(self.project.get("background_index", -1))
        if 0 <= idx < len(vals) - 1:
            self.bg_combo_var.set(vals[idx + 1])
        else:
            self.bg_combo_var.set("none")
        self.refresh_bg_color_combo()
        self.refresh_tilemap_combo()

    def on_bg_combo_change(self):
        v = self.bg_combo_var.get()
        if v == "none":
            self.project["background_index"] = -1
            self.bg_index.set("-1")
        else:
            idx = int(v.split(":")[0])
            self.project["background_index"] = idx
            self.bg_index.set(str(idx))
        self.redraw_room_canvas()

    def refresh_bg_color_combo(self):
        vals = [f"{k}: {name}" for name, k in TEXT_COLOR_NAMES.items()]
        vals = sorted(set(vals), key=lambda s: int(s.split(":")[0]))
        self.bg_color_combo["values"] = vals
        try:
            room = self._active_room()
            cur = int(room.get("background_color", self.project.get("background_color", 12)))
        except Exception:
            cur = int(self.project.get("background_color", 12))
        self.bg_color_var.set(str(cur))
        for v in vals:
            if v.startswith(f"{cur}:"):
                self.bg_color_var.set(v)
                break

    def on_bg_color_change(self):
        v = self.bg_color_var.get()
        try:
            if ":" in v:
                idx = int(v.split(":")[0])
            else:
                idx = int(v.strip())
        except Exception:
            idx = 12
        self.project["background_color"] = idx
        self._active_room()["background_color"] = idx
        self.redraw_room_canvas()

    def refresh_song_combo(self):
        vals = ["none"]
        if self.songs_meta:
            for s in self.songs_meta.get("songs", []):
                n = str(s.get("name", "")).strip()
                if n:
                    vals.append(n)
        self.song_combo["values"] = vals
        cur = self._selected_song_name()
        if cur and cur in vals:
            self.room_song_var.set(cur)
        else:
            self.room_song_var.set("none")

    def refresh_tilemap_combo(self):
        vals = ["none"]
        tilemaps = self.project.get("tilemaps", [])
        for i, tm in enumerate(tilemaps):
            vals.append(f"{i}: {tm.get('name','map')}")
        self.room_tilemap_combo["values"] = vals
        tm_idx = int(self._active_room().get("tilemap_index", -1))
        if 0 <= tm_idx < len(tilemaps):
            self.room_tilemap_index.set(vals[tm_idx + 1])
        else:
            self.room_tilemap_index.set("none")

    def on_song_combo_change(self):
        self._save_current_room_fields()

    def on_room_tilemap_change(self):
        v = self.room_tilemap_index.get()
        if v == "none":
            self._active_room()["tilemap_index"] = -1
        else:
            try:
                idx = int(v.split(":")[0])
            except Exception:
                idx = -1
            self._active_room()["tilemap_index"] = idx
        self.redraw_room_canvas()

    def refresh_room_object_list(self):
        if not hasattr(self, "room_obj_list"):
            return
        self.room_obj_list.delete(0, tk.END)
        room_objs = self._active_room_objects()
        for i, o in enumerate(room_objs):
            fr = self._obj_preview_frame(o)
            self.room_obj_list.insert(
                tk.END, f"[{i}] {o.get('name','obj')} f{fr} ({int(o.get('x',0))},{int(o.get('y',0))}) {o.get('draw_mode','normal')}"
            )
        self.sync_room_selection()

    def add_selected_object_to_room(self):
        if self.selected_obj is None:
            return
        if self.selected_obj < 0 or self.selected_obj >= len(self.project.get("objects", [])):
            return
        base = self.project["objects"][self.selected_obj]
        room_objs = self._active_room_objects()
        # Room can now contain multiple instances of the same object name.
        room_objs.append(dict(base))
        self._sync_objects_from_rooms()
        self.selected_room_obj = len(room_objs) - 1
        self.refresh_room_object_list()
        self.refresh_object_list()
        self.redraw_room_canvas()

    def remove_selected_room_object(self):
        if self.selected_room_obj is None:
            return
        room_objs = self._active_room_objects()
        if self.selected_room_obj < 0 or self.selected_room_obj >= len(room_objs):
            return
        del room_objs[self.selected_room_obj]
        self.selected_room_obj = None
        self.refresh_room_object_list()
        self.redraw_room_canvas()

    def load_room_props_from_selected(self):
        if self.selected_room_obj is None:
            return
        room_objs = self._active_room_objects()
        if self.selected_room_obj < 0 or self.selected_room_obj >= len(room_objs):
            return
        o = room_objs[self.selected_room_obj]
        self.room_x.set(str(int(o.get("x", 0))))
        self.room_y.set(str(int(o.get("y", 0))))
        self.room_frame.set(str(self._obj_preview_frame(o)))
        self.room_mode.set(str(o.get("draw_mode", "normal")))
        self.room_angle.set(str(float(o.get("angle", 0.0))))
        self.room_scale.set(str(float(o.get("scale", 1.0))))

    def sync_room_selection(self):
        if not hasattr(self, "room_obj_list"):
            return
        self.room_obj_list.selection_clear(0, tk.END)
        if self.selected_room_obj is None:
            self.redraw_room_canvas()
            return
        if 0 <= self.selected_room_obj < self.room_obj_list.size():
            self.room_obj_list.selection_set(self.selected_room_obj)
        self.redraw_room_canvas()

    def select_room_object(self):
        sel = list(self.room_obj_list.curselection())
        if not sel:
            return
        i = sel[0]
        room_objs = self._active_room_objects()
        if i >= len(room_objs):
            return
        self.selected_room_obj = i
        self.load_room_props_from_selected()

    def apply_room_props(self):
        if self.selected_room_obj is None:
            return
        room_objs = self._active_room_objects()
        if self.selected_room_obj < 0 or self.selected_room_obj >= len(room_objs):
            return
        o = room_objs[self.selected_room_obj]
        try:
            ox = max(0, min(ROOM_W - 1, int(self.room_x.get())))
            oy = max(0, min(ROOM_H - 1, int(self.room_y.get())))
            of = max(0, int(self.room_frame.get()))
            om = self.room_mode.get()
            if om not in ("normal", "rotated", "scaled"):
                om = "normal"
            oa = float(self.room_angle.get())
            osf = max(0.01, float(self.room_scale.get()))
            o["x"] = ox
            o["y"] = oy
            o["draw_mode"] = om
            o["angle"] = oa
            o["scale"] = osf
            # Keep animation sequences intact. Only overwrite idle_frames when it is empty
            # or already a single-frame value.
            current_idle = str(o.get("idle_frames", "")).strip()
            if current_idle == "" or "," not in current_idle:
                o["idle_frames"] = str(of)
            self.obj_x.set(str(ox))
            self.obj_y.set(str(oy))
            self.obj_mode.set(om)
            self.angle.set(str(oa))
            self.scale.set(str(osf))
            self.idle_frames.set(str(o.get("idle_frames", "")))
            self.redraw_room_canvas()
        except Exception as e:
            messagebox.showerror("Invalid room props", str(e))

    def canvas_to_room(self, x, y):
        return int(x / CANVAS_SCALE), int(y / CANVAS_SCALE)

    def room_to_canvas(self, x, y):
        return int(x * CANVAS_SCALE), int(y * CANVAS_SCALE)

    def on_canvas_down(self, event):
        rx, ry = self.canvas_to_room(event.x, event.y)
        hit = None
        room_objs = self._active_room_objects()
        for i in range(len(room_objs) - 1, -1, -1):
            o = room_objs[i]
            if abs(int(o.get("x", 0)) - rx) <= 10 and abs(int(o.get("y", 0)) - ry) <= 10:
                hit = i
                break
        if hit is not None:
            self.selected_room_obj = hit
            self.dragging = True
            self.load_room_props_from_selected()

    def on_canvas_drag(self, event):
        if not self.dragging or self.selected_room_obj is None:
            return
        room_objs = self._active_room_objects()
        if self.selected_room_obj < 0 or self.selected_room_obj >= len(room_objs):
            return
        rx, ry = self.canvas_to_room(event.x, event.y)
        rx = max(0, min(ROOM_W - 1, rx))
        ry = max(0, min(ROOM_H - 1, ry))
        o = room_objs[self.selected_room_obj]
        o["x"] = rx
        o["y"] = ry
        self.obj_x.set(str(rx))
        self.obj_y.set(str(ry))
        self.room_x.set(str(rx))
        self.room_y.set(str(ry))
        self.redraw_room_canvas()

    def on_canvas_up(self, _event):
        self.dragging = False

    def redraw_room_canvas(self):
        if not hasattr(self, "room_canvas"):
            return
        c = self.room_canvas
        c.delete("all")
        c.create_rectangle(0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE, fill="#111", outline="")
        self.canvas_sprites = []

        bg_idx = int(self.project.get("background_index", -1))
        if 0 <= bg_idx < len(self.bg_images):
            img = self.bg_images[bg_idx]
            if img is not None:
                try:
                    self.canvas_bg = img.zoom(CANVAS_SCALE, CANVAS_SCALE)
                    c.create_image(0, 0, image=self.canvas_bg, anchor="nw")
                except Exception:
                    pass
        if self.canvas_bg is None and PIL_AVAILABLE and 0 <= bg_idx < len(self.bg_images_pil):
            pil = self.bg_images_pil[bg_idx]
            if pil is not None:
                try:
                    z = pil.resize((ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE), resample=Image.NEAREST)
                    self.canvas_bg = ImageTk.PhotoImage(z)
                    c.create_image(0, 0, image=self.canvas_bg, anchor="nw")
                except Exception:
                    pass
        if bg_idx < 0:
            try:
                room = self._active_room()
                bg_color = int(room.get("background_color", self.project.get("background_color", 12)))
            except Exception:
                bg_color = int(self.project.get("background_color", 12))
            c.create_rectangle(0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE,
                               fill=palette_color_hex(bg_color), outline="")

        # Tilemap rendering (back + mid)
        room = self._active_room()
        tm_idx = int(room.get("tilemap_index", -1))
        if tm_idx >= 0:
            tm = None
            try:
                tm = self.project.get("tilemaps", [])[tm_idx]
            except Exception:
                tm = None
            if tm and PIL_AVAILABLE:
                self._draw_room_tilemap(c, tm, draw_front=False)

        any_drawn = False
        room_objs = self._active_room_objects()
        for i, o in enumerate(room_objs):
            x, y = self.room_to_canvas(int(o.get("x", 0)), int(o.get("y", 0)))
            frame = self._obj_preview_frame(o)
            drawn = False
            if self.sprite_images and 0 <= frame < len(self.sprite_images):
                s = self.sprite_images[frame]
                if s is not None:
                    try:
                        z = s.zoom(CANVAS_SCALE, CANVAS_SCALE)
                        c.create_image(x, y, image=z, anchor="center")
                        self.canvas_sprites.append(z)
                        drawn = True
                    except Exception:
                        pass
            if not drawn and PIL_AVAILABLE and 0 <= frame < len(self.sprite_images_pil):
                pil = self.sprite_images_pil[frame]
                if pil is not None:
                    try:
                        z = pil.resize((pil.width * CANVAS_SCALE, pil.height * CANVAS_SCALE), resample=Image.NEAREST)
                        tk_img = ImageTk.PhotoImage(z)
                        c.create_image(x, y, image=tk_img, anchor="center")
                        self.canvas_sprites.append(tk_img)
                        drawn = True
                    except Exception:
                        pass
            if not drawn:
                c.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#ffd54f", outline="#222")
                c.create_text(x, y - 14, text=str(frame), fill="#fff")
            if i == self.selected_room_obj:
                c.create_rectangle(x - 14, y - 14, x + 14, y + 14, outline="#00e5ff")
            any_drawn = any_drawn or drawn

        c.create_rectangle(0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE, outline="#666", width=2)
        if not any_drawn and PIL_AVAILABLE:
            self.set_status("Sprites loaded but not rendered. Check image paths.")

    def _draw_room_tilemap(self, canvas, tm, draw_front=False):
        size = int(tm.get("tile_size", 16))
        w = int(tm.get("width", 1))
        h = int(tm.get("height", 1))
        tileset_idx = int(tm.get("tileset_index", -1))
        if tileset_idx < 0 or tileset_idx >= len(self.bg_images_pil):
            return
        pil = self.bg_images_pil[tileset_idx]
        if pil is None:
            return
        cols = max(1, pil.width // size)
        layers = tm.get("layers", {})
        for layer in ("back", "mid"):
            data = layers.get(layer, [])
            if len(data) != w * h:
                continue
            for y in range(h):
                for x in range(w):
                    tid = data[y * w + x]
                    if tid <= 0:
                        continue
                    idx = tid - 1
                    tx = idx % cols
                    ty = idx // cols
                    box = (tx * size, ty * size, tx * size + size, ty * size + size)
                    try:
                        tile = pil.crop(box)
                        tile = self._apply_magenta_key(tile)
                        tile = tile.resize((size * CANVAS_SCALE, size * CANVAS_SCALE), resample=Image.NEAREST)
                        img = ImageTk.PhotoImage(tile)
                        px = x * size * CANVAS_SCALE
                        py = y * size * CANVAS_SCALE
                        canvas.create_image(px, py, image=img, anchor="nw")
                        self.canvas_sprites.append(img)
                    except Exception:
                        pass
        if draw_front:
            front = layers.get("front", [])
            if len(front) == w * h:
                for y in range(h):
                    for x in range(w):
                        if front[y * w + x]:
                            px = x * size * CANVAS_SCALE
                            py = y * size * CANVAS_SCALE
                            canvas.create_rectangle(px, py, px + size * CANVAS_SCALE, py + size * CANVAS_SCALE,
                                                   outline="#ff5252")

    def open_tilemap_editor(self):
        if self.tilemap_window and tk.Toplevel.winfo_exists(self.tilemap_window):
            try:
                self.tilemap_window.deiconify()
                self.tilemap_window.lift()
            except Exception:
                pass
            return
        self._ensure_tilemaps()
        self._build_tilemap_editor()

    def _build_tilemap_editor(self):
        win = tk.Toplevel(self)
        self.tilemap_window = win
        win.title("TileMap Editor")
        win.configure(bg=THEME["bg"])
        win.geometry("980x620")
        win.protocol("WM_DELETE_WINDOW", self._close_tilemap_editor)

        top = tk.Frame(win, bg=THEME["bg"])
        top.pack(fill="x", padx=8, pady=6)

        tk.Label(top, text="Tilemap", bg=THEME["bg"], fg=THEME["text"]).pack(side="left")
        self.tilemap_pick_var = tk.StringVar(value="")
        self.tilemap_pick = ttk.Combobox(top, textvariable=self.tilemap_pick_var, state="readonly", width=24)
        self.tilemap_pick.pack(side="left", padx=(6, 8))
        self.tilemap_pick.bind("<<ComboboxSelected>>", lambda _e: self._on_tilemap_pick())
        tk.Button(top, text="New", command=self._tilemap_new).pack(side="left", padx=2)
        tk.Button(top, text="Delete", command=self._tilemap_delete).pack(side="left", padx=2)
        tk.Button(top, text="Rename", command=self._tilemap_rename).pack(side="left", padx=2)

        tk.Label(top, text="Tileset", bg=THEME["bg"], fg=THEME["text"]).pack(side="left", padx=(18, 4))
        self.tilemap_tileset_var = tk.StringVar(value="none")
        self.tilemap_tileset_combo = ttk.Combobox(top, textvariable=self.tilemap_tileset_var, state="readonly", width=26)
        self.tilemap_tileset_combo.pack(side="left", padx=(0, 8))
        self.tilemap_tileset_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_tilemap_tileset_change())

        tk.Label(top, text="Tile Size", bg=THEME["bg"], fg=THEME["text"]).pack(side="left", padx=(8, 4))
        self.tilemap_size_var = tk.StringVar(value=str(self.tilemap_tile_size))
        self.tilemap_size_combo = ttk.Combobox(top, textvariable=self.tilemap_size_var, state="readonly", values=["8", "16", "32"], width=6)
        self.tilemap_size_combo.pack(side="left")
        self.tilemap_size_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_tilemap_size_change())

        tk.Label(top, text="Layer", bg=THEME["bg"], fg=THEME["text"]).pack(side="left", padx=(12, 4))
        self.tilemap_layer_var = tk.StringVar(value=self.tilemap_layer)
        ttk.Combobox(top, textvariable=self.tilemap_layer_var, values=["back", "mid", "front"], state="readonly", width=8).pack(side="left")
        self.tilemap_layer_var.trace_add("write", lambda *_: self._on_tilemap_layer_change())

        tk.Checkbutton(top, text="Grid", variable=self.tilemap_show_grid, bg=THEME["bg"], fg=THEME["text"],
                       selectcolor=THEME["bg"], command=self._tilemap_redraw).pack(side="left", padx=(12, 0))

        tk.Button(top, text="Export tilemaps.h", command=self.export_tilemaps_header).pack(side="right", padx=4)
        tk.Button(top, text="Load tilemaps.h", command=self.load_tilemaps_header).pack(side="right", padx=4)

        body = tk.PanedWindow(win, orient="horizontal", sashrelief="raised", bg=THEME["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=6)

        left = tk.LabelFrame(body, text="Tileset", bg=THEME["bg"], fg=THEME["text"])
        body.add(left, width=300)

        ts_wrap = tk.Frame(left, bg=THEME["bg"])
        ts_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.tileset_canvas = tk.Canvas(ts_wrap, bg=THEME["panel"], highlightthickness=0)
        self.tileset_canvas.pack(side="left", fill="both", expand=True)
        ts_v = tk.Scrollbar(ts_wrap, orient="vertical", command=self.tileset_canvas.yview)
        ts_v.pack(side="right", fill="y")
        ts_h = tk.Scrollbar(left, orient="horizontal", command=self.tileset_canvas.xview)
        ts_h.pack(fill="x")
        self.tileset_canvas.configure(yscrollcommand=ts_v.set, xscrollcommand=ts_h.set)
        self.tileset_canvas.bind("<ButtonPress-1>", self._tileset_mouse_down)
        self.tileset_canvas.bind("<B1-Motion>", self._tileset_mouse_drag)
        self.tileset_canvas.bind("<ButtonRelease-1>", self._tileset_mouse_up)

        right = tk.LabelFrame(body, text="Tilemap", bg=THEME["bg"], fg=THEME["text"])
        body.add(right)
        self.tilemap_canvas = tk.Canvas(right, bg=THEME["panel"], width=ROOM_W * CANVAS_SCALE, height=ROOM_H * CANVAS_SCALE, highlightthickness=0)
        self.tilemap_canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.tilemap_canvas.bind("<ButtonPress-1>", self._tilemap_paint_start)
        self.tilemap_canvas.bind("<B1-Motion>", self._tilemap_paint_drag)
        self.tilemap_canvas.bind("<ButtonPress-3>", self._tilemap_erase_start)
        self.tilemap_canvas.bind("<B3-Motion>", self._tilemap_erase_drag)

        self._refresh_tilemap_ui()

    def _close_tilemap_editor(self):
        try:
            if self.tilemap_window:
                self.tilemap_window.destroy()
        finally:
            self.tilemap_window = None

    def _refresh_tilemap_ui(self):
        if not self.tilemap_window:
            return
        self._ensure_tilemaps()
        names = [f"{i}: {tm.get('name','map')}" for i, tm in enumerate(self.project.get("tilemaps", []))]
        self.tilemap_pick["values"] = names
        if names:
            idx = self.tilemap_selected or 0
            idx = max(0, min(idx, len(names) - 1))
            self.tilemap_selected = idx
            self.tilemap_pick_var.set(names[idx])
        self._refresh_tileset_combo()
        self._apply_tilemap_to_ui()

    def _refresh_tileset_combo(self):
        vals = ["none"]
        if self.backgrounds_meta:
            for i, p in enumerate(self.backgrounds_meta.get("pngs", [])):
                vals.append(f"{i}: {os.path.basename(p)}")
        self.tilemap_tileset_combo["values"] = vals
        tm = self._active_tilemap()
        if tm:
            idx = int(tm.get("tileset_index", -1))
            if 0 <= idx < len(vals) - 1:
                self.tilemap_tileset_var.set(vals[idx + 1])
            else:
                self.tilemap_tileset_var.set("none")

    def _on_tilemap_pick(self):
        try:
            idx = int(self.tilemap_pick_var.get().split(":")[0])
        except Exception:
            idx = 0
        self.tilemap_selected = idx
        self._apply_tilemap_to_ui()

    def _apply_tilemap_to_ui(self):
        tm = self._active_tilemap()
        if not tm:
            return
        self.tilemap_tile_size = int(tm.get("tile_size", 16))
        self.tilemap_size_var.set(str(self.tilemap_tile_size))
        self.tilemap_tileset_index = int(tm.get("tileset_index", -1))
        self.tilemap_layer = self.tilemap_layer_var.get() or "back"
        self._update_tileset_image()
        self._tilemap_redraw()

    def _on_tilemap_tileset_change(self):
        v = self.tilemap_tileset_var.get()
        if v == "none":
            self.tilemap_tileset_index = -1
        else:
            try:
                self.tilemap_tileset_index = int(v.split(":")[0])
            except Exception:
                self.tilemap_tileset_index = -1
        tm = self._active_tilemap()
        if tm:
            tm["tileset_index"] = self.tilemap_tileset_index
        self._update_tileset_image()
        self._tilemap_redraw()

    def _on_tilemap_size_change(self):
        try:
            size = int(self.tilemap_size_var.get())
        except Exception:
            size = 16
        if size <= 0:
            size = 16
        tm = self._active_tilemap()
        if tm and tm.get("tile_size") != size:
            tm["tile_size"] = size
            w = max(1, ROOM_W // size)
            h = max(1, ROOM_H // size)
            tm["width"] = w
            tm["height"] = h
            empty = [0] * (w * h)
            tm["layers"] = {"back": list(empty), "mid": list(empty), "front": list(empty)}
        self.tilemap_tile_size = size
        self._update_tileset_image()
        self._tilemap_redraw()

    def _on_tilemap_layer_change(self):
        self.tilemap_layer = self.tilemap_layer_var.get() or "back"

    def _tilemap_new(self):
        name = simpledialog.askstring("New Tilemap", "Tilemap name:", parent=self)
        if not name:
            return
        self.project.setdefault("tilemaps", []).append(self._default_tilemap(name))
        self.tilemap_selected = len(self.project["tilemaps"]) - 1
        self._refresh_tilemap_ui()

    def _tilemap_delete(self):
        tm = self._active_tilemap()
        if not tm:
            return
        if not messagebox.askyesno("Delete Tilemap", f"Delete '{tm.get('name','map')}'?"):
            return
        del self.project["tilemaps"][self.tilemap_selected]
        if self.tilemap_selected >= len(self.project["tilemaps"]):
            self.tilemap_selected = max(0, len(self.project["tilemaps"]) - 1)
        self._refresh_tilemap_ui()

    def _tilemap_rename(self):
        tm = self._active_tilemap()
        if not tm:
            return
        name = simpledialog.askstring("Rename Tilemap", "New name:", initialvalue=str(tm.get("name", "map")), parent=self)
        if not name:
            return
        tm["name"] = name
        self._refresh_tilemap_ui()

    def _tilemap_layer_data(self, layer):
        tm = self._active_tilemap()
        if not tm:
            return None
        layers = tm.get("layers", {})
        if layer not in layers:
            w = int(tm.get("width", 1))
            h = int(tm.get("height", 1))
            layers[layer] = [0] * (w * h)
        return layers[layer]

    def _tileset_info(self):
        idx = self.tilemap_tileset_index
        if idx < 0 or idx >= len(self.bg_images_pil):
            return None
        pil = self.bg_images_pil[idx]
        if pil is None:
            return None
        size = max(1, int(self.tilemap_tile_size))
        cols = max(1, pil.width // size)
        rows = max(1, pil.height // size)
        return {"pil": pil, "cols": cols, "rows": rows, "size": size}

    def _apply_magenta_key(self, img):
        if not PIL_AVAILABLE or img is None:
            return img
        try:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            data = list(img.getdata())
            for i, (r, g, b, a) in enumerate(data):
                if is_magenta_key(r, g, b):
                    data[i] = (r, g, b, 0)
            img.putdata(data)
            return img
        except Exception:
            return img

    def _update_tileset_image(self):
        if not self.tilemap_window:
            return
        self.tilemap_tileset_cache = {}
        info = self._tileset_info()
        self.tileset_canvas.delete("all")
        self.tilemap_tileset_photo = None
        if not info:
            self.tileset_canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        pil = self._apply_magenta_key(info["pil"])
        self.tilemap_tileset_photo = ImageTk.PhotoImage(pil) if PIL_AVAILABLE else None
        if self.tilemap_tileset_photo:
            self.tileset_canvas.create_image(0, 0, image=self.tilemap_tileset_photo, anchor="nw")
            self.tileset_canvas.configure(scrollregion=(0, 0, pil.width, pil.height))
        if self.tilemap_sel_rect:
            self.tileset_canvas.delete(self.tilemap_sel_rect)
            self.tilemap_sel_rect = None

    def _tileset_mouse_down(self, event):
        if not self._tileset_info():
            return
        self._tileset_select_start = (self.tileset_canvas.canvasx(event.x), self.tileset_canvas.canvasy(event.y))
        self._tileset_update_selection(self._tileset_select_start, self._tileset_select_start)

    def _tileset_mouse_drag(self, event):
        if not self._tileset_info():
            return
        cur = (self.tileset_canvas.canvasx(event.x), self.tileset_canvas.canvasy(event.y))
        self._tileset_update_selection(self._tileset_select_start, cur)

    def _tileset_mouse_up(self, event):
        if not self._tileset_info():
            return
        cur = (self.tileset_canvas.canvasx(event.x), self.tileset_canvas.canvasy(event.y))
        self._tileset_update_selection(self._tileset_select_start, cur)

    def _tileset_update_selection(self, start, end):
        info = self._tileset_info()
        if not info:
            return
        size = info["size"]
        sx, sy = start
        ex, ey = end
        x0 = int(min(sx, ex) // size)
        y0 = int(min(sy, ey) // size)
        x1 = int(max(sx, ex) // size)
        y1 = int(max(sy, ey) // size)
        x0 = max(0, min(x0, info["cols"] - 1))
        x1 = max(0, min(x1, info["cols"] - 1))
        y0 = max(0, min(y0, info["rows"] - 1))
        y1 = max(0, min(y1, info["rows"] - 1))
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        tiles = []
        for yy in range(y0, y0 + h):
            for xx in range(x0, x0 + w):
                tiles.append(yy * info["cols"] + xx + 1)
        self.tilemap_sel = {"w": w, "h": h, "tiles": tiles}
        if self.tilemap_sel_rect:
            self.tileset_canvas.delete(self.tilemap_sel_rect)
        self.tilemap_sel_rect = self.tileset_canvas.create_rectangle(
            x0 * size, y0 * size, (x1 + 1) * size, (y1 + 1) * size,
            outline="#FFD166", width=2
        )

    def _tilemap_paint_start(self, event):
        self._tilemap_apply_paint(event, erase=False)

    def _tilemap_paint_drag(self, event):
        self._tilemap_apply_paint(event, erase=False)

    def _tilemap_erase_start(self, event):
        self._tilemap_apply_paint(event, erase=True)

    def _tilemap_erase_drag(self, event):
        self._tilemap_apply_paint(event, erase=True)

    def _tilemap_apply_paint(self, event, erase=False):
        tm = self._active_tilemap()
        if not tm:
            return
        size = int(tm.get("tile_size", 16))
        w = int(tm.get("width", 1))
        h = int(tm.get("height", 1))
        x = int(self.tilemap_canvas.canvasx(event.x) // (size * CANVAS_SCALE))
        y = int(self.tilemap_canvas.canvasy(event.y) // (size * CANVAS_SCALE))
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        layer = self.tilemap_layer
        data = self._tilemap_layer_data(layer)
        if data is None:
            return
        if layer == "front":
            idx = y * w + x
            data[idx] = 0 if erase else 1
        else:
            sel = self.tilemap_sel
            for dy in range(sel["h"]):
                for dx in range(sel["w"]):
                    mx = x + dx
                    my = y + dy
                    if mx < 0 or my < 0 or mx >= w or my >= h:
                        continue
                    idx = my * w + mx
                    if erase:
                        data[idx] = 0
                    else:
                        data[idx] = sel["tiles"][dy * sel["w"] + dx]
        self._tilemap_redraw()

    def _tilemap_redraw(self):
        if not hasattr(self, "tilemap_canvas"):
            return
        tm = self._active_tilemap()
        if not tm:
            return
        size = int(tm.get("tile_size", 16))
        w = int(tm.get("width", 1))
        h = int(tm.get("height", 1))
        c = self.tilemap_canvas
        c.delete("all")
        c.create_rectangle(0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE, fill="#111", outline="")
        info = self._tileset_info()
        if info and PIL_AVAILABLE:
            for layer in ("back", "mid"):
                data = self._tilemap_layer_data(layer)
                if not data:
                    continue
                for y in range(h):
                    for x in range(w):
                        tid = data[y * w + x]
                        if tid <= 0:
                            continue
                        img = self._tileset_tile_image(info, tid)
                        if img is None:
                            continue
                        px = x * size * CANVAS_SCALE
                        py = y * size * CANVAS_SCALE
                        c.create_image(px, py, image=img, anchor="nw")
        # Collision/front overlay
        front = self._tilemap_layer_data("front")
        if front:
            for y in range(h):
                for x in range(w):
                    if front[y * w + x]:
                        px = x * size * CANVAS_SCALE
                        py = y * size * CANVAS_SCALE
                        c.create_rectangle(px, py, px + size * CANVAS_SCALE, py + size * CANVAS_SCALE,
                                           outline="#ff5252")
        if self.tilemap_show_grid.get():
            for x in range(w + 1):
                px = x * size * CANVAS_SCALE
                c.create_line(px, 0, px, h * size * CANVAS_SCALE, fill="#2b2b2b")
            for y in range(h + 1):
                py = y * size * CANVAS_SCALE
                c.create_line(0, py, w * size * CANVAS_SCALE, py, fill="#2b2b2b")

    def _tileset_tile_image(self, info, tile_id):
        if tile_id <= 0:
            return None
        key = (self.tilemap_tileset_index, info["size"], tile_id)
        if key in self.tilemap_tileset_cache:
            return self.tilemap_tileset_cache[key]
        cols = info["cols"]
        idx = tile_id - 1
        tx = idx % cols
        ty = idx // cols
        pil = info["pil"]
        size = info["size"]
        box = (tx * size, ty * size, tx * size + size, ty * size + size)
        try:
            tile = pil.crop(box)
            tile = self._apply_magenta_key(tile)
            tile = tile.resize((size * CANVAS_SCALE, size * CANVAS_SCALE), resample=Image.NEAREST)
            img = ImageTk.PhotoImage(tile)
            self.tilemap_tileset_cache[key] = img
            return img
        except Exception:
            return None

    def _emit_frames_array(self, obj_name, state_name, frames):
        ident = sanitize_ident(f"{obj_name}_{state_name}_frames")
        body = ", ".join(str(x) for x in frames)
        return ident, f"static const unsigned short {ident}[] = {{{body}}};"

    def export_program(self):
        self._commit_ui_state()
        self._save_current_room_fields()
        self._ensure_rooms()
        self.project["name"] = self.project_name.get().strip() or "game_project"
        try:
            self.project["background_index"] = int(self.bg_index.get().strip())
        except Exception:
            self.project["background_index"] = 0

        out = filedialog.asksaveasfilename(
            title="Export program (.masa)",
            defaultextension=".masa",
            filetypes=[("MASA files", "*.masa"), ("All files", "*.*")],
            initialfile=f"{self.project['name']}.masa",
        )
        if not out:
            return
        self._export_program_to(out, silent=False)

    def _export_program_to(self, out, silent=False):
        self._ensure_rooms()
        self._save_current_room_fields()
        self._sync_objects_from_rooms()
        objects = [dict(o) for o in self.project.get("objects", [])]
        rooms = self.project.get("rooms", [])
        if not isinstance(rooms, list):
            rooms = []
        if not rooms:
            # Fallback: export at least one room so runtime doesn't auto-activate all objects.
            room = self._room_from_project_fields(self.project.get("name", "room0"))
            try:
                active = self._active_room()
                if isinstance(active.get("objects"), list) and active["objects"]:
                    room["objects"] = [dict(o) for o in active["objects"]]
                room["background_index"] = int(active.get("background_index", room["background_index"]))
                room["background_color"] = int(active.get("background_color", room["background_color"]))
                room["song"] = str(active.get("song", room["song"]))
                room["tilemap_index"] = int(active.get("tilemap_index", room["tilemap_index"]))
                room["name"] = str(active.get("name", room["name"]))
            except Exception:
                pass
            rooms = [room]
            self.project["rooms"] = rooms
        if not silent:
            self.log(f"Export rooms: {len(rooms)}")
        else:
            self.log(f"Export rooms: {len(rooms)}")
        if not objects and not rooms:
            if not silent:
                messagebox.showwarning("No objects", "No objects found in the project to export.")
            else:
                self.log("Export failed: no objects.")
            return False

        def _normalize_obj(o, fallback_name="obj"):
            out = dict(o)
            out.setdefault("name", fallback_name)
            out.setdefault("x", 160)
            out.setdefault("y", 100)
            out.setdefault("draw_mode", "normal")
            out.setdefault("start_state", "idle")
            out.setdefault("idle_frames", "0")
            out.setdefault("walk_frames", "")
            out.setdefault("run_frames", "")
            out.setdefault("jump_frames", "")
            out.setdefault("idle_fps", 8)
            out.setdefault("walk_fps", 8)
            out.setdefault("run_fps", 10)
            out.setdefault("jump_fps", 8)
            out.setdefault("angle", 0.0)
            out.setdefault("scale", 1.0)
            out.setdefault("persistent", False)
            out.setdefault("script_update", "")
            return out

        def _canonical_name(name, known):
            tok = str(name or "").strip()
            if not tok:
                return tok
            # Collapse auto-clone suffix chains like:
            # obj_small_rock_2 -> obj_small_rock
            # obj_small_rock_2_2 -> obj_small_rock
            cur = tok
            while True:
                m = re.match(r"^(.+?)_(\d+)$", cur)
                if not m:
                    break
                base = m.group(1)
                if base in known:
                    cur = base
                    continue
                # Keep stripping one level if possible; final membership check below.
                cur = base
            if cur in known:
                return cur
            m = re.match(r"^(.+?)_(\d+)$", tok)
            if m and m.group(1) in known:
                return m.group(1)
            return tok

        # Prototypes are object definitions (type), instances are room placements.
        proto_by_name = {}
        for i, o in enumerate(objects):
            no = _normalize_obj(o, f"obj_{i}")
            pname = str(no.get("name", f"obj_{i}")).strip()
            if pname and pname not in proto_by_name:
                proto_by_name[pname] = no
        known_proto_names = set(proto_by_name.keys())

        def _extract_obj_tokens(script_src):
            out = set()
            sig = parse_masa_signals(script_src or "")
            for c in sig.get("colliders", []):
                tok = str(c.get("other", "")).strip()
                if tok:
                    out.add(tok)
            for a in sig.get("actions", []):
                at = str(a.get("type", ""))
                if at in ("spawn", "spawn_bullet"):
                    tok = str(a.get("obj", "")).strip()
                    if tok:
                        out.add(tok)
                elif at in ("destroy", "stop", "set_input"):
                    tok = str(a.get("target", "")).strip()
                    if tok:
                        out.add(tok)
            return out

        # Keep only prototypes reachable from room objects through script references.
        reachable_proto_names = set()
        room_seed_names = set()
        if isinstance(rooms, list):
            for room in rooms:
                room_objs = room.get("objects", [])
                if not isinstance(room_objs, list):
                    continue
                for ro in room_objs:
                    raw = str(ro.get("name", "")).strip()
                    if not raw:
                        continue
                    canon = _canonical_name(raw, known_proto_names)
                    seed = canon if canon in proto_by_name else raw
                    if seed in proto_by_name:
                        room_seed_names.add(seed)
        pending = list(room_seed_names)
        while pending:
            cur = pending.pop()
            if cur in reachable_proto_names:
                continue
            reachable_proto_names.add(cur)
            script_src = str(proto_by_name.get(cur, {}).get("script_update", "") or "")
            for tok in _extract_obj_tokens(script_src):
                low = tok.lower()
                if low in ("self", "other"):
                    continue
                if tok.isdigit() or (tok.startswith("-") and tok[1:].isdigit()):
                    continue
                canon = _canonical_name(tok, known_proto_names)
                nxt = canon if canon in proto_by_name else tok
                if nxt in proto_by_name and nxt not in reachable_proto_names:
                    pending.append(nxt)
        # Keep exporter object cap aligned with runtime constant when possible.
        max_runtime_objects = 30
        try:
            runtime_h = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "MasaRuntime.h"))
            if os.path.exists(runtime_h):
                txt_rt = open(runtime_h, "r", encoding="utf-8", errors="ignore").read()
                m_rt = re.search(r"static\s+const\s+int\s+kMaxObjects\s*=\s*(\d+)\s*;", txt_rt)
                if m_rt:
                    max_runtime_objects = max(1, int(m_rt.group(1)))
        except Exception:
            pass
        if not reachable_proto_names:
            reachable_proto_names = set(proto_by_name.keys())
        room_instance_id_map = {}
        if isinstance(rooms, list) and rooms:
            runtime_instances = []
            type_names_in_rooms = set()
            for ri, room in enumerate(rooms):
                room_objs = room.get("objects", [])
                if not isinstance(room_objs, list):
                    continue
                for oi, ro in enumerate(room_objs):
                    raw_name = str(ro.get("name", f"obj_{oi}")).strip()
                    canonical = _canonical_name(raw_name, known_proto_names)
                    # Prefer the base type when this looks like an auto-clone suffix.
                    if canonical in proto_by_name:
                        source_name = canonical
                    elif raw_name in proto_by_name:
                        source_name = raw_name
                    else:
                        source_name = canonical or raw_name
                    base = proto_by_name.get(source_name)
                    if base is None:
                        base = _normalize_obj(ro, source_name or f"obj_{oi}")
                    inst = dict(base)
                    inst.update(dict(ro))
                    inst["name"] = raw_name or source_name or f"obj_{oi}"
                    inst["_type_name"] = source_name or inst["name"]
                    inst["_instance_name"] = f"room{ri}_obj{oi}_{inst['name']}"
                    runtime_instances.append(inst)
                    type_names_in_rooms.add(str(inst["_type_name"]).strip())
                    room_instance_id_map[(ri, oi)] = len(runtime_instances) - 1
            # Keep prototypes that are not placed in room but are referenced by scripts
            # (for example bullets/smoke spawned by signals).
            for pname, pobj in proto_by_name.items():
                p = str(pname).strip()
                if p not in reachable_proto_names:
                    continue
                if not p or p in type_names_in_rooms:
                    continue
                inst = dict(pobj)
                inst["name"] = p
                inst["_type_name"] = p
                inst["_instance_name"] = f"proto_{p}"
                runtime_instances.append(inst)

            # Auto-grow pools for spawn-only object classes so repeated spawns
            # do not overwrite a single instance.
            spawn_ref_count = {}
            for o in runtime_instances:
                script_src = str(o.get("script_update", "") or "")
                sig = parse_masa_signals(script_src)
                for act in sig.get("actions", []):
                    if act.get("type") != "spawn":
                        continue
                    tok = str(act.get("obj", "")).strip()
                    if not tok:
                        continue
                    tl = tok.lower()
                    if tl in ("self", "other") or tok.isdigit() or (tok.startswith("-") and tok[1:].isdigit()):
                        continue
                    tcanon = _canonical_name(tok, known_proto_names)
                    spawn_ref_count[tcanon] = int(spawn_ref_count.get(tcanon, 0)) + 1
            proto_pool_traits = {}
            for pname, pobj in proto_by_name.items():
                pscript = str(pobj.get("script_update", "") or "")
                psig = parse_masa_signals(pscript)
                pinputs = parse_masa_input_binds(pscript)
                ppool = parse_masa_pool(pscript)
                pactions = list(psig.get("actions", [])) if isinstance(psig, dict) else []
                pcolliders = list(psig.get("colliders", [])) if isinstance(psig, dict) else []
                # "Cheap passive" spawned types are good candidates for deeper pools:
                # they usually act like debris/enemies/projectiles that don't carry
                # lots of per-owner signal logic, so cloning them costs object slots
                # much more than signal-action budget.
                proto_pool_traits[str(pname).strip()] = {
                    "cheap_passive": (len(pactions) == 0 and len(pinputs) == 0),
                    "action_count": len(pactions),
                    "collider_count": len(pcolliders),
                    "pool_reserve": max(0, int(ppool.get("reserve", 0))),
                    "pool_priority": int(ppool.get("priority", 0)),
                }

            # Generic pool growth strategy:
            # - prioritize types with more spawn references,
            # - avoid game-specific name heuristics so this works across genres,
            # - give deeper pools to cheap passive spawned types because they are
            #   the ones most likely to saturate under gameplay fanout.
            for tname, cnt in sorted(
                spawn_ref_count.items(),
                key=lambda kv: (
                    -int(proto_pool_traits.get(str(kv[0]).strip(), {}).get("pool_priority", 0)),
                    -int(kv[1]),
                    str(kv[0])
                )
            ):
                if len(runtime_instances) >= max_runtime_objects:
                    break
                proto = proto_by_name.get(tname)
                if proto is None:
                    continue
                traits = proto_pool_traits.get(tname, {})
                cheap_passive = bool(traits.get("cheap_passive", False))
                pool_reserve = max(0, int(traits.get("pool_reserve", 0)))
                cur = 0
                for ro in runtime_instances:
                    if str(ro.get("_type_name", "")).strip() == tname:
                        cur += 1
                # If a type already exists in-room, add a moderate extra pool so
                # spawn targets are less likely to collide with live instances.
                # For spawn-only types, reserve a deeper generic pool.
                cnt_i = max(1, int(cnt))
                # Generic fanout-aware sizing:
                # - Deep pools only for high fanout targets (cnt_i >= 2).
                # - Keep low fanout types (common FX spawns) lightweight to avoid
                #   inflating owners/signalActions beyond runtime budgets.
                if tname in type_names_in_rooms:
                    if cnt_i >= 2:
                        if cheap_passive:
                            desired = cur + max(6, min(18, cnt_i * 5))
                        else:
                            desired = cur + max(4, min(10, cnt_i * 3))
                    else:
                        desired = cur + (3 if cheap_passive else 2)
                else:
                    if cnt_i >= 2:
                        if cheap_passive:
                            desired = max(cur + 8, min(max_runtime_objects, max(12, cnt_i * 8)))
                        else:
                            desired = max(cur + 4, min(cur + 10, max(4, cnt_i * 3)))
                    else:
                        desired = cur + (3 if cheap_passive else 2)
                desired = max(desired, pool_reserve)
                while cur < desired and len(runtime_instances) < max_runtime_objects:
                    inst = dict(proto)
                    inst["name"] = tname
                    inst["_type_name"] = tname
                    inst["_instance_name"] = f"proto_{tname}_{cur+1}"
                    runtime_instances.append(inst)
                    cur += 1
            objects = runtime_instances
        else:
            objects = list(proto_by_name.values())

        if len(objects) > max_runtime_objects:
            self.log(f"Warning: exported instances ({len(objects)}) exceed runtime limit ({max_runtime_objects}); trimming.")
            objects = objects[:max_runtime_objects]
            room_instance_id_map = {
                k: v for k, v in room_instance_id_map.items()
                if v < max_runtime_objects
            }

        script = bytearray()
        bounds_written = False
        rooms_enabled = isinstance(rooms, list) and len(rooms) > 0

        prepared = []
        for obj_id, obj in enumerate(objects):
            x = int(obj.get("x", 160))
            y = int(obj.get("y", 100))
            frame = self._obj_preview_frame(obj)
            script_text = str(obj.get("script_update", "") or "")
            behavior = parse_masa_behavior(script_text)
            idle_frames_raw = str(obj.get("idle_frames", "") or "")
            anim_frames = []
            if idle_frames_raw.strip():
                for part in idle_frames_raw.replace(";", ",").split(","):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        anim_frames.append(int(part))
                    except Exception:
                        pass
            anim_frames = [f for f in anim_frames if f >= 0]
            if len(anim_frames) > 16:
                anim_frames = anim_frames[:16]
            try:
                anim_fps = int(obj.get("idle_fps", 8))
            except Exception:
                anim_fps = 8
            script_src = str(obj.get("script_update", ""))
            texts = parse_masa_texts(script_src)
            shapes = parse_masa_shapes(script_src)
            spawns = parse_masa_spawns(script_src)
            signals = parse_masa_signals(script_src)
            textboxes = parse_masa_textboxes(script_src)
            choices = parse_masa_choices(script_src)
            input_binds = parse_masa_input_binds(script_src)
            bg_scroll_x, bg_scroll_y = parse_masa_bg_scroll(script_src)
            alarms = parse_masa_alarm(script_src)
            music = parse_masa_music(script_src)
            beeps = parse_masa_beeps(script_src)
            hud = parse_masa_hud(script_src)
            vars_info = parse_masa_vars(script_src)
            prepared.append((obj_id, x, y, frame, behavior, anim_frames, anim_fps, texts, shapes, spawns, signals, textboxes, choices, input_binds, bg_scroll_x, bg_scroll_y, alarms, music, hud, vars_info, beeps))

        persistent_any = rooms_enabled or any(
            bool(p[4].get("enabled")) or p[4].get("accel") is not None or p[4].get("friction") is not None or len(p[5]) > 1 or bool(p[4].get("input_enabled")) or len(p[7]) > 0 or len(p[8]) > 0 or len(p[9]) > 0 or (p[10].get("hitbox") is not None) or len(p[10].get("colliders", [])) > 0 or len(p[10].get("actions", [])) > 0 or len(p[11]) > 0 or len(p[12]) > 0 or len(p[13]) > 0 or (p[14] is not None) or (p[15] is not None) or len(p[16]) > 0 or len(p[17]) > 0 or bool(p[18].get("draw")) or bool(p[18].get("set")) or len(p[18].get("adds", [])) > 0 or len(p[19].get("set", [])) > 0 or len(p[19].get("add", [])) > 0 or len(p[19].get("text", [])) > 0 or len(p[20]) > 0
            for p in prepared
        )

        obj_name_to_id = {}
        obj_type_to_ids = {}
        spawn_pool_ids_by_type = {}
        instance_name_to_id = {}
        behavior_by_id = {}
        for i, o in enumerate(objects):
            obj_name = str(o.get("name", f"obj_{i}")).strip()
            type_name = str(o.get("_type_name", obj_name)).strip()
            inst_name = str(o.get("_instance_name", "")).strip()
            if obj_name and obj_name not in obj_name_to_id:
                obj_name_to_id[obj_name] = i
            if type_name and type_name not in obj_name_to_id:
                obj_name_to_id[type_name] = i
            for key in (obj_name, type_name, _canonical_name(obj_name, known_proto_names)):
                if not key:
                    continue
                obj_type_to_ids.setdefault(key, [])
                if i not in obj_type_to_ids[key]:
                    obj_type_to_ids[key].append(i)
            if type_name and inst_name.startswith("proto_"):
                spawn_pool_ids_by_type.setdefault(type_name, [])
                spawn_pool_ids_by_type[type_name].append(i)
                canon_type = _canonical_name(type_name, known_proto_names)
                if canon_type:
                    spawn_pool_ids_by_type.setdefault(canon_type, [])
                    if i not in spawn_pool_ids_by_type[canon_type]:
                        spawn_pool_ids_by_type[canon_type].append(i)
            if inst_name:
                instance_name_to_id[inst_name] = i
        for obj_id, x, y, frame, behavior, anim_frames, anim_fps, texts, shapes, spawns, signals, textboxes, choices, input_binds, bg_scroll_x, bg_scroll_y, alarms, music, hud, vars_info, beeps in prepared:
            behavior_by_id[obj_id] = behavior
        prepared_by_id = {int(p[0]): p for p in prepared}

        def _resolve_obj_ids(token, fallback):
            if token is None:
                return [fallback]
            if isinstance(token, int):
                return [token]
            tok = str(token).strip()
            if not tok:
                return [fallback]
            low = tok.lower()
            if low == "self":
                return [fallback]
            if tok in instance_name_to_id:
                return [int(instance_name_to_id[tok])]
            if tok.isdigit() or (tok.startswith("-") and tok[1:].isdigit()):
                try:
                    return [int(tok)]
                except Exception:
                    return [fallback]
            ids = list(obj_type_to_ids.get(tok, []))
            if not ids:
                ids = list(obj_type_to_ids.get(_canonical_name(tok, known_proto_names), []))
            if not ids and tok:
                # Fallback: include clone-suffixed keys (obj_enemy_2, obj_enemy_2_2, ...)
                # when querying by base type (obj_enemy).
                prefix = tok + "_"
                for key, vals in obj_type_to_ids.items():
                    if key == tok or key.startswith(prefix):
                        for v in vals:
                            if v not in ids:
                                ids.append(v)
            if not ids and tok in obj_name_to_id:
                ids = [obj_name_to_id[tok]]
            if not ids:
                return [fallback]
            return ids

        def _resolve_obj_id(token, fallback):
            ids = _resolve_obj_ids(token, fallback)
            if ids:
                return int(ids[0])
            return int(fallback)

        spawn_rr_cursor = {}

        def _resolve_spawn_target(token, fallback):
            tok = str(token if token is not None else "").strip()
            tcanon = _canonical_name(tok, known_proto_names)
            ids = list(spawn_pool_ids_by_type.get(tok, []))
            if not ids and tcanon:
                ids = list(spawn_pool_ids_by_type.get(tcanon, []))
            if not ids:
                ids = _resolve_obj_ids(token, fallback)
            if not ids:
                return int(fallback)
            key = tok
            if not key:
                key = str(fallback)
            pos = int(spawn_rr_cursor.get(key, 0))
            target = int(ids[pos % len(ids)])
            spawn_rr_cursor[key] = pos + 1
            return target

        def _spawn_pool_ids_for_token(token):
            tok = str(token if token is not None else "").strip()
            if not tok:
                return []
            out = list(spawn_pool_ids_by_type.get(tok, []))
            canon = _canonical_name(tok, known_proto_names)
            if canon:
                for v in spawn_pool_ids_by_type.get(canon, []):
                    if v not in out:
                        out.append(v)
            return out

        SPAWN_COORD_SOURCE = 32767
        SPAWN_COORD_OTHER = 32766

        def _encode_spawn_coord(token, axis):
            tok = str(token if token is not None else "0").strip().lower()
            if axis == "x":
                if tok in ("self_x", "source_x"):
                    return SPAWN_COORD_SOURCE
                if tok == "other_x":
                    return SPAWN_COORD_OTHER
            else:
                if tok in ("self_y", "source_y"):
                    return SPAWN_COORD_SOURCE
                if tok == "other_y":
                    return SPAWN_COORD_OTHER
            try:
                return int(float(tok))
            except Exception:
                return 0

        export_obj_ids = set(range(len(objects)))
        if rooms_enabled and isinstance(rooms, list) and rooms:
            try:
                active_room_idx = int(self.project.get("active_room", 0))
            except Exception:
                active_room_idx = 0
            seed_ids = set()
            for (ri, _oi), rid in room_instance_id_map.items():
                if int(ri) == int(active_room_idx) and 0 <= int(rid) < len(objects):
                    seed_ids.add(int(rid))
            if seed_ids:
                export_obj_ids = set(seed_ids)
                q = list(seed_ids)
                while q:
                    cur = int(q.pop())
                    p = prepared_by_id.get(cur)
                    if p is None:
                        continue
                    # p tuple indices:
                    # 9=spawns, 10=signals
                    p_spawns = p[9]
                    p_signals = p[10]
                    # Direct MASA_SPAWN
                    for sp in p_spawns:
                        try:
                            if sp and sp[0] == "spawn":
                                tid = int(sp[1])
                                if 0 <= tid < len(objects) and tid not in export_obj_ids:
                                    export_obj_ids.add(tid)
                                    q.append(tid)
                        except Exception:
                            pass
                    # Signal-driven spawns / bullets
                    for act in p_signals.get("actions", []):
                        at = str(act.get("type", "")).strip().lower()
                        if at == "spawn":
                            tok = act.get("obj", "")
                            # Include full pool for this type so round-robin spawn
                            # targets always have their behavior exported.
                            for pid in _spawn_pool_ids_for_token(tok):
                                try:
                                    pi = int(pid)
                                except Exception:
                                    continue
                                if 0 <= pi < len(objects) and pi not in export_obj_ids:
                                    export_obj_ids.add(pi)
                                    q.append(pi)
                            tid = _resolve_spawn_target(tok, cur)
                            if 0 <= int(tid) < len(objects) and int(tid) not in export_obj_ids:
                                export_obj_ids.add(int(tid))
                                q.append(int(tid))
                        elif at == "spawn_bullet":
                            tid = _resolve_obj_id(act.get("obj"), cur)
                            if 0 <= int(tid) < len(objects) and int(tid) not in export_obj_ids:
                                export_obj_ids.add(int(tid))
                                q.append(int(tid))
            if not silent:
                self.log(f"Script export filter: active room objects={len(seed_ids) if 'seed_ids' in locals() else 0}, exported owners={len(export_obj_ids)} / {len(objects)}")
                try:
                    export_type_counts = {}
                    for oid in sorted(export_obj_ids):
                        if not (0 <= int(oid) < len(objects)):
                            continue
                        tname = str(objects[int(oid)].get("_type_name", objects[int(oid)].get("name", f"obj_{oid}"))).strip()
                        if not tname:
                            tname = f"obj_{oid}"
                        export_type_counts[tname] = int(export_type_counts.get(tname, 0)) + 1
                    top_pools = sorted(export_type_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
                    if top_pools:
                        summary = ", ".join([f"{nm}:{cnt}" for nm, cnt in top_pools[:10]])
                        self.log(f"Export type pools: {summary}")
                except Exception:
                    pass

        export_prepared = [p for p in prepared if p[0] in export_obj_ids]
        export_prepared.sort(key=lambda p: int(p[0]))
        skip_beep_count = 0
        beep_drop_quota = {}
        # Defaults are fallbacks only; real values are read from MasaRuntime.h.
        runtime_limits = {
            "kMaxObjects": 30,
            "kMaxSignals": 16,
            "kMaxColliders": 28,
            "kMaxSignalActions": 30,
            "kMaxInputBinds": 14,
            "kMaxAlarms": 6,
        }
        try:
            runtime_h = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "MasaRuntime.h"))
            if os.path.exists(runtime_h):
                txt = open(runtime_h, "r", encoding="utf-8", errors="ignore").read()
                for k in list(runtime_limits.keys()):
                    m = re.search(rf"static\s+const\s+int\s+{k}\s*=\s*(\d+)\s*;", txt)
                    if m:
                        runtime_limits[k] = int(m.group(1))
        except Exception:
            pass
        signal_action_budget = int(runtime_limits.get("kMaxSignalActions", 30))
        if not silent:
            try:
                est_actions = 0
                by_owner = []
                type_counts = {}
                beep_candidates = []
                beep_total_by_key = {}
                beep_keep_min_by_key = {}
                total_colliders = 0
                total_input_binds = 0
                used_signal_slots = set()
                max_alarm_slot_used = -1
                for p in export_prepared:
                    oid = int(p[0])
                    sig = p[10] if len(p) > 10 else {}
                    acts = list(sig.get("actions", [])) if isinstance(sig, dict) else []
                    c = len(acts)
                    cols = list(sig.get("colliders", [])) if isinstance(sig, dict) else []
                    # Colliders are compiled as pairwise entries (objA,objB).
                    # Count expanded pairs, not just directive count.
                    for col in cols:
                        try:
                            expanded = _resolve_obj_ids(col.get("other"), oid)
                            n = 0
                            for other in expanded:
                                try:
                                    oi = int(other)
                                except Exception:
                                    continue
                                if 0 <= oi < max_runtime_objects:
                                    n += 1
                            total_colliders += n if n > 0 else 1
                        except Exception:
                            total_colliders += 1
                    for col in cols:
                        try:
                            used_signal_slots.add(int(col.get("slot", 0)))
                        except Exception:
                            pass
                    for act in acts:
                        try:
                            used_signal_slots.add(int(act.get("slot", 0)))
                        except Exception:
                            pass
                    collide_slots = set()
                    for col in sig.get("colliders", []):
                        try:
                            collide_slots.add(int(col.get("slot", 0)))
                        except Exception:
                            pass
                    slot_beep_count = {}
                    for a in acts:
                        t = str(a.get("type", "")).strip().lower()
                        if t == "beep":
                            try:
                                sl = int(a.get("slot", 0))
                            except Exception:
                                sl = 0
                            slot_beep_count[sl] = int(slot_beep_count.get(sl, 0)) + 1
                    for a in acts:
                        t = str(a.get("type", "")).strip().lower()
                        type_counts[t] = int(type_counts.get(t, 0)) + 1
                        if t == "beep":
                            try:
                                sl = int(a.get("slot", 0))
                            except Exception:
                                sl = 0
                            key = (oid, sl)
                            beep_total_by_key[key] = int(beep_total_by_key.get(key, 0)) + 1
                            if sl in collide_slots:
                                beep_keep_min_by_key[key] = 1
                            else:
                                beep_keep_min_by_key.setdefault(key, 0)
                            try:
                                dur = int(float(a.get("duration", 0)))
                            except Exception:
                                dur = 0
                            # Generic trim score (higher = dropped earlier):
                            # - non-collision slot beeps are less critical to gameplay
                            # - duplicate beeps on same owner+slot are likely redundant
                            # - longer beep durations are trimmed before short transients
                            is_collision_slot = (sl in collide_slots)
                            is_duplicate_slot = int(slot_beep_count.get(sl, 0)) > 1
                            # Trim only non-collision beeps, or duplicate beeps.
                            if (not is_collision_slot) or is_duplicate_slot:
                                score = 0
                                if not is_collision_slot:
                                    score += 100
                                if is_duplicate_slot:
                                    score += 50
                                score += min(40, max(0, dur // 20))
                                beep_candidates.append((score, oid, sl))
                    if c > 0:
                        nm = str(objects[oid].get("name", f"obj_{oid}"))
                        by_owner.append((c, oid, nm))
                    est_actions += c
                    binds = p[13] if len(p) > 13 else []
                    total_input_binds += len(binds)
                    for b in binds:
                        try:
                            used_signal_slots.add(int(b.get("slot", 0)))
                        except Exception:
                            pass
                    alarms = p[16] if len(p) > 16 else []
                    for a in alarms:
                        try:
                            sl = int(a.get("slot", -1))
                            if sl > max_alarm_slot_used:
                                max_alarm_slot_used = sl
                            if a.get("type") == "signal":
                                used_signal_slots.add(int(a.get("signal", 0)))
                        except Exception:
                            pass
                    music_ops = p[17] if len(p) > 17 else []
                    for mo in music_ops:
                        try:
                            if str(mo.get("type", "")).strip().lower() == "signal":
                                used_signal_slots.add(int(mo.get("value", 0)))
                        except Exception:
                            pass
                by_owner.sort(reverse=True)
                top = ", ".join([f"{nm}:{c}" for c, _oid, nm in by_owner[:8]])
                self.log(f"Signal actions estimate: {est_actions} (runtime max={signal_action_budget})")
                if top:
                    self.log(f"Top action owners: {top}")
                max_sig_slot = max(used_signal_slots) if used_signal_slots else -1
                rows = [
                    ("objects", len(objects), runtime_limits.get("kMaxObjects", 30), ""),
                    ("owners", len(export_prepared), runtime_limits.get("kMaxObjects", 30), ""),
                    ("signalSlotsUsed", len(used_signal_slots), runtime_limits.get("kMaxSignals", 16), f"maxSlot={max_sig_slot}"),
                    ("colliders", total_colliders, runtime_limits.get("kMaxColliders", 28), ""),
                    ("signalActions", est_actions, runtime_limits.get("kMaxSignalActions", 30), ""),
                    ("inputBinds", total_input_binds, runtime_limits.get("kMaxInputBinds", 14), ""),
                    ("maxAlarmSlotUsed", (max_alarm_slot_used if max_alarm_slot_used >= 0 else 0), runtime_limits.get("kMaxAlarms", 6) - 1, ""),
                ]
                self.log("+------------------+------+-----+--------+----------------+")
                self.log("| Metric           | Used | Max | Status | Note           |")
                self.log("+------------------+------+-----+--------+----------------+")
                for metric, used, limit, note in rows:
                    status = "OK"
                    if limit >= 0 and used > limit:
                        status = "OVER"
                    elif limit > 0 and used >= int(limit * 0.8):
                        status = "WARN"
                    self.log(
                        f"| {str(metric):<16} | {int(used):>4} | {int(limit):>3} | {status:<6} | {str(note)[:14]:<14} |"
                    )
                self.log("+------------------+------+-----+--------+----------------+")
                if est_actions > signal_action_budget:
                    overflow = int(est_actions - signal_action_budget)
                    # Keep core gameplay actions; trim cosmetic beeps first.
                    skip_beep_count = min(int(type_counts.get("beep", 0)), overflow)
                    self.log("WARNING: signal actions exceed runtime max; lower-priority actions will be dropped.")
                    if skip_beep_count > 0:
                        beep_candidates.sort(reverse=True)
                        remaining = int(skip_beep_count)
                        for score, oid, sl in beep_candidates:
                            if remaining <= 0:
                                break
                            key = (int(oid), int(sl))
                            keep_min = int(beep_keep_min_by_key.get(key, 0))
                            total = int(beep_total_by_key.get(key, 0))
                            dropped = int(beep_drop_quota.get(key, 0))
                            if (total - dropped) <= keep_min:
                                continue
                            beep_drop_quota[key] = dropped + 1
                            remaining -= 1
                        if beep_drop_quota:
                            summary = ", ".join([f"obj_{k[0]}:slot{k[1]} -{v}" for k, v in sorted(beep_drop_quota.items())[:8]])
                            self.log(f"Auto-trim beep quota: {summary}")
                        self.log(f"Auto-trim: dropping {skip_beep_count} beep signal action(s) to fit runtime max.")
            except Exception:
                pass

        signal_slot_max = max(0, int(runtime_limits.get("kMaxSignals", 16)) - 1)

        for obj_id, x, y, frame, behavior, anim_frames, anim_fps, texts, shapes, spawns, signals, textboxes, choices, input_binds, bg_scroll_x, bg_scroll_y, alarms, music, hud, vars_info, beeps in export_prepared:
            if persistent_any:
                script += struct.pack("<BB", 86, obj_id)
                if not rooms_enabled:
                    # Always keep objects alive once any persistent behavior is used.
                    script += struct.pack("<BBhhB", 6, obj_id, x, y, frame)
                if behavior.get("enabled"):
                    # OP_SET_VEL (7)
                    vx10 = int(behavior["vx"] * 10.0)
                    vy10 = int(behavior["vy"] * 10.0)
                    script += struct.pack("<BBhh", 7, obj_id, vx10, vy10)
                    if behavior.get("vel_random") is not None:
                        vmin, vmax = behavior.get("vel_random")
                        vmin10 = int(float(vmin) * 10.0)
                        vmax10 = int(float(vmax) * 10.0)
                        if vmin10 > vmax10:
                            vmin10, vmax10 = vmax10, vmin10
                        script += struct.pack("<BBhh", 91, obj_id, vmin10, vmax10)
                    # OP_SET_BOUNDS (8) once
                    if not bounds_written:
                        b = behavior["bounds"]
                        script += struct.pack("<Bhhhh", 8, int(b[0]), int(b[1]), int(b[2]), int(b[3]))
                        bounds_written = True
                    # OP_SET_ROT_SPEED (9)
                    ang10 = int(behavior["rot_speed"] * 10.0)
                    script += struct.pack("<BBh", 9, obj_id, ang10)
                    # OP_SET_SCALE_PULSE (10)
                    base1000 = int(behavior["scale_base"] * 1000.0)
                    amp1000 = int(behavior["scale_amp"] * 1000.0)
                    speed10 = int(behavior["scale_speed"] * 10.0)
                    script += struct.pack("<BBHHH", 10, obj_id, base1000, amp1000, speed10)
                if behavior.get("input_enabled"):
                    speed10 = int(behavior.get("input_speed", 0.0) * 10.0)
                    script += struct.pack("<BBh", 12, obj_id, speed10)
                if behavior.get("start_pos_x") is not None:
                    script += struct.pack("<BBh", 81, obj_id, int(behavior.get("start_pos_x")))
                if behavior.get("start_pos_y") is not None:
                    script += struct.pack("<BBh", 82, obj_id, int(behavior.get("start_pos_y")))
                default_sprite = int(frame)
                if behavior.get("sprite_index") is not None:
                    sprite_idx = int(behavior.get("sprite_index", 0))
                    script += struct.pack("<BBB", 80, obj_id, sprite_idx)
                    default_sprite = sprite_idx
                if behavior.get("rotate_speed") is not None:
                    speed10 = int(float(behavior.get("rotate_speed", 0.0)) * 10.0)
                    script += struct.pack("<BBh", 76, obj_id, speed10)
                if behavior.get("thrust") is not None:
                    thrust100 = int(round(float(behavior.get("thrust", 0.0)) * 100.0))
                    script += struct.pack("<BBh", 77, obj_id, thrust100)
                if behavior.get("wrap") is not None:
                    wx1, wx2, wy1, wy2 = behavior.get("wrap")
                    script += struct.pack("<Bhhhh", 78, int(wx1), int(wx2), int(wy1), int(wy2))
                if behavior.get("no_wrap") is not None:
                    no_wrap = 1 if int(behavior.get("no_wrap", 0)) != 0 else 0
                    script += struct.pack("<BBB", 87, obj_id, no_wrap)
                if behavior.get("bounce") is not None:
                    bounce = 1 if int(behavior.get("bounce", 0)) != 0 else 0
                    script += struct.pack("<BBB", 90, obj_id, bounce)
                if behavior.get("accel") is not None or behavior.get("friction") is not None:
                    accel = float(behavior.get("accel", 0.0))
                    friction = float(behavior.get("friction", 1.0))
                    if friction < 0.0:
                        friction = 0.0
                    if friction > 1.0:
                        friction = 1.0
                    accel10 = int(accel * 10.0)
                    friction1000 = int(friction * 1000.0)
                    script += struct.pack("<BBhh", 75, obj_id, accel10, friction1000)
                anim_override = behavior.get("anim_frames")
                anim_speed = behavior.get("image_speed")
                if anim_override:
                    anim_frames = anim_override
                    if anim_speed is not None:
                        anim_fps = max(1, int(float(anim_speed)))
                if len(anim_frames) > 1:
                    script += struct.pack("<BBB", 11, obj_id, max(1, anim_fps))
                    script += struct.pack("<B", len(anim_frames))
                    script += bytes(anim_frames)
                    if behavior.get("sprite_index") is None:
                        default_sprite = int(anim_frames[0])
                        script += struct.pack("<BBB", 80, obj_id, default_sprite)
                elif behavior.get("sprite_index") is None:
                    # Ensure inactive pool objects still carry their class sprite.
                    # Runtime spawn fallback uses sprite match to find free slots.
                    script += struct.pack("<BBB", 80, obj_id, default_sprite)
                for t in texts:
                    slot = max(0, min(3, int(t.get("slot", 0))))
                    if t.get("clear"):
                        script += struct.pack("<BB", 14, slot)
                        continue
                    tx_raw = t.get("x", None)
                    ty_raw = t.get("y", None)
                    tx = int(x if tx_raw is None else tx_raw)
                    ty = int(y if ty_raw is None else ty_raw)
                    color = max(0, min(15, int(t.get("color", 15))))
                    text = str(t.get("text", ""))[:24]
                    if not text:
                        continue
                    text_bytes = text.encode("utf-8", errors="ignore")
                    if len(text_bytes) > 24:
                        text_bytes = text_bytes[:24]
                    script += struct.pack("<BBhhBB", 13, slot, tx, ty, color, len(text_bytes))
                    script += text_bytes
                for s in shapes:
                    slot = max(0, min(7, int(s.get("slot", 0))))
                    if s.get("clear"):
                        script += struct.pack("<BB", 16, slot)
                        continue
                    stype = int(s.get("type", 0))
                    nums = list(s.get("nums", []))
                    while len(nums) < 6:
                        nums.append(0)
                    x1, y1, x2, y2, x3, y3 = nums[:6]
                    color = max(0, min(15, int(s.get("color", 15))))
                    script += struct.pack("<BBBhhhhhhB", 15, slot, stype, x1, y1, x2, y2, x3, y3, color)
                for op in spawns:
                    if op[0] == "spawn":
                        _, oid, sx, sy, spr = op
                        script += struct.pack("<BBhhB", 17, int(oid), int(sx), int(sy), int(spr))
                    elif op[0] == "destroy":
                        _, oid = op
                        script += struct.pack("<BB", 18, int(oid))
                for box in textboxes:
                    slot = max(0, min(1, int(box.get("slot", 0))))
                    if box.get("clear"):
                        script += struct.pack("<BB", 25, slot)
                        continue
                    tx = int(box.get("x", 0))
                    ty = int(box.get("y", 0))
                    tw = int(box.get("w", 0))
                    th = int(box.get("h", 0))
                    color = max(0, min(15, int(box.get("color", 15))))
                    text = str(box.get("text", ""))[:64]
                    if not text:
                        continue
                    text_bytes = text.encode("utf-8", errors="ignore")
                    if len(text_bytes) > 64:
                        text_bytes = text_bytes[:64]
                    script += struct.pack("<BBhhhhBB", 24, slot, tx, ty, tw, th, color, len(text_bytes))
                    script += text_bytes
                for ch in choices:
                    slot = max(0, min(1, int(ch.get("slot", 0))))
                    if ch.get("clear"):
                        script += struct.pack("<BB", 27, slot)
                        continue
                    cx = int(ch.get("x", 0))
                    cy = int(ch.get("y", 0))
                    color = max(0, min(15, int(ch.get("color", 15))))
                    base_signal = max(0, min(signal_slot_max, int(ch.get("base_signal", 0))))
                    items = list(ch.get("items", []))[:5]
                    script += struct.pack("<BBhhBBB", 26, slot, cx, cy, color, len(items), base_signal)
                    for item in items:
                        text = str(item)[:16]
                        b = text.encode("utf-8", errors="ignore")
                        if len(b) > 16:
                            b = b[:16]
                        script += struct.pack("<B", len(b))
                        script += b
                hitbox = signals.get("hitbox")
                if hitbox:
                    if len(hitbox) >= 4:
                        w, h, off_x, off_y = hitbox[:4]
                        script += struct.pack(
                            "<BBBBbb",
                            98,
                            obj_id,
                            max(1, min(255, int(w))),
                            max(1, min(255, int(h))),
                            max(-128, min(127, int(off_x))),
                            max(-128, min(127, int(off_y))),
                        )
                    else:
                        w, h = hitbox
                        script += struct.pack("<BBBB", 19, obj_id, max(1, min(255, int(w))), max(1, min(255, int(h))))
                colliders_by_slot = {}
                for c in signals.get("colliders", []):
                    slot = max(0, min(signal_slot_max, int(c.get("slot", 0))))
                    colliders_by_slot.setdefault(slot, set()).add(str(c.get("other", "")).strip().lower())
                    for other in _resolve_obj_ids(c.get("other"), obj_id):
                        if 0 <= int(other) < max_runtime_objects:
                            script += struct.pack("<BBBB", 20, slot, obj_id, int(other))
                for act in signals.get("actions", []):
                    slot = max(0, min(signal_slot_max, int(act.get("slot", 0))))
                    if act.get("type") == "destroy":
                        target_tok = str(act.get("target", "self")).strip()
                        target_low = target_tok.lower()
                        slot_colliders = colliders_by_slot.get(slot, set())
                        # If target matches the collider class for this slot, destroy the collision "other".
                        if target_low == "other" or (
                            target_low and target_low != "self" and target_low in slot_colliders
                        ):
                            script += struct.pack("<BBB", 21, slot, 0xFF)
                        else:
                            for target in _resolve_obj_ids(target_tok, obj_id):
                                script += struct.pack("<BBB", 21, slot, int(target))
                    elif act.get("type") == "spawn":
                        target = _resolve_spawn_target(act.get("obj"), obj_id)
                        sx = _encode_spawn_coord(act.get("x", 0), "x")
                        sy = _encode_spawn_coord(act.get("y", 0), "y")
                        frame_tok = act.get("frame", None)
                        frame = None
                        if frame_tok is not None:
                            tok = str(frame_tok).strip().lower()
                            if tok and tok != "auto":
                                try:
                                    frame = int(float(frame_tok))
                                except Exception:
                                    frame = None
                        if frame is None:
                            beh = behavior_by_id.get(target, {})
                            if 0 <= target < len(objects):
                                try:
                                    frame = int(self._obj_preview_frame(objects[target]))
                                except Exception:
                                    frame = None
                            if frame is None and beh.get("sprite_index") is not None:
                                frame = int(beh.get("sprite_index", 0))
                            if frame is None:
                                frame = 0
                        spr = int(frame)
                        script += struct.pack("<BBBhhB", 22, slot, int(target), int(sx), int(sy), int(spr))
                    elif act.get("type") == "sound":
                        try:
                            sid = int(float(act.get("sound", 0)))
                        except Exception:
                            sid = 0
                        script += struct.pack("<BBB", 23, slot, int(sid))
                    elif act.get("type") == "beep":
                        drop_key = (int(obj_id), int(slot))
                        drop_left = int(beep_drop_quota.get(drop_key, 0))
                        if drop_left > 0:
                            beep_drop_quota[drop_key] = drop_left - 1
                            continue
                        hz = masa_note_to_hz(act.get("note", ""))
                        try:
                            ms = int(float(act.get("duration", 0)))
                        except Exception:
                            ms = 0
                        if hz > 0 and ms > 0:
                            ms = max(1, min(65535, ms))
                            wave_tok = str(act.get("wave", "square")).strip().lower()
                            wave = 3 if wave_tok == "noise" else 0
                            script += struct.pack("<BBBHH", 100, slot, int(wave), int(hz), int(ms))
                    elif act.get("type") == "spawn_bullet":
                        target = _resolve_obj_id(act.get("obj"), obj_id)
                        try:
                            speed10 = int(float(act.get("speed", 0.0)) * 10.0)
                        except Exception:
                            speed10 = 0
                        try:
                            offset = int(float(act.get("offset", 0.0)))
                        except Exception:
                            offset = 0
                        frame = None
                        if act.get("frame") is not None:
                            try:
                                frame = int(float(act.get("frame", 0)))
                            except Exception:
                                frame = None
                        if frame is None:
                            beh = behavior_by_id.get(target, {})
                            if 0 <= target < len(objects):
                                try:
                                    frame = int(self._obj_preview_frame(objects[target]))
                                except Exception:
                                    frame = None
                            if frame is None and beh.get("sprite_index") is not None:
                                frame = int(beh.get("sprite_index", 0))
                            if frame is None:
                                frame = 0
                        script += struct.pack("<BBBBhhB", 79, slot, int(obj_id), int(target), int(speed10), int(offset), int(frame))
                    elif act.get("type") == "room_next":
                        script += struct.pack("<BB", 28, slot)
                    elif act.get("type") == "room_goto":
                        try:
                            room = int(float(act.get("room", 0)))
                        except Exception:
                            room = 0
                        script += struct.pack("<BBB", 74, slot, int(room))
                    elif act.get("type") == "stop":
                        for target in _resolve_obj_ids(act.get("target"), obj_id):
                            script += struct.pack("<BBB", 29, slot, int(target))
                    elif act.get("type") == "textbox":
                        box_slot = max(0, min(1, int(act.get("box", 0))))
                        tx = int(act.get("x", 0))
                        ty = int(act.get("y", 0))
                        tw = int(act.get("w", 0))
                        th = int(act.get("h", 0))
                        color = max(0, min(15, int(act.get("color", 15))))
                        text = str(act.get("text", ""))[:64]
                        if text:
                            b = text.encode("utf-8", errors="ignore")
                            if len(b) > 64:
                                b = b[:64]
                            script += struct.pack("<BBBhhhhBB", 30, slot, box_slot, tx, ty, tw, th, color, len(b))
                            script += b
                    elif act.get("type") == "choices":
                        choice_slot = max(0, min(1, int(act.get("choice", 0))))
                        cx = int(act.get("x", 0))
                        cy = int(act.get("y", 0))
                        color = max(0, min(15, int(act.get("color", 15))))
                        base_signal = max(0, min(signal_slot_max, int(act.get("base_signal", 0))))
                        items = list(act.get("items", []))[:5]
                        script += struct.pack("<BBBhhBBB", 31, slot, choice_slot, cx, cy, color, len(items), base_signal)
                        for item in items:
                            text = str(item)[:16]
                            b = text.encode("utf-8", errors="ignore")
                            if len(b) > 16:
                                b = b[:16]
                            script += struct.pack("<B", len(b))
                            script += b
                    elif act.get("type") == "textbox_clear":
                        box_slot = max(0, min(1, int(act.get("box", 0))))
                        script += struct.pack("<BBB", 32, slot, box_slot)
                    elif act.get("type") == "choices_clear":
                        choice_slot = max(0, min(1, int(act.get("choice", 0))))
                        script += struct.pack("<BBB", 33, slot, choice_slot)
                    elif act.get("type") == "set_input":
                        speed10 = int(float(act.get("speed", 0.0)) * 10.0)
                        for target in _resolve_obj_ids(act.get("target"), obj_id):
                            script += struct.pack("<BBBh", 34, slot, int(target), int(speed10))
                    elif act.get("type") == "show_text":
                        text_slot = max(0, min(7, int(act.get("text_slot", 0))))
                        x = int(act.get("x", 0))
                        y = int(act.get("y", 0))
                        color = max(0, min(15, int(act.get("color", 15))))
                        align = max(0, min(2, int(act.get("align", 0))))
                        text = str(act.get("text", ""))[:64]
                        b = text.encode("utf-8", errors="ignore")[:64]
                        if align == 0:
                            script += struct.pack("<BBBhhBB", 94, slot, text_slot, x, y, color, len(b))
                        else:
                            script += struct.pack("<BBBhhBBB", 97, slot, text_slot, x, y, color, align, len(b))
                        script += b
                    elif act.get("type") == "show_text_clear":
                        text_slot = max(0, min(7, int(act.get("text_slot", 0))))
                        script += struct.pack("<BBB", 95, slot, text_slot)
                    elif act.get("type") == "hud_add":
                        life = int(float(act.get("life", 0)))
                        score = int(float(act.get("score", 0)))
                        coins = int(float(act.get("coins", 0)))
                        life = max(-32768, min(32767, life))
                        score = max(-32768, min(32767, score))
                        coins = max(-32768, min(32767, coins))
                        script += struct.pack("<BBhhh", 92, slot, int(life), int(score), int(coins))
                for bind in input_binds:
                    slot = max(0, min(signal_slot_max, int(bind.get("slot", 0))))
                    ev = int(bind.get("ev", 0))
                    btn = int(bind.get("btn", 0))
                    script += struct.pack("<BBBB", 35, slot, ev, btn)
                if bg_scroll_x is not None:
                    script += struct.pack("<Bh", 36, int(bg_scroll_x * 10.0))
                if bg_scroll_y is not None:
                    script += struct.pack("<Bh", 37, int(bg_scroll_y * 10.0))
                if hud.get("set") is not None:
                    life, score, coins = hud.get("set")
                    script += struct.pack("<Blll", 46, int(life), int(score), int(coins))
                for life, score, coins in hud.get("adds", []):
                    script += struct.pack("<Blll", 47, int(life), int(score), int(coins))
                if hud.get("draw") is not None:
                    hx, hy, hc = hud.get("draw")
                    script += struct.pack("<BhhB", 48, int(hx), int(hy), int(hc))
                hud_style = hud.get("style")
                if hud_style is not None:
                    hx = int(hud_style.get("x", 8))
                    hy = int(hud_style.get("y", 8))
                    hc = int(hud_style.get("color", 15)) & 0xFF
                    halign = max(0, min(2, int(hud_style.get("align", 0))))
                    bg_color = int(hud_style.get("bg_color", -1))
                    bg_byte = 0xFF if bg_color < 0 else (bg_color & 0xFF)
                    pad_x = max(0, min(255, int(hud_style.get("pad_x", 2))))
                    pad_y = max(0, min(255, int(hud_style.get("pad_y", 1))))
                    txt_bytes = str(hud_style.get("template", "")).encode("utf-8", errors="ignore")
                    if len(txt_bytes) > 48:
                        txt_bytes = txt_bytes[:48]
                    script += struct.pack("<BhhBBBhhB", 96, hx, hy, hc, halign, bg_byte, pad_x, pad_y, len(txt_bytes))
                    script += txt_bytes
                for target, idx, val in vars_info.get("set", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBl", 49, scope, obj, int(idx) & 0xFF, int(val))
                for target, idx, val in vars_info.get("add", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBl", 50, scope, obj, int(idx) & 0xFF, int(val))
                for slot, tx, ty, col, target, idx, label in vars_info.get("text", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    text_bytes = str(label).encode("utf-8", errors="ignore")
                    if len(text_bytes) > 24:
                        text_bytes = text_bytes[:24]
                    script += struct.pack("<BBhhBBB", 51, int(slot) & 0xFF, int(tx), int(ty), int(col) & 0xFF, scope, obj)
                    script += struct.pack("<BB", int(idx) & 0xFF, len(text_bytes))
                    script += text_bytes
                for target, idx, val in vars_info.get("setf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 52, scope, obj, int(idx) & 0xFF, float(val))
                for target, idx, val in vars_info.get("addf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 53, scope, obj, int(idx) & 0xFF, float(val))
                for slot, tx, ty, col, target, idx, label in vars_info.get("textf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    text_bytes = str(label).encode("utf-8", errors="ignore")
                    if len(text_bytes) > 24:
                        text_bytes = text_bytes[:24]
                    script += struct.pack("<BBhhBBB", 54, int(slot) & 0xFF, int(tx), int(ty), int(col) & 0xFF, scope, obj)
                    script += struct.pack("<BB", int(idx) & 0xFF, len(text_bytes))
                    script += text_bytes
                for op_name, target, idx, val, sig in vars_info.get("ifs", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    op_id = 55 if op_name == "EQ" else 56 if op_name == "GT" else 57
                    script += struct.pack("<BBBBlB", op_id, scope, obj, int(idx) & 0xFF, int(val), int(sig) & 0xFF)
                for op_name, target, idx, val, sig in vars_info.get("ifsf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    op_id = 58 if op_name == "EQF" else 59 if op_name == "GTF" else 60
                    script += struct.pack("<BBBBfB", op_id, scope, obj, int(idx) & 0xFF, float(val), int(sig) & 0xFF)
                for target, idx, minv, maxv in vars_info.get("clamp", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBhh", 61, scope, obj, int(idx) & 0xFF, int(minv), int(maxv))
                for target, idx, minv, maxv in vars_info.get("clampf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 62, scope, obj, int(idx) & 0xFF, float(minv))
                    script += struct.pack("<f", float(maxv))
                for target, idx, minv, maxv in vars_info.get("rand", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBhh", 63, scope, obj, int(idx) & 0xFF, int(minv), int(maxv))
                for target, idx, a, b, t in vars_info.get("lerp", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 64, scope, obj, int(idx) & 0xFF, float(a))
                    script += struct.pack("<f", float(b))
                    script += struct.pack("<f", float(t))
                for target, idx, val in vars_info.get("min", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBl", 65, scope, obj, int(idx) & 0xFF, int(val))
                for target, idx, val in vars_info.get("max", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBl", 66, scope, obj, int(idx) & 0xFF, int(val))
                for target, idx, val in vars_info.get("minf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 67, scope, obj, int(idx) & 0xFF, float(val))
                for target, idx, val in vars_info.get("maxf", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 68, scope, obj, int(idx) & 0xFF, float(val))
                for target, idx, val in vars_info.get("sin", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 69, scope, obj, int(idx) & 0xFF, float(val))
                for target, idx, val in vars_info.get("cos", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBf", 70, scope, obj, int(idx) & 0xFF, float(val))
                for target, idx, text in vars_info.get("str_set", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    text_bytes = str(text).encode("utf-8", errors="ignore")
                    if len(text_bytes) > 24:
                        text_bytes = text_bytes[:24]
                    script += struct.pack("<BBBB", 71, scope, obj, int(idx) & 0xFF)
                    script += struct.pack("<B", len(text_bytes))
                    script += text_bytes
                for slot, tx, ty, col, target, idx, label in vars_info.get("str_text", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    text_bytes = str(label).encode("utf-8", errors="ignore")
                    if len(text_bytes) > 24:
                        text_bytes = text_bytes[:24]
                    script += struct.pack("<BBhhBBB", 72, int(slot) & 0xFF, int(tx), int(ty), int(col) & 0xFF, scope, obj)
                    script += struct.pack("<BB", int(idx) & 0xFF, len(text_bytes))
                    script += text_bytes
                for target, idx, val, sig in vars_info.get("switch", []):
                    scope, obj = self._resolve_var_target(target, obj_id, obj_name_to_id)
                    script += struct.pack("<BBBBlB", 73, scope, obj, int(idx) & 0xFF, int(val), int(sig) & 0xFF)
                for alarm in alarms:
                    if alarm.get("type") == "start":
                        slot = max(0, min(7, int(alarm.get("slot", 0))))
                        ms = max(0, int(alarm.get("ms", 0)))
                        repeat = 1 if int(alarm.get("repeat", 0)) else 0
                        script += struct.pack("<BBBHB", 83, obj_id, slot, ms, repeat)
                    elif alarm.get("type") == "stop":
                        slot = max(0, min(7, int(alarm.get("slot", 0))))
                        script += struct.pack("<BBB", 84, obj_id, slot)
                    elif alarm.get("type") == "signal":
                        slot = max(0, min(7, int(alarm.get("slot", 0))))
                        sig = max(0, min(7, int(alarm.get("signal", 0))))
                        script += struct.pack("<BBBB", 85, obj_id, slot, sig)
                for m in music:
                    if m.get("type") == "signal":
                        slot = max(0, min(7, int(m.get("value", 0))))
                        script += struct.pack("<BB", 41, slot)
                    elif m.get("type") == "play":
                        token = str(m.get("value", "")).strip()
                        song_id = None
                        if token.isdigit():
                            song_id = int(token)
                        elif self.songs_meta and isinstance(self.songs_meta.get("songs", []), list):
                            for idx, s in enumerate(self.songs_meta.get("songs", [])):
                                if str(s.get("name", "")) == token:
                                    song_id = idx
                                    break
                        if song_id is not None:
                            script += struct.pack("<BB", 42, int(song_id))
                    elif m.get("type") == "stop":
                        script += struct.pack("<B", 43)
                    elif m.get("type") == "pause":
                        script += struct.pack("<B", 44)
                    elif m.get("type") == "loop":
                        loop = 1 if int(m.get("value", 0)) else 0
                        script += struct.pack("<BB", 45, loop)
                for bp in beeps:
                    hz = masa_note_to_hz(bp.get("note", ""))
                    ms = max(1, min(65535, int(bp.get("duration", 0))))
                    if hz > 0 and ms > 0:
                        wave = int(bp.get("wave", 0)) & 0xFF
                        script += struct.pack("<BBHH", 99, wave, int(hz), int(ms))
            else:
                angle = float(objects[obj_id].get("angle", 0.0))
                scale = float(objects[obj_id].get("scale", 1.0))
                angle10 = int(angle * 10.0)
                scale1000 = int(scale * 1000.0)
                if abs(angle10) > 0 or abs(scale1000 - 1000) > 0:
                    script += struct.pack("<BhhBhH", 5, x, y, frame, angle10, scale1000)
                else:
                    script += struct.pack("<BhhB", 1, x, y, frame)

        if not persistent_any:
            script += struct.pack("<BH", 4, 16)
        script += struct.pack("<B", 255)

        bg_index = 0
        try:
            active_room = int(self.project.get("active_room", 0))
            rooms = self.project.get("rooms", [])
            if 0 <= active_room < len(rooms):
                bg_index = int(rooms[active_room].get("background_index", 0))
        except Exception:
            bg_index = 0

        room_song = ""
        try:
            active_room = int(self.project.get("active_room", 0))
            rooms = self.project.get("rooms", [])
            if 0 <= active_room < len(rooms):
                room_song = str(rooms[active_room].get("song", "") or "")
        except Exception:
            room_song = ""

        def song_hash_for(name: str) -> int:
            if not name:
                return 0
            h = 0x811C9DC5
            for ch in name:
                h ^= ord(ch) & 0xFF
                h = (h * 0x01000193) & 0xFFFFFFFF
            return h

        song_hash = song_hash_for(room_song)

        def _coerce_bool(v):
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "on")
            return bool(v)

        rooms_data = bytearray()
        if not isinstance(rooms, list):
            rooms = []
        if not silent:
            self.log(f"Export rooms list len={len(rooms)}")
        if rooms:
            obj_persist_by_id = {}
            max_obj_ids = 32
            for i, o in enumerate(objects):
                if i >= max_obj_ids:
                    break
                obj_persist_by_id[i] = _coerce_bool(o.get("persistent", False))

            rooms_data += struct.pack("<H", len(rooms))
            mode_map = {"normal": 0, "rotated": 1, "scaled": 2}
            state_map = {"idle": 0, "walk": 1, "run": 2, "jump": 3}
            for ri, room in enumerate(rooms):
                bg = int(room.get("background_index", 0))
                bg_color = int(room.get("background_color", self.project.get("background_color", 12)))
                room_song = str(room.get("song", "") or "")
                room_hash = song_hash_for(room_song)
                room_objs = room.get("objects", [])
                if not isinstance(room_objs, list):
                    room_objs = []
                if len(room_objs) > 255:
                    room_objs = room_objs[:255]
                encoded_room_objs = []
                for oi, ro in enumerate(room_objs):
                    obj_id = room_instance_id_map.get((ri, oi))
                    if obj_id is None:
                        continue
                    if obj_id < 0 or obj_id >= max_obj_ids:
                        continue
                    encoded_room_objs.append((oi, ro, obj_id))
                tm_idx = int(room.get("tilemap_index", -1))
                tm_byte = tm_idx if 0 <= tm_idx <= 254 else 0xFF
                rooms_data += struct.pack("<BBIBB", bg & 0xFF, bg_color & 0xFF, int(room_hash), tm_byte, len(encoded_room_objs))

                for oi, ro, obj_id in encoded_room_objs:
                    if "frame" in ro:
                        frame = int(ro.get("frame", 0))
                    else:
                        frame = self._obj_preview_frame(ro)
                    mode_key = str(ro.get("mode", ro.get("draw_mode", "normal")))
                    mode = mode_map.get(mode_key, 0)
                    state_key = str(ro.get("start_state", "idle"))
                    state = state_map.get(state_key, 0)
                    angle10 = int(float(ro.get("angle", 0.0)) * 10.0)
                    scale1000 = int(float(ro.get("scale", 1.0)) * 1000.0)
                    persist = int(_coerce_bool(obj_persist_by_id.get(obj_id, False)))
                    rooms_data += struct.pack(
                        "<BhhBBBhHB",
                        obj_id,
                        int(ro.get("x", 0)),
                        int(ro.get("y", 0)),
                        frame & 0xFF,
                        state & 0xFF,
                        mode & 0xFF,
                        angle10,
                        scale1000 & 0xFFFF,
                        persist & 0xFF,
                    )
        self.log(f"rooms_data bytes={len(rooms_data)}")

        header_size = 44
        script_offset = header_size
        script_size = len(script)
        rooms_offset = 0
        rooms_size = 0
        if rooms_data:
            rooms_offset = script_offset + script_size
            rooms_size = len(rooms_data)

        safe_bg_index = int(bg_index) & 0xFFFFFFFF
        safe_song_hash = int(song_hash) & 0xFFFFFFFF
        header = struct.pack(
            "<IHHIIIIIIIII",
            0x4D415341,
            1,
            0,
            script_offset,
            script_size,
            0,
            0,
            rooms_offset,
            rooms_size,
            0,
            safe_bg_index,
            safe_song_hash,
        )

        with open(out, "wb") as f:
            f.write(header)
            f.write(script)
            if rooms_data:
                f.write(rooms_data)

        self.set_status(f"Exported: {out}")
        if not silent:
            messagebox.showinfo("Export", f"Exported MASA program:\n{out}")
        else:
            self.log(f"Exported: {out}")
        return True


def main():
    app = GameEngineGui()
    app.mainloop()


if __name__ == "__main__":
    main()
