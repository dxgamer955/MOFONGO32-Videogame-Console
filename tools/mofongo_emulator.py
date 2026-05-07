#!/usr/bin/env python3
"""Emulador local de MOFONGO32.

Lee proyectos/exportaciones .ingr/.masa y simula el runtime sin flashear el ESP32.
Es la forma rapida de probar scripts, rooms, collisions y assets antes de generar SPIFFS.
"""

import json
import math
import os
import random
import re
import struct
import threading
import time
import zipfile
import tkinter as tk
from tkinter import filedialog
import sys


THEME = {
    "bg": "#384F3E",
    "panel": "#5B8065",
    "accent": "#8CAD92",
    "text": "#FFFFFF",
}

MAGENTA_KEY = (255, 0, 255)


def is_magenta_key(r, g, b):
    if r == 255 and g == 0 and b == 255:
        return True
    # Accept near-magenta to handle palette/PNG conversions.
    return r >= 200 and b >= 200 and g <= 80

ROOM_W = 320
ROOM_H = 200
DEFAULT_SCALE = 2
MAX_OBJECTS = 30
MAX_COLLIDERS = 48
DEBUG_ASTEROIDS = True
DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "asteroids_debug.log")


def init_debug_log():
    if not DEBUG_ASTEROIDS:
        return
    try:
        with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
            f.write(f"[EMU] Debug session started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception:
        pass


def debug_log(msg: str):
    if not DEBUG_ASTEROIDS:
        return
    line = str(msg)
    print(line, flush=True)
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

OP_DRAW_SPRITE = 1
OP_DRAW_SPRITE_XFORM = 5
OP_SET_OBJECT = 6
OP_SET_VEL = 7
OP_SET_BOUNDS = 8
OP_SET_ROT_SPEED = 9
OP_SET_SCALE_PULSE = 10
OP_SET_ANIM = 11
OP_SET_INPUT = 12
OP_TEXT_SET = 13
OP_TEXT_CLEAR = 14
OP_SHAPE_SET = 15
OP_SHAPE_CLEAR = 16
OP_SPAWN_OBJECT = 17
OP_DESTROY_OBJECT = 18
OP_SET_HITBOX = 19
OP_SET_HITBOX_EX = 98
OP_COLLIDE_SIGNAL = 20
OP_SIGNAL_DESTROY = 21
OP_SIGNAL_SPAWN = 22
OP_SIGNAL_SOUND = 23
OP_TEXTBOX_SET = 24
OP_TEXTBOX_CLEAR = 25
OP_CHOICES_SET = 26
OP_CHOICES_CLEAR = 27
OP_SIGNAL_ROOM_NEXT = 28
OP_SIGNAL_STOP = 29
OP_SIGNAL_TEXTBOX = 30
OP_SIGNAL_CHOICES = 31
OP_SIGNAL_TEXTBOX_CLEAR = 32
OP_SIGNAL_CHOICES_CLEAR = 33
OP_SIGNAL_SET_INPUT = 34
OP_INPUT_BIND = 35
OP_BG_SCROLL_X = 36
OP_BG_SCROLL_Y = 37
OP_ALARM_START = 38
OP_ALARM_STOP = 39
OP_ALARM_SIGNAL = 40
OP_ALARM_START_OBJ = 83
OP_ALARM_STOP_OBJ = 84
OP_ALARM_SIGNAL_OBJ = 85
OP_SET_ACTION_OWNER = 86
OP_SET_NO_WRAP = 87
OP_BEEP = 88
OP_SIGNAL_BEEP = 89
OP_BEEP_WAVE = 99
OP_SIGNAL_BEEP_WAVE = 100
OP_SET_BOUNCE = 90
OP_SET_VEL_RANDOM = 91
OP_SIGNAL_HUD_ADD = 92
OP_SET_GAME_OVER_UI = 93
OP_SIGNAL_TEXT_SET = 94
OP_SIGNAL_TEXT_CLEAR = 95
OP_HUD_STYLE = 96
OP_SIGNAL_TEXT_SET_EX = 97
OP_MUSIC_SIGNAL = 41
OP_PLAY_MUSIC = 42
OP_STOP_MUSIC = 43
OP_PAUSE_MUSIC = 44
OP_SONG_LOOP = 45
OP_HUD_SET = 46
OP_HUD_ADD = 47
OP_HUD_DRAW = 48
OP_VAR_SET = 49
OP_VAR_ADD = 50
OP_VAR_TEXT = 51
OP_VARF_SET = 52
OP_VARF_ADD = 53
OP_VARF_TEXT = 54
OP_IF_EQ = 55
OP_IF_GT = 56
OP_IF_LT = 57
OP_IF_EQF = 58
OP_IF_GTF = 59
OP_IF_LTF = 60
OP_VAR_CLAMP = 61
OP_VARF_CLAMP = 62
OP_VAR_RAND = 63
OP_VARF_LERP = 64
OP_VAR_MIN = 65
OP_VAR_MAX = 66
OP_VARF_MIN = 67
OP_VARF_MAX = 68
OP_VARF_SIN = 69
OP_VARF_COS = 70
OP_STR_SET = 71
OP_STR_TEXT = 72
OP_SWITCH = 73
OP_SIGNAL_ROOM_GOTO = 74
OP_SET_ACCEL = 75
OP_SET_ROTATE = 76
OP_SET_THRUST = 77
OP_SET_WRAP = 78
OP_SIGNAL_SPAWN_BULLET = 79
OP_SET_SPRITE = 80
OP_SET_POS_X = 81
OP_SET_POS_Y = 82
OP_MOVE_OBJECT = 2
OP_PLAY_SOUND = 3
OP_WAIT = 4
OP_END = 255

RENDER_DRAW_SPRITE = 1
RENDER_DRAW_SPRITE_XFORM = 2
RENDER_DRAW_TEXT = 4
RENDER_DRAW_SHAPE = 5

INPUT_UP = 1 << 0
INPUT_DOWN = 1 << 1
INPUT_LEFT = 1 << 2
INPUT_RIGHT = 1 << 3
INPUT_A = 1 << 4
INPUT_B = 1 << 5
INPUT_X = 1 << 6
INPUT_Y = 1 << 7
INPUT_START = 1 << 8
INPUT_SELECT = 1 << 9
INPUT_L = 1 << 10
INPUT_R = 1 << 11

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False

try:
    import winsound
    WIN_SOUND_AVAILABLE = True
except Exception:
    winsound = None
    WIN_SOUND_AVAILABLE = False


def sanitize_filename(name: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_.-]", "_", name.strip())
    return out or "file"


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


def read_header(data: bytes):
    if len(data) < 44:
        return None
    vals = struct.unpack("<IHHIIIIIIIII", data[:44])
    return {
        "magic": vals[0],
        "version": vals[1],
        "flags": vals[2],
        "script_offset": vals[3],
        "script_size": vals[4],
        "sprites_offset": vals[5],
        "sprites_size": vals[6],
        "tilemap_offset": vals[7],
        "tilemap_size": vals[8],
        "entry_point": vals[9],
        "reserved": vals[10],
        "song_hash": vals[11],
    }


class Runtime:
    def __init__(self, script: bytes, entry_point: int = 0):
        self.script = script
        self.pc = entry_point
        self.wait_until = 0
        self.running = True
        self.entry_point = entry_point
        self.persistent = False
        self.last_tick = 0
        self.bounds_enabled = False
        self.bounds = (0, 0, 0, 0)
        self.wrap_enabled = False
        self.wrap_bounds = (0, 0, 0, 0)
        self.input_mask = 0
        self.objects = {}
        self.audio_cb = None
        self.rooms = None
        self.rooms_size = 0
        self.room_count = 0
        self.room_index = 0
        self.room_bg = 0
        self.room_bg_color = 12
        self.room_tilemap = -1
        self.room_song_hash = 0
        self.room_persistent_all = set()
        self.room_active_ids = set()
        self.spawned_ids = set()
        self.spawned_ids = set()
        self.text_slots = [{"visible": False, "x": 0, "y": 0, "color": 15, "text": ""} for _ in range(8)]
        self.text_span = [1] * 8
        self.shape_slots = [{"visible": False, "type": 0, "coords": (0, 0, 0, 0, 0, 0), "color": 15} for _ in range(12)]
        self.hitbox = {}
        self.bounce_enabled = {}
        self.vel_random = {}
        self.colliders = []
        self.signal_actions = []
        self.input_binds = []
        self.signals = [False] * 8
        self.signal_prev = [False] * 8
        self.signal_force = [False] * 8
        self.signal_other = [None] * 8
        self.signal_source = [None] * 8
        self.slot_spawn_bullet_seen = [False] * 8
        self.slot_spawn_bullet_fired = [False] * 8
        self.action_owner_cur = None
        self.input_bind_owner = []
        self.choice_owner = [None] * 2
        self.textbox = {}
        self.choices = {}
        self.prev_input_mask = 0
        self.bg_scroll_x = 0
        self.bg_scroll_y = 0
        self.bg_scroll_x10 = 0
        self.bg_scroll_y10 = 0
        self.bg_scroll_acc_x = 0.0
        self.bg_scroll_acc_y = 0.0
        self.alarm_active = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_repeat = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_period = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_next = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_signal = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_default_ms = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_default_repeat = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.music_playing = False
        self.music_loop = False
        self.music_song = 0
        self.music_cmd = None
        self.music_signal = None
        self.music_signal_owner = None
        self.hud_enabled = False
        self.hud_x = 8
        self.hud_y = 8
        self.hud_color = 15
        self.hud_align = 0
        self.hud_bg_color = -1
        self.hud_pad_x = 2
        self.hud_pad_y = 1
        self.hud_template = "L:{LIFE} S:{SCORE} C:{COINS}"
        self.hud_life = 3
        self.hud_score = 0
        self.hud_coins = 0
        self.game_over_armed = False
        self.game_over_prev_mask = 0
        self.game_over_text = "GAME OVER"
        self.game_over_score_prefix = "SCORE:"
        self.game_over_restart_text = "PRESS ANY BUTTON TO RESTART"
        self.var_global = [0] * 64
        self.var_obj = [[0] * 12 for _ in range(32)]
        self.var_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]
        self.varf_global = [0.0] * 64
        self.varf_obj = [[0.0] * 12 for _ in range(32)]
        self.varf_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]
        self.str_global = [""] * 64
        self.str_obj = [[""] * 12 for _ in range(32)]
        self.str_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]

    def reset(self):
        self.pc = self.entry_point
        self.wait_until = 0
        self.running = True
        self.persistent = False
        self.last_tick = 0
        self.bounds_enabled = False
        self.wrap_enabled = False
        self.wrap_bounds = (0, 0, 0, 0)
        self.objects = {}
        self.input_mask = 0
        self.audio_cb = None
        self.room_persistent_all = set()
        self.text_slots = [{"visible": False, "x": 0, "y": 0, "color": 15, "text": ""} for _ in range(8)]
        self.text_span = [1] * 8
        self.shape_slots = [{"visible": False, "type": 0, "coords": (0, 0, 0, 0, 0, 0), "color": 15} for _ in range(12)]
        self.hitbox = {}
        self.bounce_enabled = {}
        self.vel_random = {}
        self.colliders = []
        self.signal_actions = []
        self.input_binds = []
        self.signals = [False] * 8
        self.signal_prev = [False] * 8
        self.signal_force = [False] * 8
        self.signal_other = [None] * 8
        self.signal_source = [None] * 8
        self.slot_spawn_bullet_seen = [False] * 8
        self.slot_spawn_bullet_fired = [False] * 8
        self.action_owner_cur = None
        self.input_bind_owner = []
        self.choice_owner = [None] * 2
        self.textbox = {}
        self.choices = {}
        self.prev_input_mask = 0
        self.bg_scroll_x = 0
        self.bg_scroll_y = 0
        self.bg_scroll_x10 = 0
        self.bg_scroll_y10 = 0
        self.bg_scroll_acc_x = 0.0
        self.bg_scroll_acc_y = 0.0
        self.alarm_active = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_repeat = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_period = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_next = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_signal = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_default_ms = [[0] * 8 for _ in range(MAX_OBJECTS)]
        self.alarm_default_repeat = [[False] * 8 for _ in range(MAX_OBJECTS)]
        self.music_playing = False
        self.music_loop = False
        self.music_song = 0
        self.music_cmd = None
        self.music_signal = None
        self.music_signal_owner = None
        self.hud_enabled = False
        self.hud_x = 8
        self.hud_y = 8
        self.hud_color = 15
        self.hud_align = 0
        self.hud_bg_color = -1
        self.hud_pad_x = 2
        self.hud_pad_y = 1
        self.hud_template = "L:{LIFE} S:{SCORE} C:{COINS}"
        self.hud_life = 3
        self.hud_score = 0
        self.hud_coins = 0
        self.game_over_armed = False
        self.game_over_prev_mask = 0
        self.game_over_text = "GAME OVER"
        self.game_over_score_prefix = "SCORE:"
        self.game_over_restart_text = "PRESS ANY BUTTON TO RESTART"
        self.var_global = [0] * 64
        self.var_obj = [[0] * 12 for _ in range(32)]
        self.var_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]
        self.varf_global = [0.0] * 64
        self.varf_obj = [[0.0] * 12 for _ in range(32)]
        self.varf_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]
        self.str_global = [""] * 64
        self.str_obj = [[""] * 12 for _ in range(32)]
        self.str_text = [{"visible": False, "x": 0, "y": 0, "color": 15, "scope": 0, "obj": 0, "idx": 0, "label": ""} for _ in range(8)]
        if self.room_count > 0:
            self.persistent = True
        if self.rooms and self.room_count > 0:
            self.set_room(0)

    def set_audio_callback(self, cb):
        self.audio_cb = cb

    def _emit_beep(self, hz: int, duration_ms: int):
        if hz <= 0 or duration_ms <= 0:
            return
        if not WIN_SOUND_AVAILABLE:
            return
        hz = max(37, min(32767, int(hz)))
        duration_ms = max(1, min(5000, int(duration_ms)))
        threading.Thread(target=lambda: winsound.Beep(hz, duration_ms), daemon=True).start()

    def _rand_vel10(self, obj_id: int) -> int:
        lo, hi = self.vel_random.get(int(obj_id), (0, 0))
        if lo > hi:
            lo, hi = hi, lo
        v = int(random.randint(int(lo), int(hi)))
        if v == 0 and lo < 0 and hi > 0:
            v = -1 if random.random() < 0.5 else 1
        return v

    def set_input_mask(self, mask: int):
        self.input_mask = int(mask) & 0xFFFF

    def set_rooms(self, data: bytes):
        self.rooms = data
        self.rooms_size = len(data) if data else 0
        self.room_count = 0
        self.room_index = 0
        self.room_bg = 0
        self.room_bg_color = 12
        self.room_tilemap = -1
        self.room_song_hash = 0
        self.room_persistent_all = set()
        self.room_active_ids = set()
        if not data or len(data) < 2:
            return
        self.room_count = int(struct.unpack_from("<H", data, 0)[0])
        self._scan_room_persistent()
        if self.room_count > 0:
            self.persistent = True
        if self.room_count > 0:
            self.set_room(0)

    def _scan_room_persistent(self):
        self.room_persistent_all = set()
        if not self.rooms or self.rooms_size < 2:
            return
        total = int(struct.unpack_from("<H", self.rooms, 0)[0])
        off = 2
        for _ in range(total):
            if off + 8 > self.rooms_size:
                return
            off += 1
            off += 1
            off += 4
            off += 1
            obj_count = self.rooms[off]
            off += 1
            for _ in range(obj_count):
                if off + 13 > self.rooms_size:
                    return
                obj_id = self.rooms[off]
                persistent = self.rooms[off + 12]
                if persistent:
                    self.room_persistent_all.add(obj_id)
                off += 13

    def set_room(self, idx: int) -> bool:
        if not self.rooms or self.rooms_size < 2:
            return False
        total = int(struct.unpack_from("<H", self.rooms, 0)[0])
        if total <= 0:
            return False
        if idx >= total:
            idx = 0

        off = 2
        room_bg = 0
        room_bg_color = 12
        room_song = 0
        room_tilemap = 0xFF
        obj_count = 0
        for r in range(total):
            if off + 8 > self.rooms_size:
                return False
            room_bg = self.rooms[off]
            off += 1
            room_bg_color = self.rooms[off]
            off += 1
            room_song = struct.unpack_from("<I", self.rooms, off)[0]
            off += 4
            room_tilemap = self.rooms[off]
            off += 1
            obj_count = self.rooms[off]
            off += 1
            if r == idx:
                break
            off += obj_count * 13
            if off > self.rooms_size:
                return False

        for obj_id, o in self.objects.items():
            if obj_id not in self.room_persistent_all:
                o["active"] = False
        self.room_active_ids = set()
        self.spawned_ids = set()

        for _ in range(obj_count):
            if off + 13 > self.rooms_size:
                break
            obj_id = self.rooms[off]
            off += 1
            x, y = struct.unpack_from("<hh", self.rooms, off)
            off += 4
            frame = self.rooms[off]
            off += 1
            state = self.rooms[off]
            off += 1
            mode = self.rooms[off]
            off += 1
            angle10 = struct.unpack_from("<h", self.rooms, off)[0]
            off += 2
            scale1000 = struct.unpack_from("<H", self.rooms, off)[0]
            off += 2
            persistent = self.rooms[off]
            off += 1

            self.objects.setdefault(obj_id, {})
            o = self.objects[obj_id]
            o.update({
                "x": float(x),
                "y": float(y),
                "spr": int(frame),
                "is_projectile": False,
                "vx10": o.get("vx10", 0.0),
                "vy10": o.get("vy10", 0.0),
                "angle10": float(angle10 if mode == 1 else 0),
                "angleSpeed10": o.get("angleSpeed10", 0.0),
                "scaleBase1000": float(scale1000 if mode == 2 else 1000.0),
                "scaleAmp1000": o.get("scaleAmp1000", 0.0),
                "scalePhase": o.get("scalePhase", 0.0),
                "scaleSpeedRadPerMs": o.get("scaleSpeedRadPerMs", 0.0),
                "active": True,
            })
            self._start_alarm_defaults(obj_id, self._now_ms())
            self.room_active_ids.add(obj_id)
            _ = persistent
            _ = state

        self.room_index = int(idx)
        self.room_bg = int(room_bg)
        self.room_bg_color = int(room_bg_color)
        self.room_tilemap = int(room_tilemap) if room_tilemap != 0xFF else -1
        self.room_song_hash = int(room_song)
        return True

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _start_alarm_defaults(self, obj_id: int, now_ms: int):
        if obj_id < 0 or obj_id >= MAX_OBJECTS:
            return
        for a in range(8):
            if self.alarm_default_ms[obj_id][a] > 0:
                self.alarm_active[obj_id][a] = True
                self.alarm_repeat[obj_id][a] = bool(self.alarm_default_repeat[obj_id][a])
                self.alarm_period[obj_id][a] = int(self.alarm_default_ms[obj_id][a])
                self.alarm_next[obj_id][a] = int(now_ms) + int(self.alarm_period[obj_id][a])

    def _append_signal_action(self, action: dict):
        if self.action_owner_cur is not None:
            action["owner"] = int(self.action_owner_cur)
        self.signal_actions.append(action)

    def step(self, now_ms: int):
        if not self.running and not self.persistent:
            return []
        if self.running and now_ms < self.wait_until:
            return self._update_behaviors(now_ms)

        cmds = []
        ops = 0
        while self.running and self.pc < len(self.script) and ops < 32:
            ops += 1
            op = self.script[self.pc]
            self.pc += 1
            if op == OP_DRAW_SPRITE:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                spr = self.script[self.pc]
                self.pc += 1
                cmds.append((RENDER_DRAW_SPRITE, x, y, spr, 0, 1000))
            elif op == OP_DRAW_SPRITE_XFORM:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                spr = self.script[self.pc]
                self.pc += 1
                angle10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                scale1000 = struct.unpack_from("<H", self.script, self.pc)[0]
                self.pc += 2
                cmds.append((RENDER_DRAW_SPRITE_XFORM, x, y, spr, angle10, scale1000))
            elif op == OP_SET_OBJECT:
                if self.pc + 6 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                spr = self.script[self.pc]
                self.pc += 1
                self.objects.setdefault(obj_id, {})
                o = self.objects[obj_id]
                o.update({
                    "x": float(x),
                    "y": float(y),
                    "spr": spr,
                    "is_projectile": False,
                    "vx10": 0,
                    "vy10": 0,
                    "accel10": 0,
                    "friction1000": 1000,
                    "turnSpeed10": 0,
                    "thrust10": 0,
                    "angle10": 0.0,
                    "angleSpeed10": 0.0,
                    "scaleBase1000": 1000.0,
                    "scaleAmp1000": 0.0,
                    "scalePhase": 0.0,
                    "scaleSpeedRadPerMs": 0.0,
                    "active": True,
                })
                self._start_alarm_defaults(obj_id, now_ms)
                self.persistent = True
            elif op == OP_SET_VEL:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                vx10, vy10 = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                self.objects.setdefault(obj_id, {"active": False})
                o = self.objects[obj_id]
                o["vx10"] = float(vx10)
                o["vy10"] = float(vy10)
                self.persistent = True
            elif op == OP_SET_BOUNDS:
                if self.pc + 8 > len(self.script):
                    self.running = False
                    break
                b = struct.unpack_from("<hhhh", self.script, self.pc)
                self.pc += 8
                self.bounds = b
                self.bounds_enabled = True
                self.persistent = True
            elif op == OP_SET_ROT_SPEED:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                ang10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["angleSpeed10"] = float(ang10)
                self.persistent = True
            elif op == OP_SET_SCALE_PULSE:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                base1000, amp1000, speed10 = struct.unpack_from("<HHH", self.script, self.pc)
                self.pc += 6
                self.objects.setdefault(obj_id, {"active": False})
                o = self.objects[obj_id]
                o["scaleBase1000"] = float(base1000)
                o["scaleAmp1000"] = float(amp1000)
                speed_deg = (speed10 * 0.1)
                o["scaleSpeedRadPerMs"] = (speed_deg * math.pi / 180.0) / 16.0
                self.persistent = True
            elif op == OP_SET_ANIM:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                fps = self.script[self.pc]
                self.pc += 1
                count = self.script[self.pc]
                self.pc += 1
                if self.pc + count > len(self.script):
                    self.running = False
                    break
                frames = list(self.script[self.pc:self.pc + count])
                self.pc += count
                self.objects.setdefault(obj_id, {"active": False})
                o = self.objects[obj_id]
                o["anim_frames"] = frames
                o["anim_index"] = 0
                o["anim_fps"] = int(fps)
                o["anim_next_ms"] = 0
                self.persistent = True
            elif op == OP_SET_INPUT:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                speed10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                o = self.objects[obj_id]
                o["inputSpeed10"] = float(speed10)
                self.persistent = True
            elif op == OP_SET_ROTATE:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                speed10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["turnSpeed10"] = float(speed10)
                self.persistent = True
            elif op == OP_SET_THRUST:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                thrust10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["thrust10"] = float(thrust10)
                self.persistent = True
            elif op == OP_SET_WRAP:
                if self.pc + 8 > len(self.script):
                    self.running = False
                    break
                self.wrap_bounds = struct.unpack_from("<hhhh", self.script, self.pc)
                self.pc += 8
                self.wrap_enabled = True
                self.bounds_enabled = False
                self.persistent = True
            elif op == OP_SET_NO_WRAP:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                no_wrap = self.script[self.pc]
                self.pc += 1
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["no_wrap"] = (int(no_wrap) != 0)
                self.persistent = True
            elif op == OP_SET_BOUNCE:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                enabled = self.script[self.pc]
                self.pc += 1
                self.objects.setdefault(obj_id, {"active": False})
                self.bounce_enabled[obj_id] = (int(enabled) != 0)
                self.persistent = True
            elif op == OP_SET_VEL_RANDOM:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                vmin10, vmax10 = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                if vmin10 > vmax10:
                    vmin10, vmax10 = vmax10, vmin10
                self.vel_random[obj_id] = (int(vmin10), int(vmax10))
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["vx10"] = float(self._rand_vel10(obj_id))
                self.objects[obj_id]["vy10"] = float(self._rand_vel10(obj_id))
                self.persistent = True
            elif op == OP_SET_SPRITE:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                spr = self.script[self.pc]
                self.pc += 1
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["spr"] = int(spr)
                self.persistent = True
            elif op == OP_SET_POS_X:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                x = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["x"] = float(x)
                self.persistent = True
            elif op == OP_SET_POS_Y:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                y = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.objects.setdefault(obj_id, {"active": False})
                self.objects[obj_id]["y"] = float(y)
                self.persistent = True
            elif op == OP_SET_ACCEL:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                accel10, friction1000 = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                if friction1000 < 0:
                    friction1000 = 0
                if friction1000 > 1000:
                    friction1000 = 1000
                self.objects.setdefault(obj_id, {"active": False})
                o = self.objects[obj_id]
                o["accel10"] = float(accel10)
                o["friction1000"] = float(friction1000)
                self.persistent = True
            elif op == OP_TEXT_SET:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = self.script[self.pc]
                self.pc += 1
                length = self.script[self.pc]
                self.pc += 1
                if self.pc + length > len(self.script):
                    self.running = False
                    break
                text_bytes = self.script[self.pc:self.pc + length]
                self.pc += length
                if slot < len(self.text_slots):
                    try:
                        text = text_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        text = "".join(chr(b) for b in text_bytes)
                    self.text_slots[slot] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "text": text,
                    }
                self.persistent = True
            elif op == OP_TEXT_CLEAR:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot < len(self.text_slots):
                    self.text_slots[slot]["visible"] = False
                self.persistent = True
            elif op == OP_SHAPE_SET:
                if self.pc + 15 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                stype = self.script[self.pc]
                self.pc += 1
                x1, y1, x2, y2, x3, y3 = struct.unpack_from("<hhhhhh", self.script, self.pc)
                self.pc += 12
                color = self.script[self.pc]
                self.pc += 1
                if slot < len(self.shape_slots):
                    self.shape_slots[slot] = {
                        "visible": True,
                        "type": int(stype),
                        "coords": (int(x1), int(y1), int(x2), int(y2), int(x3), int(y3)),
                        "color": int(color),
                    }
                self.persistent = True
            elif op == OP_SHAPE_CLEAR:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot < len(self.shape_slots):
                    self.shape_slots[slot]["visible"] = False
                self.persistent = True
            elif op == OP_SPAWN_OBJECT:
                if self.pc + 6 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                spr = self.script[self.pc]
                self.pc += 1
                self.objects.setdefault(obj_id, {})
                o = self.objects[obj_id]
                o.update({
                    "x": float(x),
                    "y": float(y),
                    "spr": int(spr),
                    "active": True,
                    "is_projectile": False,
                })
                self.spawned_ids.add(int(obj_id))
                self.persistent = True
            elif op == OP_DESTROY_OBJECT:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                if obj_id in self.objects:
                    self.objects[obj_id]["active"] = False
                    self.objects[obj_id]["is_projectile"] = False
                if obj_id in self.spawned_ids:
                    self.spawned_ids.remove(int(obj_id))
                self.persistent = True
            elif op == OP_SET_HITBOX:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                w = self.script[self.pc]
                self.pc += 1
                h = self.script[self.pc]
                self.pc += 1
                self.hitbox[int(obj_id)] = (max(1, int(w)), max(1, int(h)), 0, 0)
                self.persistent = True
            elif op == OP_SET_HITBOX_EX:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                w = self.script[self.pc]
                self.pc += 1
                h = self.script[self.pc]
                self.pc += 1
                off_x = struct.unpack_from("<b", self.script, self.pc)[0]
                self.pc += 1
                off_y = struct.unpack_from("<b", self.script, self.pc)[0]
                self.pc += 1
                self.hitbox[int(obj_id)] = (max(1, int(w)), max(1, int(h)), int(off_x), int(off_y))
                self.persistent = True
            elif op == OP_COLLIDE_SIGNAL:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                obj_a = self.script[self.pc]
                self.pc += 1
                obj_b = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    if len(self.colliders) < MAX_COLLIDERS:
                        self.colliders.append((int(slot), int(obj_a), int(obj_b)))
                self.persistent = True
            elif op == OP_SIGNAL_DESTROY:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                obj_id = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    if int(obj_id) == 0xFF:
                        self._append_signal_action({"slot": int(slot), "type": "destroy_other"})
                    else:
                        self._append_signal_action({"slot": int(slot), "type": "destroy", "obj": int(obj_id)})
                self.persistent = True
            elif op == OP_SIGNAL_SPAWN:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                obj_id = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                spr = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot),
                        "type": "spawn",
                        "obj": int(obj_id),
                        "x": int(x),
                        "y": int(y),
                        "spr": int(spr),
                    })
                self.persistent = True
            elif op == OP_SIGNAL_SOUND:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                sid = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "sound", "sound": int(sid)})
                self.persistent = True
            elif op == OP_SIGNAL_BEEP:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                hz, ms = struct.unpack_from("<HH", self.script, self.pc)
                self.pc += 4
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "beep", "hz": int(hz), "ms": int(ms), "wave": 0})
                self.persistent = True
            elif op == OP_SIGNAL_BEEP_WAVE:
                if self.pc + 6 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                wave = self.script[self.pc]
                self.pc += 1
                hz, ms = struct.unpack_from("<HH", self.script, self.pc)
                self.pc += 4
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "beep", "hz": int(hz), "ms": int(ms), "wave": int(wave)})
                self.persistent = True
            elif op == OP_TEXTBOX_SET:
                if self.pc + 11 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                x, y, w, h = struct.unpack_from("<hhhh", self.script, self.pc)
                self.pc += 8
                color = self.script[self.pc]
                self.pc += 1
                length = self.script[self.pc]
                self.pc += 1
                if self.pc + length > len(self.script):
                    self.running = False
                    break
                text_bytes = self.script[self.pc:self.pc + length]
                self.pc += length
                if slot < 2:
                    try:
                        text = text_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        text = "".join(chr(b) for b in text_bytes)
                    self.textbox[int(slot)] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "w": int(w),
                        "h": int(h),
                        "color": int(color),
                        "text": text,
                    }
                self.persistent = True
            elif op == OP_TEXTBOX_CLEAR:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot in self.textbox:
                    self.textbox[slot]["visible"] = False
                self.persistent = True
            elif op == OP_CHOICES_SET:
                if self.pc + 8 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = self.script[self.pc]
                self.pc += 1
                count = self.script[self.pc]
                self.pc += 1
                base_signal = self.script[self.pc]
                self.pc += 1
                items = []
                for _ in range(count):
                    if self.pc + 1 > len(self.script):
                        self.running = False
                        break
                    ln = self.script[self.pc]
                    self.pc += 1
                    if self.pc + ln > len(self.script):
                        self.running = False
                        break
                    text_bytes = self.script[self.pc:self.pc + ln]
                    self.pc += ln
                    try:
                        txt = text_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        txt = "".join(chr(b) for b in text_bytes)
                    items.append(txt)
                if slot < 2:
                    self.choices[int(slot)] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "items": items[:5],
                        "sel": 0,
                        "base": int(base_signal),
                        "prev_up": False,
                        "prev_down": False,
                        "prev_ok": False,
                    }
                    self.choice_owner[int(slot)] = self.action_owner_cur
                self.persistent = True
            elif op == OP_CHOICES_CLEAR:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot in self.choices:
                    self.choices[slot]["visible"] = False
                self.persistent = True
            elif op == OP_SIGNAL_ROOM_NEXT:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "room_next"})
                self.persistent = True
            elif op == OP_SIGNAL_ROOM_GOTO:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                room = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "room_goto", "room": int(room)})
                self.persistent = True
            elif op == OP_SIGNAL_SPAWN_BULLET:
                if self.pc + 8 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                src_obj = self.script[self.pc]
                self.pc += 1
                bullet_obj = self.script[self.pc]
                self.pc += 1
                speed10, offset = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                frame = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot),
                        "type": "spawn_bullet",
                        "src": int(src_obj),
                        "bullet": int(bullet_obj),
                        "speed10": float(speed10),
                        "offset": float(offset),
                        "frame": int(frame),
                    })
                self.persistent = True
            elif op == OP_SIGNAL_STOP:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                obj_id = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "stop", "obj": int(obj_id)})
                self.persistent = True
            elif op == OP_SIGNAL_TEXTBOX:
                if self.pc + 12 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                box_slot = self.script[self.pc]
                self.pc += 1
                x, y, w, h = struct.unpack_from("<hhhh", self.script, self.pc)
                self.pc += 8
                color = self.script[self.pc]
                self.pc += 1
                length = self.script[self.pc]
                self.pc += 1
                if self.pc + length > len(self.script):
                    self.running = False
                    break
                text_bytes = self.script[self.pc:self.pc + length]
                self.pc += length
                if slot < 8:
                    try:
                        text = text_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        text = "".join(chr(b) for b in text_bytes)
                    self._append_signal_action({
                        "slot": int(slot),
                        "type": "textbox",
                        "box": int(box_slot),
                        "x": int(x),
                        "y": int(y),
                        "w": int(w),
                        "h": int(h),
                        "color": int(color),
                        "text": text,
                    })
                self.persistent = True
            elif op == OP_SIGNAL_CHOICES:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                choice_slot = self.script[self.pc]
                self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = self.script[self.pc]
                self.pc += 1
                count = self.script[self.pc]
                self.pc += 1
                base_signal = self.script[self.pc]
                self.pc += 1
                items = []
                for _ in range(count):
                    if self.pc + 1 > len(self.script):
                        self.running = False
                        break
                    ln = self.script[self.pc]
                    self.pc += 1
                    if self.pc + ln > len(self.script):
                        self.running = False
                        break
                    text_bytes = self.script[self.pc:self.pc + ln]
                    self.pc += ln
                    try:
                        txt = text_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        txt = "".join(chr(b) for b in text_bytes)
                    items.append(txt)
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot),
                        "type": "choices",
                        "choice": int(choice_slot),
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "items": items[:5],
                        "base": int(base_signal),
                    })
                self.persistent = True
            elif op == OP_SIGNAL_TEXTBOX_CLEAR:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                box_slot = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "textbox_clear", "box": int(box_slot)})
                self.persistent = True
            elif op == OP_SIGNAL_CHOICES_CLEAR:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                choice_slot = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "choices_clear", "choice": int(choice_slot)})
                self.persistent = True
            elif op == OP_SIGNAL_SET_INPUT:
                if self.pc + 4 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                obj_id = self.script[self.pc]
                self.pc += 1
                speed10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "set_input", "obj": int(obj_id), "speed10": int(speed10)})
                self.persistent = True
            elif op == OP_SIGNAL_HUD_ADD:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                life, score, coins = struct.unpack_from("<hhh", self.script, self.pc)
                self.pc += 6
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot),
                        "type": "hud_add",
                        "life": int(life),
                        "score": int(score),
                        "coins": int(coins),
                    })
                self.persistent = True
            elif op == OP_SET_GAME_OVER_UI:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                l1 = int(self.script[self.pc]); self.pc += 1
                l2 = int(self.script[self.pc]); self.pc += 1
                l3 = int(self.script[self.pc]); self.pc += 1
                if self.pc + l1 + l2 + l3 > len(self.script):
                    self.running = False
                    break
                b1 = self.script[self.pc:self.pc + l1]; self.pc += l1
                b2 = self.script[self.pc:self.pc + l2]; self.pc += l2
                b3 = self.script[self.pc:self.pc + l3]; self.pc += l3
                self.game_over_text = b1.decode("utf-8", errors="ignore") if l1 > 0 else self.game_over_text
                self.game_over_score_prefix = b2.decode("utf-8", errors="ignore") if l2 > 0 else self.game_over_score_prefix
                self.game_over_restart_text = b3.decode("utf-8", errors="ignore") if l3 > 0 else self.game_over_restart_text
                self.persistent = True
            elif op == OP_SIGNAL_TEXT_SET:
                if self.pc + 8 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]; self.pc += 1
                text_slot = self.script[self.pc]; self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc); self.pc += 4
                color = self.script[self.pc]; self.pc += 1
                ln = self.script[self.pc]; self.pc += 1
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                b = self.script[self.pc:self.pc + ln]; self.pc += ln
                text = b.decode("utf-8", errors="ignore")
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot), "type": "show_text", "text_slot": int(text_slot),
                        "x": int(x), "y": int(y), "color": int(color), "align": 0, "text": text
                    })
                self.persistent = True
            elif op == OP_SIGNAL_TEXT_SET_EX:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]; self.pc += 1
                text_slot = self.script[self.pc]; self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc); self.pc += 4
                color = self.script[self.pc]; self.pc += 1
                align = self.script[self.pc]; self.pc += 1
                ln = self.script[self.pc]; self.pc += 1
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                b = self.script[self.pc:self.pc + ln]; self.pc += ln
                text = b.decode("utf-8", errors="ignore")
                if slot < 8:
                    self._append_signal_action({
                        "slot": int(slot), "type": "show_text", "text_slot": int(text_slot),
                        "x": int(x), "y": int(y), "color": int(color), "align": max(0, min(2, int(align))), "text": text
                    })
                self.persistent = True
            elif op == OP_SIGNAL_TEXT_CLEAR:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]; self.pc += 1
                text_slot = self.script[self.pc]; self.pc += 1
                if slot < 8:
                    self._append_signal_action({"slot": int(slot), "type": "show_text_clear", "text_slot": int(text_slot)})
                self.persistent = True
            elif op == OP_INPUT_BIND:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                ev = self.script[self.pc]
                self.pc += 1
                btn = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self.input_binds.append((int(slot), int(ev), int(btn), self.action_owner_cur))
                self.persistent = True
            elif op == OP_SET_ACTION_OWNER:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                self.action_owner_cur = int(obj_id) if obj_id < MAX_OBJECTS else None
                self.persistent = True
            elif op == OP_BG_SCROLL_X:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                self.bg_scroll_x10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.persistent = True
            elif op == OP_BG_SCROLL_Y:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                self.bg_scroll_y10 = struct.unpack_from("<h", self.script, self.pc)[0]
                self.pc += 2
                self.persistent = True
            elif op == OP_ALARM_START:
                if self.pc + 4 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                ms = struct.unpack_from("<H", self.script, self.pc)[0]
                self.pc += 2
                repeat = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self.alarm_active[0][slot] = True
                    self.alarm_repeat[0][slot] = bool(repeat)
                    self.alarm_period[0][slot] = int(ms)
                    self.alarm_next[0][slot] = now_ms + int(ms)
                self.persistent = True
            elif op == OP_ALARM_STOP:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self.alarm_active[0][slot] = False
                self.persistent = True
            elif op == OP_ALARM_SIGNAL:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                alarm = self.script[self.pc]
                self.pc += 1
                signal = self.script[self.pc]
                self.pc += 1
                if alarm < 8:
                    self.alarm_signal[0][alarm] = int(signal)
                self.persistent = True
            elif op == OP_ALARM_START_OBJ:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                slot = self.script[self.pc]
                self.pc += 1
                ms = struct.unpack_from("<H", self.script, self.pc)[0]
                self.pc += 2
                repeat = self.script[self.pc]
                self.pc += 1
                if obj_id < MAX_OBJECTS and slot < 8:
                    self.alarm_default_ms[obj_id][slot] = int(ms)
                    self.alarm_default_repeat[obj_id][slot] = bool(repeat)
                    if self.objects.get(obj_id, {}).get("active", False):
                        self.alarm_active[obj_id][slot] = True
                        self.alarm_repeat[obj_id][slot] = bool(repeat)
                        self.alarm_period[obj_id][slot] = int(ms)
                        self.alarm_next[obj_id][slot] = now_ms + int(ms)
                self.persistent = True
            elif op == OP_ALARM_STOP_OBJ:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                slot = self.script[self.pc]
                self.pc += 1
                if obj_id < MAX_OBJECTS and slot < 8:
                    self.alarm_active[obj_id][slot] = False
                    self.alarm_default_ms[obj_id][slot] = 0
                    self.alarm_default_repeat[obj_id][slot] = False
                self.persistent = True
            elif op == OP_ALARM_SIGNAL_OBJ:
                if self.pc + 3 > len(self.script):
                    self.running = False
                    break
                obj_id = self.script[self.pc]
                self.pc += 1
                alarm = self.script[self.pc]
                self.pc += 1
                signal = self.script[self.pc]
                self.pc += 1
                if obj_id < MAX_OBJECTS and alarm < 8:
                    self.alarm_signal[obj_id][alarm] = int(signal)
                self.persistent = True
            elif op == OP_MUSIC_SIGNAL:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                slot = self.script[self.pc]
                self.pc += 1
                if slot < 8:
                    self.music_signal = int(slot)
                    self.music_signal_owner = self.action_owner_cur
                self.persistent = True
            elif op == OP_PLAY_MUSIC:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                song = self.script[self.pc]
                self.pc += 1
                self.music_song = int(song)
                self.music_playing = True
                self.music_cmd = ("play", self.music_song, self.music_loop)
                self.persistent = True
            elif op == OP_STOP_MUSIC:
                self.music_playing = False
                self.music_cmd = ("stop", self.music_song, self.music_loop)
                self.persistent = True
            elif op == OP_PAUSE_MUSIC:
                self.music_playing = False
                self.music_cmd = ("pause", self.music_song, self.music_loop)
                self.persistent = True
            elif op == OP_SONG_LOOP:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                loop = self.script[self.pc]
                self.pc += 1
                self.music_loop = bool(loop)
                self.music_cmd = ("loop", self.music_song, self.music_loop)
                self.persistent = True
            elif op == OP_HUD_SET:
                if self.pc + 12 > len(self.script):
                    self.running = False
                    break
                self.hud_life, self.hud_score, self.hud_coins = struct.unpack_from("<lll", self.script, self.pc)
                self.pc += 12
                self.persistent = True
            elif op == OP_HUD_ADD:
                if self.pc + 12 > len(self.script):
                    self.running = False
                    break
                dl, ds, dc = struct.unpack_from("<lll", self.script, self.pc)
                self.pc += 12
                self.hud_life += dl
                self.hud_score += ds
                self.hud_coins += dc
                self.persistent = True
            elif op == OP_HUD_DRAW:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                self.hud_x, self.hud_y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                self.hud_color = int(self.script[self.pc])
                self.pc += 1
                self.hud_enabled = True
                self.persistent = True
            elif op == OP_HUD_STYLE:
                if self.pc + 12 > len(self.script):
                    self.running = False
                    break
                self.hud_x, self.hud_y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                self.hud_color = int(self.script[self.pc]); self.pc += 1
                self.hud_align = int(self.script[self.pc]); self.pc += 1
                bg = int(self.script[self.pc]); self.pc += 1
                self.hud_bg_color = -1 if bg == 0xFF else bg
                self.hud_pad_x, self.hud_pad_y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                ln = int(self.script[self.pc]); self.pc += 1
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                b = self.script[self.pc:self.pc + ln]
                self.pc += ln
                try:
                    self.hud_template = b.decode("utf-8", errors="ignore")
                except Exception:
                    self.hud_template = "L:{LIFE} S:{SCORE} C:{COINS}"
                if self.hud_align not in (0, 1, 2):
                    self.hud_align = 0
                self.hud_pad_x = max(0, int(self.hud_pad_x))
                self.hud_pad_y = max(0, int(self.hud_pad_y))
                self.hud_enabled = True
                self.persistent = True
            elif op == OP_VAR_SET:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<l", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        self.var_global[idx] = val
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        self.var_obj[obj][idx] = val
                self.persistent = True
            elif op == OP_VAR_ADD:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<l", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        self.var_global[idx] += val
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        self.var_obj[obj][idx] += val
                self.persistent = True
            elif op == OP_VAR_TEXT:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                slot = int(self.script[self.pc]); self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = int(self.script[self.pc]); self.pc += 1
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                ln = int(self.script[self.pc]); self.pc += 1
                label = ""
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                if ln > 0:
                    raw = self.script[self.pc:self.pc + ln]
                    try:
                        label = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        label = "".join(chr(b) for b in raw)
                    self.pc += ln
                if 0 <= slot < len(self.var_text):
                    self.var_text[slot] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "scope": int(scope),
                        "obj": int(obj),
                        "idx": int(idx),
                        "label": label,
                    }
                self.persistent = True
            elif op == OP_VARF_SET:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<f", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] = val
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] = val
                self.persistent = True
            elif op == OP_VARF_ADD:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<f", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] += val
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] += val
                self.persistent = True
            elif op == OP_VARF_TEXT:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                slot = int(self.script[self.pc]); self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = int(self.script[self.pc]); self.pc += 1
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                ln = int(self.script[self.pc]); self.pc += 1
                label = ""
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                if ln > 0:
                    raw = self.script[self.pc:self.pc + ln]
                    try:
                        label = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        label = "".join(chr(b) for b in raw)
                    self.pc += ln
                if 0 <= slot < len(self.varf_text):
                    self.varf_text[slot] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "scope": int(scope),
                        "obj": int(obj),
                        "idx": int(idx),
                        "label": label,
                    }
                self.persistent = True
            elif op in (OP_IF_EQ, OP_IF_GT, OP_IF_LT):
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<l", self.script, self.pc)[0]
                self.pc += 4
                sig = int(self.script[self.pc]); self.pc += 1
                cur = 0
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        cur = self.var_global[idx]
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        cur = self.var_obj[obj][idx]
                pass_cond = (cur == val) if op == OP_IF_EQ else (cur > val) if op == OP_IF_GT else (cur < val)
                if 0 <= sig < len(self.signals):
                    self.signals[sig] = pass_cond
                self.persistent = True
            elif op in (OP_IF_EQF, OP_IF_GTF, OP_IF_LTF):
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<f", self.script, self.pc)[0]
                self.pc += 4
                sig = int(self.script[self.pc]); self.pc += 1
                cur = 0.0
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        cur = self.varf_global[idx]
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        cur = self.varf_obj[obj][idx]
                if op == OP_IF_EQF:
                    pass_cond = abs(cur - val) < 0.0001
                elif op == OP_IF_GTF:
                    pass_cond = cur > val
                else:
                    pass_cond = cur < val
                if 0 <= sig < len(self.signals):
                    self.signals[sig] = pass_cond
                self.persistent = True
            elif op in (OP_VAR_MIN, OP_VAR_MAX):
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<l", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        self.var_global[idx] = min(self.var_global[idx], val) if op == OP_VAR_MIN else max(self.var_global[idx], val)
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        self.var_obj[obj][idx] = min(self.var_obj[obj][idx], val) if op == OP_VAR_MIN else max(self.var_obj[obj][idx], val)
                self.persistent = True
            elif op in (OP_VARF_MIN, OP_VARF_MAX):
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<f", self.script, self.pc)[0]
                self.pc += 4
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] = min(self.varf_global[idx], val) if op == OP_VARF_MIN else max(self.varf_global[idx], val)
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] = min(self.varf_obj[obj][idx], val) if op == OP_VARF_MIN else max(self.varf_obj[obj][idx], val)
                self.persistent = True
            elif op in (OP_VARF_SIN, OP_VARF_COS):
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<f", self.script, self.pc)[0]
                self.pc += 4
                rad = val * 0.0174532925
                out = math.sin(rad) if op == OP_VARF_SIN else math.cos(rad)
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] = out
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] = out
                self.persistent = True
            elif op == OP_STR_SET:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                ln = int(self.script[self.pc]); self.pc += 1
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                label = ""
                if ln > 0:
                    raw = self.script[self.pc:self.pc + ln]
                    try:
                        label = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        label = "".join(chr(b) for b in raw)
                    self.pc += ln
                if scope == 0:
                    if 0 <= idx < len(self.str_global):
                        self.str_global[idx] = label
                else:
                    if 0 <= obj < len(self.str_obj) and 0 <= idx < len(self.str_obj[obj]):
                        self.str_obj[obj][idx] = label
                self.persistent = True
            elif op == OP_STR_TEXT:
                if self.pc + 9 > len(self.script):
                    self.running = False
                    break
                slot = int(self.script[self.pc]); self.pc += 1
                x, y = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                color = int(self.script[self.pc]); self.pc += 1
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                ln = int(self.script[self.pc]); self.pc += 1
                label = ""
                if self.pc + ln > len(self.script):
                    self.running = False
                    break
                if ln > 0:
                    raw = self.script[self.pc:self.pc + ln]
                    try:
                        label = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        label = "".join(chr(b) for b in raw)
                    self.pc += ln
                if 0 <= slot < len(self.str_text):
                    self.str_text[slot] = {
                        "visible": True,
                        "x": int(x),
                        "y": int(y),
                        "color": int(color),
                        "scope": int(scope),
                        "obj": int(obj),
                        "idx": int(idx),
                        "label": label,
                    }
                self.persistent = True
            elif op == OP_SWITCH:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                val = struct.unpack_from("<l", self.script, self.pc)[0]
                self.pc += 4
                sig = int(self.script[self.pc]); self.pc += 1
                cur = 0
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        cur = self.var_global[idx]
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        cur = self.var_obj[obj][idx]
                if 0 <= sig < len(self.signals):
                    self.signals[sig] = (cur == val)
                self.persistent = True
            elif op == OP_VAR_CLAMP:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                minv, maxv = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                if minv > maxv:
                    minv, maxv = maxv, minv
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        self.var_global[idx] = max(min(self.var_global[idx], maxv), minv)
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        self.var_obj[obj][idx] = max(min(self.var_obj[obj][idx], maxv), minv)
                self.persistent = True
            elif op == OP_VARF_CLAMP:
                if self.pc + 11 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                minv = struct.unpack_from("<f", self.script, self.pc)[0]; self.pc += 4
                maxv = struct.unpack_from("<f", self.script, self.pc)[0]; self.pc += 4
                if minv > maxv:
                    minv, maxv = maxv, minv
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] = max(min(self.varf_global[idx], maxv), minv)
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] = max(min(self.varf_obj[obj][idx], maxv), minv)
                self.persistent = True
            elif op == OP_VAR_RAND:
                if self.pc + 7 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                minv, maxv = struct.unpack_from("<hh", self.script, self.pc)
                self.pc += 4
                if minv > maxv:
                    minv, maxv = maxv, minv
                val = random.randint(int(minv), int(maxv)) if maxv >= minv else int(minv)
                if scope == 0:
                    if 0 <= idx < len(self.var_global):
                        self.var_global[idx] = val
                else:
                    if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                        self.var_obj[obj][idx] = val
                self.persistent = True
            elif op == OP_VARF_LERP:
                if self.pc + 15 > len(self.script):
                    self.running = False
                    break
                scope = int(self.script[self.pc]); self.pc += 1
                obj = int(self.script[self.pc]); self.pc += 1
                idx = int(self.script[self.pc]); self.pc += 1
                a = struct.unpack_from("<f", self.script, self.pc)[0]; self.pc += 4
                b = struct.unpack_from("<f", self.script, self.pc)[0]; self.pc += 4
                t = struct.unpack_from("<f", self.script, self.pc)[0]; self.pc += 4
                if t < 0.0: t = 0.0
                if t > 1.0: t = 1.0
                val = a + (b - a) * t
                if scope == 0:
                    if 0 <= idx < len(self.varf_global):
                        self.varf_global[idx] = val
                else:
                    if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                        self.varf_obj[obj][idx] = val
                self.persistent = True
            elif op == OP_MOVE_OBJECT:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                self.pc += 5
            elif op == OP_PLAY_SOUND:
                if self.pc + 1 > len(self.script):
                    self.running = False
                    break
                sid = self.script[self.pc]
                self.pc += 1
                if self.audio_cb:
                    try:
                        self.audio_cb(int(sid))
                    except Exception:
                        pass
            elif op == OP_BEEP:
                if self.pc + 4 > len(self.script):
                    self.running = False
                    break
                hz, ms = struct.unpack_from("<HH", self.script, self.pc)
                self.pc += 4
                self._emit_beep(int(hz), int(ms))
            elif op == OP_BEEP_WAVE:
                if self.pc + 5 > len(self.script):
                    self.running = False
                    break
                wave = self.script[self.pc]
                self.pc += 1
                hz, ms = struct.unpack_from("<HH", self.script, self.pc)
                self.pc += 4
                self._emit_beep(int(hz), int(ms))
            elif op == OP_WAIT:
                if self.pc + 2 > len(self.script):
                    self.running = False
                    break
                wait_ms = struct.unpack_from("<H", self.script, self.pc)[0]
                self.pc += 2
                self.wait_until = now_ms + wait_ms
                break
            elif op == OP_END:
                self.running = False
                break
            else:
                self.running = False
                break
        if self.persistent:
            cmds.extend(self._update_behaviors(now_ms))
        return cmds

    def _update_behaviors(self, now_ms: int):
        if not self.persistent:
            return []
        if self.last_tick == 0:
            self.last_tick = now_ms
        dt = max(1, now_ms - self.last_tick)
        self.last_tick = now_ms
        t = dt / 16.0
        cmds = []
        for obj_id, o in self.objects.items():
            if not o.get("active", False):
                continue
            if self.room_count > 0 and obj_id not in self.room_active_ids and obj_id not in self.room_persistent_all and obj_id not in self.spawned_ids:
                continue
            input_speed = o.get("inputSpeed10", 0.0)
            if input_speed != 0.0:
                move = (input_speed * t * 0.1)
                if self.input_mask & INPUT_LEFT:
                    o["x"] = o.get("x", 0.0) - move
                if self.input_mask & INPUT_RIGHT:
                    o["x"] = o.get("x", 0.0) + move
                if self.input_mask & INPUT_UP:
                    o["y"] = o.get("y", 0.0) - move
                if self.input_mask & INPUT_DOWN:
                    o["y"] = o.get("y", 0.0) + move
            turn_speed = o.get("turnSpeed10", 0.0)
            if turn_speed != 0.0:
                turn = turn_speed * t
                if self.input_mask & INPUT_LEFT:
                    o["angle10"] = o.get("angle10", 0.0) - turn
                if self.input_mask & INPUT_RIGHT:
                    o["angle10"] = o.get("angle10", 0.0) + turn
            thrust10 = o.get("thrust10", 0.0)
            if thrust10 != 0.0 and (self.input_mask & INPUT_UP):
                deg = (o.get("angle10", 0.0) * 0.1)
                rad = deg * math.pi / 180.0
                # OP_SET_THRUST stores value in hundredths to allow finer decimals.
                accel = thrust10 * 0.1 * t
                o["vx10"] = o.get("vx10", 0.0) + math.cos(rad) * accel
                o["vy10"] = o.get("vy10", 0.0) + math.sin(rad) * accel
            accel10 = o.get("accel10", 0.0)
            if accel10 != 0.0:
                accel = accel10 * t
                if self.input_mask & INPUT_LEFT:
                    o["vx10"] = o.get("vx10", 0.0) - accel
                if self.input_mask & INPUT_RIGHT:
                    o["vx10"] = o.get("vx10", 0.0) + accel
                if self.input_mask & INPUT_UP:
                    o["vy10"] = o.get("vy10", 0.0) - accel
                if self.input_mask & INPUT_DOWN:
                    o["vy10"] = o.get("vy10", 0.0) + accel
            friction1000 = o.get("friction1000", 1000.0)
            if friction1000 != 1000.0:
                f = max(0.0, min(1000.0, friction1000)) * 0.001
                o["vx10"] = o.get("vx10", 0.0) * f
                o["vy10"] = o.get("vy10", 0.0) * f
            vx10 = o.get("vx10", 0.0)
            vy10 = o.get("vy10", 0.0)
            x = o.get("x", 0.0) + (vx10 * t * 0.1)
            y = o.get("y", 0.0) + (vy10 * t * 0.1)

            if self.wrap_enabled and not bool(o.get("no_wrap", False)):
                minx, maxx, miny, maxy = self.wrap_bounds
                if x < minx:
                    x = maxx
                elif x > maxx:
                    x = minx
                if y < miny:
                    y = maxy
                elif y > maxy:
                    y = miny
            elif self.wrap_enabled and bool(o.get("no_wrap", False)) and bool(o.get("is_projectile", False)):
                minx, maxx, miny, maxy = self.wrap_bounds
                if x < minx or x > maxx or y < miny or y > maxy:
                    o["active"] = False
                    if obj_id in self.spawned_ids:
                        self.spawned_ids.remove(obj_id)
                    continue
            elif self.bounds_enabled:
                minx, maxx, miny, maxy = self.bounds
                if x < minx:
                    x = minx
                    vx10 = abs(vx10)
                elif x > maxx:
                    x = maxx
                    vx10 = -abs(vx10)
                if y < miny:
                    y = miny
                    vy10 = abs(vy10)
                elif y > maxy:
                    y = maxy
                    vy10 = -abs(vy10)
            o["x"] = x
            o["y"] = y
            o["vx10"] = vx10
            o["vy10"] = vy10

            angle10 = o.get("angle10", 0.0) + o.get("angleSpeed10", 0.0) * t
            if angle10 > 3600.0 or angle10 < -3600.0:
                angle10 = math.fmod(angle10, 3600.0)
            o["angle10"] = angle10

            phase = o.get("scalePhase", 0.0) + o.get("scaleSpeedRadPerMs", 0.0) * dt
            o["scalePhase"] = phase
            base = o.get("scaleBase1000", 1000.0)
            amp = o.get("scaleAmp1000", 0.0)
            scale1000 = base + amp * (0.5 + 0.5 * math.sin(phase))
            if scale1000 < 1.0:
                scale1000 = 1.0
            spr = int(o.get("spr", 0))
            frames = o.get("anim_frames")
            fps = int(o.get("anim_fps", 0))
            if frames and fps > 0:
                if o.get("anim_next_ms", 0) == 0:
                    o["anim_next_ms"] = now_ms
                frame_ms = int(1000 / fps) if fps > 0 else 1000
                if now_ms >= o["anim_next_ms"]:
                    o["anim_next_ms"] = now_ms + frame_ms
                    o["anim_index"] = int((o.get("anim_index", 0) + 1) % len(frames))
                spr = int(frames[o.get("anim_index", 0)])
            o["render"] = (int(x), int(y), spr, int(angle10), int(scale1000))

        # Optional per-object AABB bounce (used by asteroids rocks).
        active_bouncers = [
            obj_id for obj_id, o in self.objects.items()
            if o.get("active", False) and self.bounce_enabled.get(obj_id, False)
        ]
        for i in range(len(active_bouncers)):
            a_id = active_bouncers[i]
            oa = self.objects.get(a_id)
            if not oa:
                continue
            for j in range(i + 1, len(active_bouncers)):
                b_id = active_bouncers[j]
                ob = self.objects.get(b_id)
                if not ob:
                    continue
                aw, ah, aox, aoy = self.hitbox.get(a_id, (16, 16, 0, 0))
                bw, bh, box, boy = self.hitbox.get(b_id, (16, 16, 0, 0))
                ax = float(oa.get("x", 0.0)) + float(aox)
                ay = float(oa.get("y", 0.0)) + float(aoy)
                bx = float(ob.get("x", 0.0)) + float(box)
                by = float(ob.get("y", 0.0)) + float(boy)
                dx = bx - ax
                dy = by - ay
                rx = (float(aw) + float(bw)) * 0.5
                ry = (float(ah) + float(bh)) * 0.5
                if abs(dx) > rx or abs(dy) > ry:
                    continue
                relx = float(ob.get("vx10", 0.0)) - float(oa.get("vx10", 0.0))
                rely = float(ob.get("vy10", 0.0)) - float(oa.get("vy10", 0.0))
                approaching = (relx * dx + rely * dy) < 0.0
                if approaching:
                    tvx = float(oa.get("vx10", 0.0))
                    tvy = float(oa.get("vy10", 0.0))
                    oa["vx10"] = float(ob.get("vx10", 0.0))
                    oa["vy10"] = float(ob.get("vy10", 0.0))
                    ob["vx10"] = tvx
                    ob["vy10"] = tvy
                ox = rx - abs(dx)
                oy = ry - abs(dy)
                if ox < oy:
                    push = ox * 0.5 + 0.01
                    direction = 1.0 if dx >= 0.0 else -1.0
                    oa["x"] = float(oa.get("x", 0.0)) - direction * push
                    ob["x"] = float(ob.get("x", 0.0)) + direction * push
                else:
                    push = oy * 0.5 + 0.01
                    direction = 1.0 if dy >= 0.0 else -1.0
                    oa["y"] = float(oa.get("y", 0.0)) - direction * push
                    ob["y"] = float(ob.get("y", 0.0)) + direction * push

        for i in range(len(self.signals)):
            self.signals[i] = False
            self.signal_other[i] = None
            self.signal_source[i] = None
            self.slot_spawn_bullet_seen[i] = False
            self.slot_spawn_bullet_fired[i] = False

        if self.music_playing and self.music_signal is not None:
            if 0 <= self.music_signal < len(self.signals):
                self.signals[self.music_signal] = True
                self.signal_source[self.music_signal] = self.music_signal_owner
        self.signal_force = [False] * len(self.signals)
        if self.hud_enabled and int(self.hud_life) <= 0 and len(self.signals) > 7:
            self.signals[7] = True
            self.signal_source[7] = 0

        if self.bg_scroll_x10 != 0:
            self.bg_scroll_acc_x += (self.bg_scroll_x10 * t * 0.1)
            step = int(round(self.bg_scroll_acc_x))
            self.bg_scroll_acc_x -= step
            self.bg_scroll_x += step
        if self.bg_scroll_y10 != 0:
            self.bg_scroll_acc_y += (self.bg_scroll_y10 * t * 0.1)
            step = int(round(self.bg_scroll_acc_y))
            self.bg_scroll_acc_y -= step
            self.bg_scroll_y += step

        for obj_id, o in self.objects.items():
            if not o.get("active", False):
                continue
            if obj_id >= MAX_OBJECTS:
                continue
            for i in range(8):
                if not self.alarm_active[obj_id][i] or self.alarm_period[obj_id][i] <= 0:
                    continue
                if now_ms >= self.alarm_next[obj_id][i]:
                    sig = int(self.alarm_signal[obj_id][i])
                    if 0 <= sig < len(self.signals):
                        self.signals[sig] = True
                        self.signal_force[sig] = True
                        self.signal_other[sig] = int(obj_id)
                        self.signal_source[sig] = int(obj_id)
                    if self.alarm_repeat[obj_id][i]:
                        self.alarm_next[obj_id][i] = now_ms + self.alarm_period[obj_id][i]
                    else:
                        self.alarm_active[obj_id][i] = False

        for slot, ev, btn, owner in self.input_binds:
            # Ignore input binds declared by inactive objects so helper/debug
            # objects outside the current room don't hijack shared signal slots.
            if owner is not None:
                if owner not in self.objects:
                    continue
                if not self.objects[owner].get("active", False):
                    continue
            bit = 0
            if btn == 0:
                bit = INPUT_UP
            elif btn == 1:
                bit = INPUT_DOWN
            elif btn == 2:
                bit = INPUT_LEFT
            elif btn == 3:
                bit = INPUT_RIGHT
            elif btn == 4:
                bit = INPUT_A
            elif btn == 5:
                bit = INPUT_B
            elif btn == 6:
                bit = INPUT_X
            elif btn == 7:
                bit = INPUT_Y
            elif btn == 8:
                bit = INPUT_START
            elif btn == 9:
                bit = INPUT_SELECT
            elif btn == 10:
                bit = INPUT_L
            elif btn == 11:
                bit = INPUT_R
            down_now = (self.input_mask & bit) != 0
            down_prev = (getattr(self, "prev_input_mask", 0) & bit) != 0
            if ev == 0 and down_now:
                self.signals[slot] = True
                self.signal_source[slot] = owner
            elif ev == 1 and down_now and not down_prev:
                self.signals[slot] = True
                self.signal_source[slot] = owner
            elif ev == 2 and (not down_now) and down_prev:
                self.signals[slot] = True
                self.signal_source[slot] = owner
        self.prev_input_mask = self.input_mask

        projectile_hit_consumed = {}
        for slot, obj_a, obj_b in self.colliders:
            if slot < 0 or slot >= len(self.signals):
                continue
            oa = self.objects.get(obj_a)
            ob = self.objects.get(obj_b)
            if not oa or not ob:
                continue
            if not oa.get("active", False) or not ob.get("active", False):
                continue
            if oa.get("is_projectile", False) and projectile_hit_consumed.get(int(obj_a), False):
                continue
            aw, ah, aox, aoy = self.hitbox.get(obj_a, (16, 16, 0, 0))
            bw, bh, box, boy = self.hitbox.get(obj_b, (16, 16, 0, 0))
            ax = float(oa.get("x", 0.0)) + float(aox)
            ay = float(oa.get("y", 0.0)) + float(aoy)
            bx = float(ob.get("x", 0.0)) + float(box)
            by = float(ob.get("y", 0.0)) + float(boy)
            if abs(ax - bx) <= (aw * 0.5 + bw * 0.5) and abs(ay - by) <= (ah * 0.5 + bh * 0.5):
                if DEBUG_ASTEROIDS and int(slot) <= 2:
                    debug_log(f"[EMU] COLLIDE slot={slot} src={obj_a} other={obj_b} srcSpr={int(oa.get('spr',0))} otherSpr={int(ob.get('spr',0))}")
                self.signals[slot] = True
                self.signal_other[slot] = obj_b
                self.signal_source[slot] = obj_a
                if oa.get("is_projectile", False):
                    projectile_hit_consumed[int(obj_a)] = True

        for slot, ch in self.choices.items():
            if not ch.get("visible"):
                continue
            items = ch.get("items", [])
            if not items:
                continue
            up_now = (self.input_mask & INPUT_UP) != 0
            down_now = (self.input_mask & INPUT_DOWN) != 0
            ok_now = (self.input_mask & (INPUT_A | INPUT_START)) != 0
            if up_now and not ch.get("prev_up", False):
                ch["sel"] = (ch.get("sel", 0) - 1) % len(items)
            if down_now and not ch.get("prev_down", False):
                ch["sel"] = (ch.get("sel", 0) + 1) % len(items)
            if ok_now and not ch.get("prev_ok", False):
                base = int(ch.get("base", 0))
                sig = base + int(ch.get("sel", 0))
                if 0 <= sig < len(self.signals):
                    self.signals[sig] = True
                    self.signal_other[sig] = int(ch.get("sel", 0))
                    self.signal_source[sig] = self.choice_owner[int(slot)] if int(slot) < len(self.choice_owner) else None
            ch["prev_up"] = up_now
            ch["prev_down"] = down_now
            ch["prev_ok"] = ok_now

        for action in self.signal_actions:
            slot = action.get("slot", 0)
            if slot < 0 or slot >= len(self.signals):
                continue
            if not self.signals[slot] or (self.signal_prev[slot] and not self.signal_force[slot]):
                continue
            owner = action.get("owner", None)
            if owner is not None and owner != self.signal_source[slot]:
                continue
            if action.get("type") == "spawn_bullet":
                self.slot_spawn_bullet_seen[slot] = True
        slot_spawn_need = [0] * len(self.signals)
        slot_spawn_ok = [0] * len(self.signals)
        slot_defer_destroy_other = [False] * len(self.signals)
        slot_defer_destroy_target = [None] * len(self.signals)
        for action in self.signal_actions:
            slot = action.get("slot", 0)
            if slot < 0 or slot >= len(self.signals):
                continue
            if not self.signals[slot] or (self.signal_prev[slot] and not self.signal_force[slot]):
                continue
            owner = action.get("owner", None)
            if owner is not None and owner != self.signal_source[slot]:
                continue
            if action.get("type") == "spawn":
                slot_spawn_need[slot] += 1

        for action in self.signal_actions:
            slot = action.get("slot", 0)
            if slot < 0 or slot >= len(self.signals):
                continue
            if not self.signals[slot] or (self.signal_prev[slot] and not self.signal_force[slot]):
                continue
            owner = action.get("owner", None)
            if owner is not None and owner != self.signal_source[slot]:
                continue
            atype = action.get("type")
            log_action = DEBUG_ASTEROIDS and int(slot) <= 2
            # Ignore smoke spam: MASA_ON_SIGNAL_SPAWN_BULLET used as particle emitter
            # with speed10 == 0 (e.g. player rear smoke alarm).
            if atype == "spawn_bullet" and int(action.get("speed10", 0)) == 0:
                log_action = False
            if log_action:
                debug_log(f"[EMU] ACTION slot={slot} type={atype} owner={owner} src={self.signal_source[slot]} other={self.signal_other[slot]} obj={action.get('obj')}")
            if atype == "destroy":
                obj = action.get("obj")
                if DEBUG_ASTEROIDS and int(slot) <= 2:
                    debug_log(f"[EMU] DESTROY slot={slot} target={obj} spr={int(self.objects.get(obj,{}).get('spr',0))}")
                if obj in self.objects:
                    self.objects[obj]["active"] = False
                    self.objects[obj]["is_projectile"] = False
                if obj in self.spawned_ids:
                    self.spawned_ids.remove(obj)
            elif atype == "destroy_other":
                obj = int(self.signal_other[slot])
                if slot_spawn_need[int(slot)] > 0:
                    slot_defer_destroy_other[int(slot)] = True
                    slot_defer_destroy_target[int(slot)] = obj
                else:
                    if DEBUG_ASTEROIDS and int(slot) <= 2:
                        debug_log(f"[EMU] DESTROY_OTHER slot={slot} target={obj} spr={int(self.objects.get(obj,{}).get('spr',0))}")
                    if obj in self.objects:
                        self.objects[obj]["active"] = False
                        self.objects[obj]["is_projectile"] = False
                    if obj in self.spawned_ids:
                        self.spawned_ids.remove(obj)
            elif atype == "spawn":
                obj = action.get("obj")
                if obj is None:
                    continue
                src = self.signal_source[slot] if 0 <= slot < len(self.signal_source) else None
                if self.objects.get(obj, {}).get("active", False) and int(obj) != int(src if src is not None else -1):
                    fallback_obj = None
                    target_spr = int(action.get("spr", 0))
                    other = self.signal_other[slot] if 0 <= slot < len(self.signal_other) else None
                    if DEBUG_ASTEROIDS and int(slot) <= 2:
                        debug_log(f"[EMU] SPAWN target busy slot={slot} obj={obj} spr={int(self.objects.get(obj,{}).get('spr',0))} wantedSpr={target_spr}")
                    for cand_id, cand in self.objects.items():
                        if cand.get("active", False):
                            continue
                        if cand_id == src or cand_id == other:
                            continue
                        if int(cand.get("spr", 0)) == target_spr:
                            fallback_obj = cand_id
                            break
                    if fallback_obj is None:
                        if DEBUG_ASTEROIDS and int(slot) <= 2:
                            debug_log(f"[EMU] SPAWN FAILED slot={slot} wantedSpr={target_spr} (no compatible free slot)")
                        continue
                    if DEBUG_ASTEROIDS and int(slot) <= 2:
                        debug_log(f"[EMU] SPAWN fallback slot={slot} old={obj} new={fallback_obj} wantedSpr={target_spr}")
                    obj = int(fallback_obj)
                sx = float(action.get("x", 0))
                sy = float(action.get("y", 0))
                k_spawn_source = 32767
                k_spawn_other = 32766
                other = self.signal_other[slot] if 0 <= slot < len(self.signal_other) else None
                if int(sx) == k_spawn_source and src in self.objects:
                    sx = float(self.objects[src].get("x", 0.0))
                elif int(sx) == k_spawn_other and other in self.objects:
                    sx = float(self.objects[other].get("x", 0.0))
                if int(sy) == k_spawn_source and src in self.objects:
                    sy = float(self.objects[src].get("y", 0.0))
                elif int(sy) == k_spawn_other and other in self.objects:
                    sy = float(self.objects[other].get("y", 0.0))
                if DEBUG_ASTEROIDS and int(slot) <= 2:
                    debug_log(f"[EMU] SPAWN slot={slot} obj={obj} x={int(sx)} y={int(sy)} spr={int(action.get('spr',0))} src={src} other={other}")
                self.objects.setdefault(obj, {})
                self.objects[obj].update({
                    "x": float(sx),
                    "y": float(sy),
                    "spr": int(action.get("spr", 0)),
                    "active": True,
                    "is_projectile": False,
                    "angle10": 0.0,
                    "angleSpeed10": 0.0,
                    "vx10": 0.0,
                    "vy10": 0.0,
                    "accel10": 0.0,
                    "friction1000": 1000.0,
                    "scaleBase1000": 1000.0,
                    "scaleAmp1000": 0.0,
                    "scalePhase": 0.0,
                    "scaleSpeedRadPerMs": 0.0,
                    "anim_index": 0,
                    "anim_next_ms": 0,
                })
                if int(obj) in self.vel_random:
                    self.objects[obj]["vx10"] = float(self._rand_vel10(int(obj)))
                    self.objects[obj]["vy10"] = float(self._rand_vel10(int(obj)))
                self._start_alarm_defaults(int(obj), self._now_ms())
                self.spawned_ids.add(obj)
                slot_spawn_ok[int(slot)] += 1
            elif atype == "sound":
                if self.audio_cb:
                    try:
                        self.audio_cb(int(action.get("sound", 0)))
                    except Exception:
                        pass
            elif atype == "room_next":
                if self.room_count > 0:
                    self.set_room((self.room_index + 1) % self.room_count)
            elif atype == "room_goto":
                if self.room_count > 0:
                    target = int(action.get("room", 0))
                    if 0 <= target < self.room_count:
                        self.set_room(target)
            elif atype == "spawn_bullet":
                src = int(action.get("src", 0))
                slot = int(action.get("slot", 0))
                if 0 <= slot < len(self.signal_source) and self.signal_source[slot] is not None:
                    src = int(self.signal_source[slot])
                bullet = int(action.get("bullet", 0))
                fired = False
                if src in self.objects:
                    src_obj = self.objects[src]
                    angle10 = float(src_obj.get("angle10", 0.0))
                    rad = (angle10 * 0.1) * math.pi / 180.0
                    offset = float(action.get("offset", 0.0))
                    speed10 = float(action.get("speed10", 0.0))
                    if abs(speed10) > 0.01 and bullet in self.objects and self.objects[bullet].get("active", False):
                        continue
                    bx = float(src_obj.get("x", 0.0)) + math.cos(rad) * offset
                    by = float(src_obj.get("y", 0.0)) + math.sin(rad) * offset
                    self.objects.setdefault(bullet, {})
                    b = self.objects[bullet]
                    frame = action.get("frame", None)
                    if frame is None:
                        frame = b.get("spr", 0)
                    else:
                        try:
                            frame = int(frame)
                        except Exception:
                            frame = b.get("spr", 0)
                        if frame == 0xFF:
                            frame = b.get("spr", 0)
                    b.update({
                        "x": bx,
                        "y": by,
                        "active": True,
                        "is_projectile": True,
                        "spr": int(frame),
                        "angle10": angle10,
                        "angleSpeed10": 0.0,
                        "inputSpeed10": 0.0,
                        "accel10": 0.0,
                        "friction1000": 1000.0,
                        "turnSpeed10": 0.0,
                        "thrust10": 0.0,
                    })
                    b["vx10"] = math.cos(rad) * speed10
                    b["vy10"] = math.sin(rad) * speed10
                    self.spawned_ids.add(bullet)
                    fired = True
                if 0 <= slot < len(self.slot_spawn_bullet_fired) and fired:
                    self.slot_spawn_bullet_fired[slot] = True
            elif atype == "beep":
                slot = int(action.get("slot", -1))
                if 0 <= slot < len(self.slot_spawn_bullet_seen):
                    if self.slot_spawn_bullet_seen[slot] and not self.slot_spawn_bullet_fired[slot]:
                        continue
                self._emit_beep(int(action.get("hz", 0)), int(action.get("ms", 0)))
            elif atype == "stop":
                obj = action.get("obj")
                if obj in self.objects:
                    o = self.objects[obj]
                    o["vx10"] = 0.0
                    o["vy10"] = 0.0
                    o["inputSpeed10"] = 0.0
                    o["angleSpeed10"] = 0.0
            elif atype == "textbox":
                box = int(action.get("box", 0))
                self.textbox[box] = {
                    "visible": True,
                    "x": int(action.get("x", 0)),
                    "y": int(action.get("y", 0)),
                    "w": int(action.get("w", 0)),
                    "h": int(action.get("h", 0)),
                    "color": int(action.get("color", 15)),
                    "text": str(action.get("text", "")),
                }
            elif atype == "choices":
                ch = int(action.get("choice", 0))
                self.choices[ch] = {
                    "visible": True,
                    "x": int(action.get("x", 0)),
                    "y": int(action.get("y", 0)),
                    "color": int(action.get("color", 15)),
                    "items": list(action.get("items", []))[:5],
                    "sel": 0,
                    "base": int(action.get("base", 0)),
                    "prev_up": False,
                    "prev_down": False,
                    "prev_ok": False,
                }
            elif atype == "textbox_clear":
                box = int(action.get("box", 0))
                if box in self.textbox:
                    self.textbox[box]["visible"] = False
            elif atype == "choices_clear":
                ch = int(action.get("choice", 0))
                if ch in self.choices:
                    self.choices[ch]["visible"] = False
            elif atype == "set_input":
                obj = action.get("obj")
                if obj in self.objects:
                    self.objects[obj]["inputSpeed10"] = float(action.get("speed10", 0))
            elif atype == "hud_add":
                self.hud_life += int(action.get("life", 0))
                if self.hud_life < 0:
                    self.hud_life = 0
                self.hud_score += int(action.get("score", 0))
                self.hud_coins += int(action.get("coins", 0))
                if self.hud_enabled and self.hud_life <= 0:
                    src = self.signal_source[slot] if 0 <= slot < len(self.signal_source) else None
                    if src in self.objects:
                        self.objects[src]["active"] = False
                        self.objects[src]["is_projectile"] = False
            elif atype == "show_text":
                tslot = max(0, min(7, int(action.get("text_slot", 0))))
                old_span = int(self.text_span[tslot]) if 0 <= tslot < len(self.text_span) else 1
                if old_span <= 0:
                    old_span = 1
                for si in range(old_span):
                    ss = tslot + si
                    if ss >= len(self.text_slots):
                        break
                    self.text_slots[ss]["visible"] = False
                    self.text_slots[ss]["text"] = ""
                txt = str(action.get("text", ""))
                txt = txt.replace("{SCORE}", str(int(self.hud_score)))
                align = max(0, min(2, int(action.get("align", 0))))
                draw_x = int(action.get("x", 0))
                total_len = len(txt)
                if align == 1:
                    draw_x -= (total_len * 6) // 2
                elif align == 2:
                    draw_x -= total_len * 6
                max_chars = 24
                max_span = len(self.text_slots) - tslot
                used_span = 0
                cursor = 0
                consumed_total = 0
                while used_span < max_span:
                    ss = tslot + used_span
                    if ss >= len(self.text_slots):
                        break
                    chunk = ""
                    consumed = 0
                    if cursor < total_len:
                        rem = total_len - cursor
                        take = max_chars if rem > max_chars else rem
                        if rem > max_chars:
                            split = -1
                            for k in range(take - 1, 0, -1):
                                if txt[cursor + k] == " ":
                                    split = k
                                    break
                            if split > 0:
                                take = split + 1
                        chunk = txt[cursor:cursor + take]
                        consumed = take
                        while (cursor + consumed) < total_len and txt[cursor + consumed] == " ":
                            consumed += 1
                    self.text_slots[ss] = {
                        "visible": True,
                        "x": int(draw_x + consumed_total * 6),
                        "y": int(action.get("y", 0)),
                        "color": int(action.get("color", 15)),
                        "text": chunk,
                    }
                    used_span += 1
                    if cursor >= total_len or consumed <= 0:
                        break
                    cursor += consumed
                    consumed_total += consumed
                if used_span <= 0:
                    used_span = 1
                if tslot < len(self.text_span):
                    self.text_span[tslot] = int(used_span)
            elif atype == "show_text_clear":
                tslot = max(0, min(7, int(action.get("text_slot", 0))))
                span = int(self.text_span[tslot]) if 0 <= tslot < len(self.text_span) else 1
                if span <= 0:
                    span = 1
                for si in range(span):
                    ss = tslot + si
                    if ss >= len(self.text_slots):
                        break
                    self.text_slots[ss]["visible"] = False
                    self.text_slots[ss]["text"] = ""
                if 0 <= tslot < len(self.text_span):
                    self.text_span[tslot] = 1
        for sidx in range(len(self.signals)):
            if not slot_defer_destroy_other[sidx]:
                continue
            target = slot_defer_destroy_target[sidx]
            if target is None:
                continue
            can_destroy_other = (
                slot_spawn_need[sidx] == 0
                or slot_spawn_ok[sidx] >= slot_spawn_need[sidx]
                or slot_spawn_need[sidx] <= 1
            )
            if can_destroy_other:
                if DEBUG_ASTEROIDS and int(sidx) <= 2:
                    debug_log(f"[EMU] DESTROY_OTHER(deferred) slot={sidx} target={target} spr={int(self.objects.get(target,{}).get('spr',0))}")
                if target in self.objects:
                    self.objects[target]["active"] = False
                    self.objects[target]["is_projectile"] = False
                if target in self.spawned_ids:
                    self.spawned_ids.remove(target)
            elif DEBUG_ASTEROIDS and int(sidx) <= 2:
                debug_log(f"[EMU] DESTROY_OTHER canceled slot={sidx} need={slot_spawn_need[sidx]} got={slot_spawn_ok[sidx]} target={target}")

        for i in range(len(self.signals)):
            self.signal_prev[i] = self.signals[i]

        for obj_id, o in self.objects.items():
            if not o.get("active", False):
                continue
            if self.room_count > 0 and obj_id not in self.room_active_ids and obj_id not in self.room_persistent_all and obj_id not in self.spawned_ids:
                continue
            render = o.get("render")
            if not render:
                render = (int(o.get("x", 0)), int(o.get("y", 0)), int(o.get("spr", 0)), int(o.get("angle10", 0)), int(o.get("scaleBase1000", 1000)))
            cmds.append((RENDER_DRAW_SPRITE_XFORM, render[0], render[1], render[2], render[3], render[4]))

        for slot, tb in self.textbox.items():
            if not tb.get("visible"):
                continue
            x = int(tb.get("x", 0))
            y = int(tb.get("y", 0))
            w = int(tb.get("w", 0))
            h = int(tb.get("h", 0))
            color = int(tb.get("color", 15))
            text = str(tb.get("text", ""))
            x2 = x + w
            y2 = y + h
            cmds.append((RENDER_DRAW_SHAPE, 3, x, y, x2, y2, 0, 0, color))
            cmds.append((RENDER_DRAW_SHAPE, 2, x, y, x2, y2, 0, 0, 15))
            line1 = text
            line2 = ""
            if "|" in text:
                parts = text.split("|", 1)
                line1 = parts[0]
                line2 = parts[1]
            if line1:
                cmds.append((RENDER_DRAW_TEXT, x + 6, y + 8, 15, line1))
            if line2:
                cmds.append((RENDER_DRAW_TEXT, x + 6, y + 20, 15, line2))

        for slot, ch in self.choices.items():
            if not ch.get("visible"):
                continue
            items = ch.get("items", [])
            if not items:
                continue
            base_x = int(ch.get("x", 0))
            base_y = int(ch.get("y", 0))
            col = int(ch.get("color", 15))
            sel = int(ch.get("sel", 0))
            for idx, label in enumerate(items):
                prefix = "> " if idx == sel else ""
                color = 15 if idx == sel else col
                cmds.append((RENDER_DRAW_TEXT, base_x, base_y + idx * 12, color, f"{prefix}{label}"))
        for slot in self.text_slots:
            if not slot.get("visible"):
                continue
            text = slot.get("text", "")
            if not text:
                continue
            cmds.append((RENDER_DRAW_TEXT, int(slot.get("x", 0)), int(slot.get("y", 0)),
                         int(slot.get("color", 15)), text))
        if self.hud_enabled:
            hud_tpl = str(getattr(self, "hud_template", "L:{LIFE} S:{SCORE} C:{COINS}") or "L:{LIFE} S:{SCORE} C:{COINS}")
            hud = (hud_tpl
                   .replace("{LIFE}", str(int(self.hud_life)))
                   .replace("{SCORE}", str(int(self.hud_score)))
                   .replace("{COINS}", str(int(self.hud_coins))))
            draw_x = int(self.hud_x)
            draw_y = int(self.hud_y)
            text_w = len(hud) * 6
            align = int(getattr(self, "hud_align", 0))
            if align == 1:
                draw_x -= (text_w // 2)
            elif align == 2:
                draw_x -= text_w
            bg_color = int(getattr(self, "hud_bg_color", -1))
            if bg_color >= 0:
                pad_x = max(0, int(getattr(self, "hud_pad_x", 2)))
                pad_y = max(0, int(getattr(self, "hud_pad_y", 1)))
                x1 = draw_x - pad_x
                y1 = draw_y - pad_y
                x2 = draw_x + text_w + pad_x
                y2 = draw_y + 8 + pad_y
                cmds.append((RENDER_DRAW_SHAPE, 3, x1, y1, x2, y2, 0, 0, bg_color))
            cmds.append((RENDER_DRAW_TEXT, draw_x, draw_y, int(self.hud_color), hud))
        if self.hud_enabled and int(self.hud_life) <= 0:
            if not self.game_over_armed:
                if int(self.input_mask) == 0:
                    self.game_over_armed = True
            else:
                restart_mask = (INPUT_A | INPUT_B | INPUT_X | INPUT_Y |
                                INPUT_START | INPUT_SELECT | INPUT_L | INPUT_R)
                now_restart = int(self.input_mask) & int(restart_mask)
                if now_restart != 0 and int(self.game_over_prev_mask) == 0:
                    self.reset()
                    return []
                self.game_over_prev_mask = now_restart
        for slot in self.var_text:
            if not slot.get("visible"):
                continue
            val = 0
            if int(slot.get("scope", 0)) == 0:
                idx = int(slot.get("idx", 0))
                if 0 <= idx < len(self.var_global):
                    val = self.var_global[idx]
            else:
                obj = int(slot.get("obj", 0))
                idx = int(slot.get("idx", 0))
                if 0 <= obj < len(self.var_obj) and 0 <= idx < len(self.var_obj[obj]):
                    val = self.var_obj[obj][idx]
            label = str(slot.get("label", ""))
            text = f"{label}{val}" if label else f"{val}"
            cmds.append((RENDER_DRAW_TEXT, int(slot.get("x", 0)), int(slot.get("y", 0)),
                         int(slot.get("color", 15)), text))
        for slot in self.varf_text:
            if not slot.get("visible"):
                continue
            val = 0.0
            if int(slot.get("scope", 0)) == 0:
                idx = int(slot.get("idx", 0))
                if 0 <= idx < len(self.varf_global):
                    val = self.varf_global[idx]
            else:
                obj = int(slot.get("obj", 0))
                idx = int(slot.get("idx", 0))
                if 0 <= obj < len(self.varf_obj) and 0 <= idx < len(self.varf_obj[obj]):
                    val = self.varf_obj[obj][idx]
            label = str(slot.get("label", ""))
            text = f"{label}{val:.2f}" if label else f"{val:.2f}"
            cmds.append((RENDER_DRAW_TEXT, int(slot.get("x", 0)), int(slot.get("y", 0)),
                         int(slot.get("color", 15)), text))
        for slot in self.str_text:
            if not slot.get("visible"):
                continue
            val = ""
            if int(slot.get("scope", 0)) == 0:
                idx = int(slot.get("idx", 0))
                if 0 <= idx < len(self.str_global):
                    val = self.str_global[idx]
            else:
                obj = int(slot.get("obj", 0))
                idx = int(slot.get("idx", 0))
                if 0 <= obj < len(self.str_obj) and 0 <= idx < len(self.str_obj[obj]):
                    val = self.str_obj[obj][idx]
            label = str(slot.get("label", ""))
            text = f"{label}{val}" if label else f"{val}"
            cmds.append((RENDER_DRAW_TEXT, int(slot.get("x", 0)), int(slot.get("y", 0)),
                         int(slot.get("color", 15)), text))
        for slot in self.shape_slots:
            if not slot.get("visible"):
                continue
            coords = slot.get("coords", (0, 0, 0, 0, 0, 0))
            cmds.append((RENDER_DRAW_SHAPE, int(slot.get("type", 0)),
                         int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3]),
                         int(coords[4]), int(coords[5]), int(slot.get("color", 15))))
        return cmds

    def poll_music_cmd(self):
        if not self.music_cmd:
            return None
        cmd = self.music_cmd
        self.music_cmd = None
        return cmd


