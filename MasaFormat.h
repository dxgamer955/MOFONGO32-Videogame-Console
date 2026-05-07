#pragma once

#include <Arduino.h>

namespace MasaFormat
{
// Firma del archivo .masa: ASCII "MASA" en little-endian
static const uint32_t kMagic = 0x4D415341; // "MASA"
static const uint16_t kVersion = 1;

// Header binario al inicio del .masa. Mantener alineado con el exporter Python
struct Header
{
  uint32_t magic;
  uint16_t version;
  uint16_t flags;
  uint32_t scriptOffset;
  uint32_t scriptSize;
  uint32_t spritesOffset;
  uint32_t spritesSize;
  uint32_t tilemapOffset;
  uint32_t tilemapSize;
  uint32_t entryPoint;
  uint32_t reserved; // bgIndex
  uint32_t reserved2; // song hash
};

enum Op : uint8_t
{
  // Bytecode MASA. Estos numeros son contrato entre tools/game_engine_gui.py y MasaRuntime.cpp
  OP_NOP = 0,
  OP_DRAW_SPRITE = 1,
  OP_DRAW_SPRITE_XFORM = 5,
  OP_SET_OBJECT = 6,
  OP_SET_VEL = 7,
  OP_SET_BOUNDS = 8,
  OP_SET_ROT_SPEED = 9,
  OP_SET_SCALE_PULSE = 10,
  OP_SET_ANIM = 11,
  OP_SET_INPUT = 12,
  OP_TEXT_SET = 13,
  OP_TEXT_CLEAR = 14,
  OP_SHAPE_SET = 15,
  OP_SHAPE_CLEAR = 16,
  OP_SPAWN_OBJECT = 17,
  OP_DESTROY_OBJECT = 18,
  OP_SET_HITBOX = 19,
  OP_COLLIDE_SIGNAL = 20,
  OP_SIGNAL_DESTROY = 21,
  OP_SIGNAL_SPAWN = 22,
  OP_SIGNAL_SOUND = 23,
  OP_TEXTBOX_SET = 24,
  OP_TEXTBOX_CLEAR = 25,
  OP_CHOICES_SET = 26,
  OP_CHOICES_CLEAR = 27,
  OP_SIGNAL_ROOM_NEXT = 28,
  OP_SIGNAL_STOP = 29,
  OP_SIGNAL_TEXTBOX = 30,
  OP_SIGNAL_CHOICES = 31,
  OP_SIGNAL_TEXTBOX_CLEAR = 32,
  OP_SIGNAL_CHOICES_CLEAR = 33,
  OP_SIGNAL_SET_INPUT = 34,
  OP_INPUT_BIND = 35,
  OP_BG_SCROLL_X = 36,
  OP_BG_SCROLL_Y = 37,
  OP_ALARM_START = 38,
  OP_ALARM_STOP = 39,
  OP_ALARM_SIGNAL = 40,
  OP_ALARM_START_OBJ = 83,
  OP_ALARM_STOP_OBJ = 84,
  OP_ALARM_SIGNAL_OBJ = 85,
  OP_SET_ACTION_OWNER = 86,
  OP_SET_NO_WRAP = 87,
  OP_BEEP = 88,
  OP_SIGNAL_BEEP = 89,
  OP_SET_BOUNCE = 90,
  OP_SET_VEL_RANDOM = 91,
  OP_SIGNAL_HUD_ADD = 92,
  OP_SET_GAME_OVER_UI = 93,
  OP_SIGNAL_TEXT_SET = 94,
  OP_SIGNAL_TEXT_CLEAR = 95,
  OP_HUD_STYLE = 96,
  OP_SIGNAL_TEXT_SET_EX = 97,
  OP_SET_HITBOX_EX = 98,
  OP_BEEP_WAVE = 99,
  OP_SIGNAL_BEEP_WAVE = 100,
  OP_MUSIC_SIGNAL = 41,
  OP_PLAY_MUSIC = 42,
  OP_STOP_MUSIC = 43,
  OP_PAUSE_MUSIC = 44,
  OP_SONG_LOOP = 45,
  OP_HUD_SET = 46,
  OP_HUD_ADD = 47,
  OP_HUD_DRAW = 48,
  OP_VAR_SET = 49,
  OP_VAR_ADD = 50,
  OP_VAR_TEXT = 51,
  OP_VARF_SET = 52,
  OP_VARF_ADD = 53,
  OP_VARF_TEXT = 54,
  OP_IF_EQ = 55,
  OP_IF_GT = 56,
  OP_IF_LT = 57,
  OP_IF_EQF = 58,
  OP_IF_GTF = 59,
  OP_IF_LTF = 60,
  OP_VAR_CLAMP = 61,
  OP_VARF_CLAMP = 62,
  OP_VAR_RAND = 63,
  OP_VARF_LERP = 64,
  OP_VAR_MIN = 65,
  OP_VAR_MAX = 66,
  OP_VARF_MIN = 67,
  OP_VARF_MAX = 68,
  OP_VARF_SIN = 69,
  OP_VARF_COS = 70,
  OP_STR_SET = 71,
  OP_STR_TEXT = 72,
  OP_SWITCH = 73,
  OP_SIGNAL_ROOM_GOTO = 74,
  OP_SET_ACCEL = 75,
  OP_SET_ROTATE = 76,
  OP_SET_THRUST = 77,
  OP_SET_WRAP = 78,
  OP_SIGNAL_SPAWN_BULLET = 79,
  OP_SET_SPRITE = 80,
  OP_SET_POS_X = 81,
  OP_SET_POS_Y = 82,
  OP_MOVE_OBJECT = 2,
  OP_PLAY_SOUND = 3,
  OP_WAIT = 4,
  OP_END = 255
};
}