class SimpleAudio:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def stop(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._stop.set()
                self._thread.join(timeout=0.2)
            self._stop.clear()

    def play(self, name, song, loop=False):
        if not WIN_SOUND_AVAILABLE:
            return
        if not song:
            return
        notes, durs = song
        self.stop()
        self._thread = threading.Thread(target=self._run, args=(notes, durs, loop), daemon=True)
        self._thread.start()

    def _run(self, notes, durs, loop):
        while not self._stop.is_set():
            for freq, dur in zip(notes, durs):
                if self._stop.is_set():
                    return
                if freq <= 0.0:
                    time.sleep(max(0.0, dur) / 1000.0)
                else:
                    try:
                        winsound.Beep(int(freq), int(dur))
                    except Exception:
                        time.sleep(max(0.0, dur) / 1000.0)
            if not loop:
                return


def fnv1a_32(text: str) -> int:
    h = 0x811C9DC5
    for ch in text:
        h ^= ord(ch) & 0xFF
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def parse_num_list(text: str):
    out = []
    for part in text.replace("\n", " ").split(","):
        part = part.strip()
        if not part:
            continue
        if part.endswith("f") or part.endswith("F"):
            part = part[:-1]
        try:
            out.append(float(part))
        except Exception:
            pass
    return out


def parse_songs_header(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read()
    notes_map = {}
    durs_map = {}
    for m in re.finditer(r"static\s+const\s+float\s+(\w+)Notes\[\]\s*=\s*\{([^}]*)\};", txt, re.S):
        notes_map[m.group(1)] = parse_num_list(m.group(2))
    for m in re.finditer(r"static\s+const\s+unsigned\s+short\s+(\w+)DurMs\[\]\s*=\s*\{([^}]*)\};", txt, re.S):
        durs_map[m.group(1)] = [int(x) for x in parse_num_list(m.group(2))]
    song_order = []
    songs_db = {}
    for sm in re.finditer(r"\{\s*\"([^\"]+)\"\s*,\s*(\w+)Notes\s*,\s*(\w+)DurMs", txt):
        name = sm.group(1)
        notes_key = sm.group(2)
        durs_key = sm.group(3)
        notes = notes_map.get(notes_key, [])
        durs = durs_map.get(durs_key, [])
        if notes and durs:
            songs_db[name] = (notes, durs)
            song_order.append(name)
    return songs_db, song_order


class Emulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MOFONGO32 Emulator")
        self.configure(bg=THEME["bg"])
        self.option_add("*Background", THEME["bg"])
        self.option_add("*Foreground", THEME["text"])
        self.option_add("*Button.Background", THEME["panel"])
        self.option_add("*Button.Foreground", THEME["text"])
        self.geometry("900x520")
        self._apply_logo()
        self._build_menu()

        self.runtime = None
        self.last_cmds = []
        self.project = None
        self.songs_db = {}
        self.song_order = []
        self.song_hash_map = {}
        self.song_path = ""
        self.audio = SimpleAudio()
        self.sprites_meta = None
        self.backgrounds_meta = None
        self.tilemaps = []
        self.sprite_images = []
        self.bg_images_pil = []
        self.sprite_images_scaled = []
        self.sprite_scaled_cache = {}
        self.sprite_pil = []
        self.sprite_transform_cache = {}
        self.sprite_paths = []
        self.tile_cache = {}
        self.demo_anim_frames = [0]
        self.bg_image = None
        self.bg_image_scaled = None
        self.bg_color = 12
        self.scale = DEFAULT_SCALE
        self.canvas_w = ROOM_W * DEFAULT_SCALE
        self.canvas_h = ROOM_H * DEFAULT_SCALE
        self.offset_x = 0
        self.offset_y = 0
        self.bg_scroll_x = 0
        self.bg_scroll_y = 0
        self.demo_mode = False
        self.canvas_images = []
        self.loop_mode = False
        self.last_room_index = -1
        self.key_down = set()
        self.select_down = False
        self.last_select_ms = 0

        top = tk.Frame(self, bg=THEME["bg"])
        top.pack(fill="x", padx=8, pady=6)
        self.status = tk.Label(top, text="No file loaded", bg=THEME["bg"], fg=THEME["text"])
        self.status.pack(side="left", padx=10)
        self.pil_status = tk.Label(top, text="", bg=THEME["bg"], fg=THEME["text"])
        self.pil_status.pack(side="left", padx=10)
        self.audio_status = tk.Label(top, text="", bg=THEME["bg"], fg=THEME["text"])
        self.audio_status.pack(side="left", padx=10)
        self.song_status = tk.Label(top, text="", bg=THEME["bg"], fg=THEME["text"])
        self.song_status.pack(side="left", padx=10)
        self.song_debug = tk.Label(top, text="", bg=THEME["bg"], fg=THEME["text"])
        self.song_debug.pack(side="left", padx=10)
        self.input_help_text = "Keys: Arrows=Move  A=Z/Space  B=X  X=A  Y=S  Start=Enter  Select=Tab  L=Q  R=E"

        self.canvas = tk.Canvas(
            self,
            width=self.canvas_w,
            height=self.canvas_h,
            bg=THEME["panel"],
            highlightthickness=0,
        )
        self.canvas.pack(padx=8, pady=8, fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.bind("<KeyPress>", self.on_key_down)
        self.bind("<KeyRelease>", self.on_key_up)
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        self.canvas.focus_set()
        self.focus_set()

        self.geometry(f"{ROOM_W * DEFAULT_SCALE + 40}x{ROOM_H * DEFAULT_SCALE + 120}")

        self.after(16, self.tick)
        self._update_pil_status()
        self._update_audio_status()

    def _scale_image(self, img):
        if img is None:
            return None
        if self.scale >= 1:
            try:
                return img.zoom(self.scale, self.scale)
            except Exception:
                return img
        return img

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load .masa", command=self.load_masa)
        file_menu.add_command(label="Load .ingr", command=self.load_ingr)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        inputs_menu = tk.Menu(menubar, tearoff=0)
        help_text = getattr(self, "input_help_text", "Keys: Arrows=Move  A=Z/Space  B=X  X=A  Y=S  Start=Enter  Select=Tab  L=Q  R=E")
        inputs_menu.add_command(label=help_text)
        menubar.add_cascade(label="Inputs", menu=inputs_menu)
        self.config(menu=menubar)

    def _apply_logo(self):
        logo_path = os.path.join(os.path.dirname(__file__), "..", "mofongo_logo.png")
        logo_path = os.path.abspath(logo_path)
        self.logo_image = None
        if os.path.isfile(logo_path):
            try:
                self.logo_image = tk.PhotoImage(file=logo_path)
                self.iconphoto(False, self.logo_image)
            except Exception:
                self.logo_image = None

    def _scale_sprite(self, spr_id, scale):
        key = (spr_id, scale)
        if key in self.sprite_scaled_cache:
            return self.sprite_scaled_cache[key]
        if 0 <= spr_id < len(self.sprite_images) and self.sprite_images[spr_id] is not None:
            base = self.sprite_images[spr_id]
            try:
                img = base.zoom(scale, scale)
            except Exception:
                img = base
            self.sprite_scaled_cache[key] = img
            return img
        return None

    def _load_images_from_meta(self):
        self.sprite_images = []
        self.sprite_images_scaled = []
        self.sprite_pil = []
        self.sprite_transform_cache = {}
        self.sprite_paths = []
        self.demo_anim_frames = [0]
        self.bg_images_pil = []
        self.bg_images = []
        if self.sprites_meta:
            for p in self.sprites_meta.get("pngs", []):
                self.sprite_paths.append(p)
                try:
                    img = tk.PhotoImage(file=p)
                except Exception:
                    img = None
                self.sprite_images.append(img)
                self.sprite_images_scaled.append(self._scale_image(img))
                if PIL_AVAILABLE:
                    try:
                        self.sprite_pil.append(Image.open(p).convert("RGBA"))
                    except Exception:
                        self.sprite_pil.append(None)
                else:
                    self.sprite_pil.append(None)

            anims = self.sprites_meta.get("animations", {})
            if isinstance(anims, dict) and anims:
                # Prefer the first animation in metadata for demo.
                first_key = list(anims.keys())[0]
                frames = anims.get(first_key, [])
                if isinstance(frames, list) and frames:
                    self.demo_anim_frames = [int(x) for x in frames]

        self.bg_image = None
        self.bg_image_scaled = None
        if self.backgrounds_meta:
            bg_idx = 0
            if self.project:
                try:
                    bg_idx = int(self.project.get("background_index", 0))
                except Exception:
                    bg_idx = 0
            pngs = self.backgrounds_meta.get("pngs", [])
            for p in pngs:
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
            if 0 <= bg_idx < len(pngs):
                try:
                    self.bg_image = tk.PhotoImage(file=pngs[bg_idx])
                    self.bg_image_scaled = self._scale_image(self.bg_image)
                except Exception:
                    self.bg_image = None
                    self.bg_image_scaled = None

    def on_canvas_resize(self, event):
        w = max(1, int(event.width))
        h = max(1, int(event.height))
        scale = int(min(w / ROOM_W, h / ROOM_H))
        if scale < 1:
            scale = 1
        self.canvas_w = w
        self.canvas_h = h
        self.offset_x = (w - ROOM_W * scale) // 2
        self.offset_y = (h - ROOM_H * scale) // 2
        if scale != self.scale:
            self.scale = scale
            self._load_images_from_meta()
            self.sprite_scaled_cache = {}

    def load_masa(self):
        path = filedialog.askopenfilename(filetypes=[("MASA files", "*.masa"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        hdr = read_header(data)
        if not hdr or hdr["magic"] != 0x4D415341:
            self.status.config(text="Invalid MASA file")
            self.runtime = None
            return
        s0 = hdr["script_offset"]
        s1 = s0 + hdr["script_size"]
        script = data[s0:s1]
        self.runtime = Runtime(script, hdr["entry_point"])
        self.runtime.set_audio_callback(self.on_play_sound)
        self.last_cmds = []
        rooms = b""
        if hdr.get("tilemap_size", 0):
            r0 = hdr["tilemap_offset"]
            r1 = r0 + hdr["tilemap_size"]
            rooms = data[r0:r1]
            if rooms:
                self.runtime.set_rooms(rooms)
                self.last_cmds = []
        if not self.sprites_meta and not self.backgrounds_meta:
            alt = os.path.splitext(path)[0] + ".ingr"
            if os.path.isfile(alt):
                try:
                    self._load_ingr_path(alt)
                except Exception:
                    pass
        self._load_songs()
        song_hash = int(hdr.get("song_hash") or 0)
        if self.runtime and self.runtime.room_count > 0:
            song_hash = int(self.runtime.room_song_hash)
        if song_hash:
            self.play_song_by_hash(song_hash)
        else:
            self.song_status.config(text="SongHash: none")
        if self.runtime and self.runtime.room_count > 0:
            self._apply_room_visuals()
        self.status.config(text=f"Loaded {os.path.basename(path)}")
        self.demo_mode = False

    def _extract_assets(self, zf, base_dir):
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

    def _load_ingr_path(self, path):
        with zipfile.ZipFile(path, "r") as zf:
            if "project.json" not in zf.namelist():
                raise ValueError("Missing project.json in .ingr")
            self.project = json.loads(zf.read("project.json").decode("utf-8"))
            if "tilemaps/tilemaps.json" in zf.namelist():
                try:
                    self.project["tilemaps"] = json.loads(zf.read("tilemaps/tilemaps.json").decode("utf-8"))
                except Exception:
                    pass
            self.tilemaps = self.project.get("tilemaps", []) if isinstance(self.project.get("tilemaps"), list) else []
            cache_root = os.path.join(os.path.dirname(__file__), "emulator_cache", sanitize_filename(self.project.get("name", "game_project")))
            assets = self._extract_assets(zf, cache_root)

            sprites_meta = None
            backgrounds_meta = None
            if "assets/metadata/sprites.json" in zf.namelist():
                sprites_meta = json.loads(zf.read("assets/metadata/sprites.json").decode("utf-8"))
            if "assets/metadata/backgrounds.json" in zf.namelist():
                backgrounds_meta = json.loads(zf.read("assets/metadata/backgrounds.json").decode("utf-8"))

            if sprites_meta and isinstance(sprites_meta.get("pngs"), list):
                sprites_meta["pngs"] = [assets.get(f"assets/sprites/{os.path.basename(p)}", p) for p in sprites_meta.get("pngs", [])]
            if backgrounds_meta and isinstance(backgrounds_meta.get("pngs"), list):
                backgrounds_meta["pngs"] = [assets.get(f"assets/backgrounds/{os.path.basename(p)}", p) for p in backgrounds_meta.get("pngs", [])]

            self.sprites_meta = sprites_meta
            self.backgrounds_meta = backgrounds_meta
            self._load_images_from_meta()
            try:
                active_room = int(self.project.get("active_room", 0))
                rooms = self.project.get("rooms", [])
                if 0 <= active_room < len(rooms):
                    self.bg_color = int(rooms[active_room].get("background_color", 12))
                else:
                    self.bg_color = int(self.project.get("background_color", 12))
            except Exception:
                self.bg_color = int(self.project.get("background_color", 12)) if self.project else 12
            header_song = os.path.join(cache_root, "assets", "headers", "songs.h")
            if os.path.isfile(header_song):
                self.song_path = header_song
            else:
                self.song_path = os.path.join(cache_root, "gfx", "songs.h")
            self._load_songs()

    def load_ingr(self):
        path = filedialog.askopenfilename(filetypes=[("Mofongo project", "*.ingr"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._load_ingr_path(path)
            self.status.config(text=f"Loaded {os.path.basename(path)}")
            self.demo_mode = False
        except Exception as e:
            self.status.config(text=f"Load failed: {e}")

    def load_path(self, path: str):
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".masa":
            try:
                with open(path, "rb") as f:
                    data = f.read()
                hdr = read_header(data)
                if not hdr or hdr["magic"] != 0x4D415341:
                    self.status.config(text="Invalid MASA file")
                    self.runtime = None
                    return
                s0 = hdr["script_offset"]
                s1 = s0 + hdr["script_size"]
                script = data[s0:s1]
                self.runtime = Runtime(script, hdr["entry_point"])
                self.runtime.set_audio_callback(self.on_play_sound)
                self.last_cmds = []
                rooms = b""
                if hdr.get("tilemap_size", 0):
                    r0 = hdr["tilemap_offset"]
                    r1 = r0 + hdr["tilemap_size"]
                    rooms = data[r0:r1]
                    if rooms:
                        self.runtime.set_rooms(rooms)
                        self.last_cmds = []
                if not self.sprites_meta and not self.backgrounds_meta:
                    alt = os.path.splitext(path)[0] + ".ingr"
                    if os.path.isfile(alt):
                        try:
                            self._load_ingr_path(alt)
                        except Exception:
                            pass
                self._load_songs()
                song_hash = int(hdr.get("song_hash") or 0)
                if self.runtime and self.runtime.room_count > 0:
                    song_hash = int(self.runtime.room_song_hash)
                if song_hash:
                    self.play_song_by_hash(song_hash)
                else:
                    self.song_status.config(text="SongHash: none")
                if self.runtime and self.runtime.room_count > 0:
                    self._apply_room_visuals()
                self.status.config(text=f"Loaded {os.path.basename(path)}")
                self.demo_mode = False
            except Exception as e:
                self.status.config(text=f"Load failed: {e}")
        elif ext == ".ingr":
            try:
                self._load_ingr_path(path)
                self.status.config(text=f"Loaded {os.path.basename(path)}")
                self.demo_mode = False
            except Exception as e:
                self.status.config(text=f"Load failed: {e}")

    def draw_cmds(self, cmds):
        self.canvas.delete("all")
        self.canvas_images = []
        if not self.bg_image_scaled:
            fill = self.sprite_color(int(self.bg_color))
            self.canvas.create_rectangle(0, 0, self.canvas_w, self.canvas_h, fill=fill, outline="")
        if self.bg_image_scaled:
            img = self.bg_image_scaled
            try:
                w = img.width()
                h = img.height()
            except Exception:
                w = 0
                h = 0
            if w <= 0 or h <= 0:
                self.canvas.create_image(self.offset_x, self.offset_y, image=img, anchor="nw")
            else:
                ox = self.offset_x + (self.bg_scroll_x % w) - w
                oy = self.offset_y + (self.bg_scroll_y % h) - h
                for dx in (0, w, 2 * w):
                    for dy in (0, h, 2 * h):
                        self.canvas.create_image(ox + dx, oy + dy, image=img, anchor="nw")
        self._draw_tilemap_layers()
        for cmd in cmds:
            op = cmd[0]
            x = cmd[1]
            y = cmd[2]
            spr = cmd[3]
            angle10 = cmd[4] if len(cmd) > 4 else 0
            scale1000 = cmd[5] if len(cmd) > 5 else 1000
            if op == RENDER_DRAW_SPRITE or op == RENDER_DRAW_SPRITE_XFORM:
                sx = int(x * self.scale + self.offset_x)
                sy = int(y * self.scale + self.offset_y)
                angle = angle10 / 10.0
                scale = max(0.05, (scale1000 / 1000.0))
                if op == RENDER_DRAW_SPRITE_XFORM and PIL_AVAILABLE:
                    img = self._get_transformed_sprite(spr, scale, angle)
                    if img:
                        self.canvas.create_image(sx, sy, image=img, anchor="center")
                        continue
                if scale == 1.0 and 0 <= spr < len(self.sprite_images_scaled) and self.sprite_images_scaled[spr] is not None:
                    self.canvas.create_image(sx, sy, image=self.sprite_images_scaled[spr], anchor="center")
                else:
                    fallback = self._scale_sprite(spr, int(round(scale)))
                    if fallback:
                        self.canvas.create_image(sx, sy, image=fallback, anchor="center")
                    else:
                        c = self.sprite_color(spr)
                        self.canvas.create_rectangle(
                            sx - 6,
                            sy - 6,
                            sx + 6,
                            sy + 6,
                            fill=c,
                            outline=""
                        )
                        self.canvas.create_text(sx, sy - 10, text=str(spr), fill=THEME["text"])
            elif op == RENDER_DRAW_TEXT:
                sx = int(x * self.scale + self.offset_x)
                sy = int(y * self.scale + self.offset_y)
                color = self.sprite_color(spr)
                text = cmd[4] if len(cmd) > 4 else ""
                if text:
                    self.canvas.create_text(sx, sy, text=text, fill=color, anchor="nw")
            elif op == RENDER_DRAW_SHAPE:
                stype = cmd[1] if len(cmd) > 1 else 0
                x1 = cmd[2] if len(cmd) > 2 else 0
                y1 = cmd[3] if len(cmd) > 3 else 0
                x2 = cmd[4] if len(cmd) > 4 else 0
                y2 = cmd[5] if len(cmd) > 5 else 0
                x3 = cmd[6] if len(cmd) > 6 else 0
                y3 = cmd[7] if len(cmd) > 7 else 0
                color = self.sprite_color(cmd[8] if len(cmd) > 8 else 15)
                sx1 = int(x1 * self.scale + self.offset_x)
                sy1 = int(y1 * self.scale + self.offset_y)
                sx2 = int(x2 * self.scale + self.offset_x)
                sy2 = int(y2 * self.scale + self.offset_y)
                sx3 = int(x3 * self.scale + self.offset_x)
                sy3 = int(y3 * self.scale + self.offset_y)
                if stype == 1:
                    self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color)
                elif stype == 2:
                    self.canvas.create_rectangle(sx1, sy1, sx1 + sx2, sy1 + sy2, outline=color)
                elif stype == 3:
                    self.canvas.create_rectangle(sx1, sy1, sx1 + sx2, sy1 + sy2, outline=color, fill=color)
                elif stype == 4:
                    self.canvas.create_polygon(sx1, sy1, sx2, sy2, sx3, sy3, outline=color, fill="")
                elif stype == 5:
                    r = int(x2 * self.scale)
                    self.canvas.create_oval(sx1 - r, sy1 - r, sx1 + r, sy1 + r, outline=color)
        self._mask_outside_viewport()

    def _draw_tilemap_layers(self):
        if not self.tilemaps or not PIL_AVAILABLE:
            return
        if not self.bg_images_pil and self.backgrounds_meta:
            self._load_images_from_meta()
        room_idx = 0
        if self.runtime and self.runtime.room_count > 0:
            room_idx = int(self.runtime.room_index)
        elif self.project:
            try:
                room_idx = int(self.project.get("active_room", 0))
            except Exception:
                room_idx = 0
        rooms = self.project.get("rooms", []) if self.project else []
        if not rooms or room_idx < 0 or room_idx >= len(rooms):
            return
        tm_idx = int(rooms[room_idx].get("tilemap_index", -1))
        if tm_idx < 0 or tm_idx >= len(self.tilemaps):
            return
        tm = self.tilemaps[tm_idx]
        size = int(tm.get("tile_size", 16))
        if size <= 0:
            return
        w = int(tm.get("width", 1))
        h = int(tm.get("height", 1))
        tileset_idx = int(tm.get("tileset_index", -1))
        if tileset_idx < 0 or tileset_idx >= len(self.bg_images_pil):
            return
        tileset = self.bg_images_pil[tileset_idx]
        if tileset is None:
            return
        cols = max(1, tileset.width // size)
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
                    img = self._get_tile_image(tileset_idx, tileset, size, cols, tid)
                    if img is None:
                        continue
                    px = int(self.offset_x + x * size * self.scale)
                    py = int(self.offset_y + y * size * self.scale)
                    self.canvas.create_image(px, py, image=img, anchor="nw")
                    self.canvas_images.append(img)

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

    def _get_tile_image(self, tileset_idx, tileset, size, cols, tile_id):
        key = (tileset_idx, size, tile_id, int(self.scale))
        img = self.tile_cache.get(key)
        if img is not None:
            return img
        idx = tile_id - 1
        tx = idx % cols
        ty = idx // cols
        box = (tx * size, ty * size, tx * size + size, ty * size + size)
        try:
            tile = tileset.crop(box)
            tile = self._apply_magenta_key(tile)
            w = max(1, int(size * self.scale))
            h = max(1, int(size * self.scale))
            tile = tile.resize((w, h), resample=Image.NEAREST)
            img = ImageTk.PhotoImage(tile)
            self.tile_cache[key] = img
            return img
        except Exception:
            return None

    def toggle_demo(self):
        self.demo_mode = not self.demo_mode
        if self.demo_mode and not PIL_AVAILABLE:
            self.status.config(text="Transform test: ON (rotation needs Pillow)")
        else:
            self.status.config(text="Transform test: ON" if self.demo_mode else "Transform test: OFF")

    def _mask_outside_viewport(self):
        vw = ROOM_W * self.scale
        vh = ROOM_H * self.scale
        x0 = self.offset_x
        y0 = self.offset_y
        x1 = x0 + vw
        y1 = y0 + vh
        w = self.canvas_w
        h = self.canvas_h
        if y0 > 0:
            self.canvas.create_rectangle(0, 0, w, y0, fill=THEME["panel"], outline="")
        if x0 > 0:
            self.canvas.create_rectangle(0, y0, x0, y1, fill=THEME["panel"], outline="")
        if x1 < w:
            self.canvas.create_rectangle(x1, y0, w, y1, fill=THEME["panel"], outline="")
        if y1 < h:
            self.canvas.create_rectangle(0, y1, w, h, fill=THEME["panel"], outline="")

    def _update_pil_status(self):
        self.pil_status.config(text="Pillow: OK" if PIL_AVAILABLE else "Pillow: MISSING")

    def toggle_loop(self):
        self.loop_mode = not self.loop_mode
        self.status.config(text="Loop: ON" if self.loop_mode else "Loop: OFF")

    def _get_transformed_sprite(self, frame_id, scale, angle_deg):
        if not PIL_AVAILABLE:
            return None
        if frame_id < 0 or frame_id >= len(self.sprite_pil):
            return None
        base = self.sprite_pil[frame_id]
        if base is None and 0 <= frame_id < len(self.sprite_paths):
            try:
                base = Image.open(self.sprite_paths[frame_id]).convert("RGBA")
                self.sprite_pil[frame_id] = base
            except Exception:
                base = None
        if base is None:
            return None
        ang = int(angle_deg) % 360
        total_scale = max(0.05, scale * self.scale)
        new_w = max(1, int(round(base.width * total_scale)))
        new_h = max(1, int(round(base.height * total_scale)))
        key = (frame_id, new_w, new_h, ang)
        if key in self.sprite_transform_cache:
            return self.sprite_transform_cache[key]
        img = base
        if new_w != base.width or new_h != base.height:
            img = img.resize((new_w, new_h), resample=Image.NEAREST)
        if ang != 0:
            img = img.rotate(-ang, resample=Image.NEAREST, expand=True)
        tk_img = ImageTk.PhotoImage(img)
        self.sprite_transform_cache[key] = tk_img
        return tk_img

    def draw_demo(self, now_ms):
        self.canvas.delete("all")
        if self.bg_image_scaled:
            self.canvas.create_image(self.offset_x, self.offset_y, image=self.bg_image_scaled, anchor="nw")

        t = now_ms / 1000.0
        x = 160 + int(80 * math.sin(t * 1.1))
        y = 100 + int(20 * math.sin(t * 0.7))
        angle = (t * 90.0) % 360.0
        scale = 1 + int(((math.sin(t * 1.5) + 1.0) * 0.5) * 2.0)
        if scale < 1:
            scale = 1
        if scale > 3:
            scale = 3

        # Animate sprite frames if available.
        if self.demo_anim_frames:
            frame_idx = int(now_ms / 120) % len(self.demo_anim_frames)
            spr_id = self.demo_anim_frames[frame_idx]
        else:
            spr_id = 0

        # Draw rotated+scaled sprite if Pillow is available.
        img = self._get_transformed_sprite(spr_id, scale, angle)
        sx = int(x * self.scale + self.offset_x)
        sy = int(y * self.scale + self.offset_y)
        if img:
            self.canvas.create_image(sx, sy, image=img, anchor="center")
        else:
            # Fallback: scaled (no rotation) when Pillow is missing.
            fallback = self._scale_sprite(spr_id, scale)
            if fallback:
                self.canvas.create_image(sx, sy, image=fallback, anchor="center")
            else:
                self.canvas.create_rectangle(sx - 10, sy - 10, sx + 10, sy + 10, outline=THEME["text"])

        # Draw rotated diamond as visual rotation marker.
        r = 20 * scale
        a = math.radians(angle)
        pts = []
        for dx, dy in [(0, -r), (r, 0), (0, r), (-r, 0)]:
            rx = dx * math.cos(a) - dy * math.sin(a)
            ry = dx * math.sin(a) + dy * math.cos(a)
            pts.append((sx + rx, sy + ry))
        self.canvas.create_polygon(pts, outline=THEME["text"], fill="")
        self.canvas.create_text(sx, sy - 28, text=f"rot {int(angle)}°", fill=THEME["text"])

    def sprite_color(self, spr_id: int) -> str:
        palette = [
            "#000000",  # 0 black
            "#1E3A27",  # 1 darkgreen
            "#2F6B3F",  # 2 green
            "#8CAD92",  # 3 lightgreen
            "#2A2A2A",  # 4 darkgray
            "#555555",  # 5 gray
            "#AAAAAA",  # 6 lightgray
            "#FFFFFF",  # 7 white-ish
            "#FFFFFF",  # 8 (alias)
            "#C0392B",  # 9 red
            "#E67E22",  # 10 orange
            "#F1C40F",  # 11 yellow
            "#2980B9",  # 12 blue
            "#1ABC9C",  # 13 cyan
            "#9B59B6",  # 14 magenta
            "#FFFFFF",  # 15 white
        ]
        idx = spr_id % len(palette)
        return palette[idx]

    def tick(self):
        now_ms = int(time.time() * 1000)
        if self.demo_mode:
            self.draw_demo(now_ms)
        elif self.runtime:
            self.runtime.set_input_mask(self._input_mask())
            self._handle_select_room(now_ms)
            cmds = self.runtime.step(now_ms)
            self.bg_scroll_x = int(getattr(self.runtime, "bg_scroll_x", 0))
            self.bg_scroll_y = int(getattr(self.runtime, "bg_scroll_y", 0))
            if cmds:
                self.last_cmds = cmds
            if self.last_cmds:
                self.draw_cmds(self.last_cmds)
            cmd = self.runtime.poll_music_cmd()
            if cmd:
                self._apply_music_cmd(cmd)
            if self.runtime.room_count > 0 and self.runtime.room_index != self.last_room_index:
                self.last_room_index = self.runtime.room_index
                self._apply_room_visuals()
                song_hash = int(self.runtime.room_song_hash)
                if song_hash:
                    self.play_song_by_hash(song_hash)
            if not self.runtime.running and self.loop_mode:
                self.runtime.reset()
        self.after(16, self.tick)

    def _handle_select_room(self, now_ms: int):
        select_now = ("Shift_L" in self.key_down) or ("Shift_R" in self.key_down)
        if select_now and not self.select_down:
            if now_ms - self.last_select_ms > 200:
                self.last_select_ms = now_ms
                if self.runtime and self.runtime.room_count > 0:
                    next_idx = (self.runtime.room_index + 1) % self.runtime.room_count
                    if self.runtime.set_room(next_idx):
                        self._apply_room_visuals()
                else:
                    self._cycle_background()
        self.select_down = select_now

    def _apply_room_visuals(self):
        if not self.runtime:
            return
        self.last_cmds = []
        if self.backgrounds_meta:
            pngs = self.backgrounds_meta.get("pngs", [])
            idx = int(self.runtime.room_bg)
            if pngs and 0 <= idx < len(pngs):
                try:
                    self.bg_image = tk.PhotoImage(file=pngs[idx])
                    self.bg_image_scaled = self._scale_image(self.bg_image)
                except Exception:
                    self.bg_image = None
                    self.bg_image_scaled = None
            else:
                self.bg_image = None
                self.bg_image_scaled = None
        else:
            self.bg_image = None
            self.bg_image_scaled = None
        self.bg_color = int(getattr(self.runtime, "room_bg_color", 12))
        if self.project and self.runtime:
            try:
                self.project["active_room"] = int(self.runtime.room_index)
            except Exception:
                pass
        if self.runtime.room_song_hash:
            self.play_song_by_hash(int(self.runtime.room_song_hash))
        else:
            try:
                self.audio.stop()
            except Exception:
                pass
            self.song_status.config(text="SongHash: none")

    def _apply_music_cmd(self, cmd):
        if not cmd:
            return
        action, song, loop = cmd
        if action == "play":
            self._play_song_index(song, loop)
        elif action == "stop":
            self.audio.stop()
        elif action == "pause":
            self.audio.stop()
        elif action == "loop":
            if self.runtime and self.runtime.music_playing:
                self._play_song_index(song, loop)

    def _play_song_index(self, idx, loop=False):
        idx = int(idx)
        if idx < 0 or idx >= len(self.song_order):
            return
        name = self.song_order[idx]
        song = self.songs_db.get(name)
        if song:
            self.audio.play(name, song, loop=bool(loop))

    def _cycle_background(self):
        if not self.backgrounds_meta:
            return
        pngs = self.backgrounds_meta.get("pngs", [])
        if not pngs:
            return
        idx = 0
        if self.project:
            try:
                idx = int(self.project.get("background_index", 0))
            except Exception:
                idx = 0
            idx = (idx + 1) % len(pngs)
            self.project["background_index"] = idx
        else:
            idx = (idx + 1) % len(pngs)
        try:
            self.bg_image = tk.PhotoImage(file=pngs[idx])
            self.bg_image_scaled = self._scale_image(self.bg_image)
        except Exception:
            self.bg_image = None
            self.bg_image_scaled = None

    def _input_mask(self):
        mask = 0
        if "Up" in self.key_down:
            mask |= INPUT_UP
        if "Down" in self.key_down:
            mask |= INPUT_DOWN
        if "Left" in self.key_down:
            mask |= INPUT_LEFT
        if "Right" in self.key_down:
            mask |= INPUT_RIGHT
        if "z" in self.key_down or "Z" in self.key_down or "space" in self.key_down or "Space" in self.key_down:
            mask |= INPUT_A
        if "x" in self.key_down:
            mask |= INPUT_B
        if "a" in self.key_down:
            mask |= INPUT_X
        if "s" in self.key_down:
            mask |= INPUT_Y
        if "Return" in self.key_down:
            mask |= INPUT_START
        if "Tab" in self.key_down:
            mask |= INPUT_SELECT
        if "q" in self.key_down:
            mask |= INPUT_L
        if "e" in self.key_down:
            mask |= INPUT_R
        return mask

    def on_key_down(self, event):
        self.key_down.add(event.keysym)

    def on_key_up(self, event):
        if event.keysym in self.key_down:
            self.key_down.remove(event.keysym)

    def on_focus_in(self, _event):
        self.key_down.clear()

    def on_focus_out(self, _event):
        self.key_down.clear()

    def _update_audio_status(self):
        if WIN_SOUND_AVAILABLE:
            self.audio_status.config(text="Audio: OK")
        else:
            self.audio_status.config(text="Audio: MISSING")

    def _load_songs(self):
        path = self.song_path
        if not path or not os.path.isfile(path):
            fallback = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gfx", "songs.h"))
            if os.path.isfile(fallback):
                path = fallback
        if not path or not os.path.isfile(path):
            self.song_status.config(text="Songs: 0 (no songs.h)")
            self.song_debug.config(text="")
            return
        try:
            self.songs_db, self.song_order = parse_songs_header(path)
            self.song_hash_map = {}
            for name in self.song_order:
                self.song_hash_map[fnv1a_32(name)] = name
        except Exception:
            self.songs_db = {}
            self.song_order = []
            self.song_hash_map = {}
        self.song_status.config(text=f"Songs: {len(self.song_order)}")
        self.song_debug.config(text=os.path.basename(path))

    def play_song_by_hash(self, song_hash: int):
        try:
            self.audio.stop()
        except Exception:
            pass
        name = self.song_hash_map.get(song_hash)
        if not name:
            fallback = self._project_song_name()
            if fallback and fallback in self.songs_db:
                self.song_status.config(text=f"Song: {fallback} (fallback)")
                self.song_debug.config(text=f"SongHash: {song_hash:08X} (no match)")
                self.audio.play(fallback, self.songs_db.get(fallback), loop=True)
                return
            self.song_status.config(text=f"SongHash: {song_hash:08X} (no match)")
            self.song_debug.config(text="")
            self.audio.stop()
            return
        self.song_status.config(text=f"Song: {name}")
        self.song_debug.config(text=f"SongHash: {song_hash:08X}")
        self.audio.play(name, self.songs_db.get(name), loop=True)

    def on_play_sound(self, song_id: int):
        if song_id < 0 or song_id >= len(self.song_order):
            return
        name = self.song_order[song_id]
        self.audio.play(name, self.songs_db.get(name), loop=False)

    def _project_song_name(self):
        if not self.project:
            return ""
        try:
            active_room = int(self.project.get("active_room", 0))
            rooms = self.project.get("rooms", [])
            if 0 <= active_room < len(rooms):
                return str(rooms[active_room].get("song", "") or "")
        except Exception:
            pass
        return ""


if __name__ == "__main__":
    init_debug_log()
    app = Emulator()
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            app.load_path(p)
    app.mainloop()
