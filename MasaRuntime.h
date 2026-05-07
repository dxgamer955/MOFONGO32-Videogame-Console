#pragma once

#include <Arduino.h>
#include "MasaLoader.h"
#include "MasaFormat.h"

// Runtime de MASA
// Mantiene pools fijos para no depender tanto del heap del ESP32 durante gameplay
// Las cantidades aqui son parte del budget de RAM: subirlas ayuda a juegos grandes,
// pero tambien puede romper builds con Bluepad32 o video compuesto por falta de memoria
namespace MasaRuntime
{
// Limites de runtime. Son pequenos a proposito por RAM y por tamano del paquete SPI
static const int kMaxObjects = 48;
static const int kMaxCommands = 24;
static const int kMaxTextSlots = 5;
static const int kMaxTextLen = 30;
static const int kMaxShapeSlots = 8;
static const int kMaxSignals = 20;
static const int kMaxColliders = 96;
static const int kMaxSignalActions = 48;
static const int kMaxTextBoxes = 1;
static const int kMaxTextBoxLen = 40;
static const int kMaxChoiceSlots = 1;
static const int kMaxChoiceItems = 4;
static const int kMaxChoiceLen = 10;
static const int kMaxInputBinds = 14;
static const int kMaxAlarms = 6;

enum RenderOp : uint8_t
{
  // Comandos que el runtime produce cada frame y que el video board entiende
  RENDER_DRAW_SPRITE = 1,
  RENDER_DRAW_SPRITE_XFORM = 2,
  RENDER_CLEAR = 3,
  RENDER_DRAW_TEXT = 4,
  RENDER_DRAW_SHAPE = 5
};

enum InputMask : uint16_t
{
  INPUT_UP = 1 << 0,
  INPUT_DOWN = 1 << 1,
  INPUT_LEFT = 1 << 2,
  INPUT_RIGHT = 1 << 3,
  INPUT_A = 1 << 4,
  INPUT_B = 1 << 5,
  INPUT_X = 1 << 6,
  INPUT_Y = 1 << 7,
  INPUT_START = 1 << 8,
  INPUT_SELECT = 1 << 9,
  INPUT_L = 1 << 10,
  INPUT_R = 1 << 11,
};

#pragma pack(push, 1)
struct RenderCmd
{
  // Paquete minimo para sprite: posicion, frame, rotacion en decimas y escala x1000
  uint8_t op;
  int16_t x;
  int16_t y;
  uint8_t sprite;
  int16_t angle10;
  uint16_t scale1000;
  uint8_t reserved;
};

struct TextCmd
{
  int16_t x;
  int16_t y;
  uint8_t color;
  uint8_t len;
  char text[kMaxTextLen];
};

enum ShapeType : uint8_t
{
  SHAPE_LINE = 1,
  SHAPE_RECT = 2,
  SHAPE_FILL_RECT = 3,
  SHAPE_TRI = 4,
  SHAPE_CIRCLE = 5
};

struct ShapeCmd
{
  uint8_t type;
  int16_t x1;
  int16_t y1;
  int16_t x2;
  int16_t y2;
  int16_t x3;
  int16_t y3;
  uint8_t color;
};
#pragma pack(pop)

struct CommandQueue
{
  // Cola por frame. Se resetea antes de step() y luego se convierte a MasaSpiLink::Packet
  RenderCmd cmds[kMaxCommands];
  uint8_t count;
  TextCmd texts[kMaxTextSlots];
  uint8_t textCount;
  ShapeCmd shapes[kMaxShapeSlots];
  uint8_t shapeCount;
  int16_t bgScrollX;
  int16_t bgScrollY;

  void reset()
  {
    count = 0;
    textCount = 0;
    shapeCount = 0;
    bgScrollX = 0;
    bgScrollY = 0;
  }

  bool push(uint8_t op, int16_t x, int16_t y, uint8_t sprite, int16_t angle10, uint16_t scale1000)
  {
    if(count >= kMaxCommands)
      return false;
    cmds[count++] = {op, x, y, sprite, angle10, scale1000, 0};
    return true;
  }

  bool push_text(int16_t x, int16_t y, uint8_t color, const char *str, uint8_t len)
  {
    if(textCount >= kMaxTextSlots)
      return false;
    TextCmd &t = texts[textCount++];
    t.x = x;
    t.y = y;
    t.color = color;
    if(len > kMaxTextLen)
      len = kMaxTextLen;
    t.len = len;
    for(uint8_t i = 0; i < len; i++)
      t.text[i] = str[i];
    if(len < kMaxTextLen)
      t.text[len] = '\0';
    return true;
  }

  bool push_shape(uint8_t type, int16_t x1, int16_t y1, int16_t x2, int16_t y2, int16_t x3, int16_t y3, uint8_t color)
  {
    if(shapeCount >= kMaxShapeSlots)
      return false;
    ShapeCmd &s = shapes[shapeCount++];
    s.type = type;
    s.x1 = x1;
    s.y1 = y1;
    s.x2 = x2;
    s.y2 = y2;
    s.x3 = x3;
    s.y3 = y3;
    s.color = color;
    return true;
  }
};

struct ObjectState
{
  // Estado visible/base de cada objeto. El resto de comportamiento vive en pools internos del .cpp
  int16_t x;
  int16_t y;
  uint8_t spriteId;
  bool active;
};

class Runtime
{
  public:
  Runtime();

  // API publica usada por el sketch principal
  void begin(const MasaLoader::GameData &game);
  void reset();
  void step(uint32_t nowMs, CommandQueue &out);
  void set_audio_callback(void (*cb)(uint8_t));
  void set_beep_callback(void (*cb)(uint16_t, uint16_t));
  void set_beep_ex_callback(void (*cb)(uint8_t, uint16_t, uint16_t));
  void set_input_mask(uint16_t mask);
  void set_rooms(const uint8_t *data, uint32_t size);
  bool set_room(uint8_t idx);
  uint8_t room_index() const { return m_roomIndex; }
  uint8_t room_count() const { return m_roomCount; }
  uint8_t room_bg() const { return m_roomBg; }
  uint8_t room_bg_color() const { return m_roomBgColor; }
  uint8_t room_tilemap() const { return m_roomTilemap; }
  uint32_t room_song_hash() const { return m_roomSongHash; }
  struct MusicCmd
  {
    uint8_t type;
    uint8_t song;
    uint8_t loop;
  };
  bool poll_music_cmd(MusicCmd &out);
  bool music_playing() const { return m_musicPlaying; }
  uint8_t music_song() const { return m_musicSong; }
  bool music_loop() const { return m_musicLoop; }
  bool persistent() const
  {
    return m_persistent;
  }

  bool running() const
  {
    return m_running;
  }

  private:
  // Estado del bytecode actual
  const uint8_t *m_script;
  uint32_t m_scriptSize;
  uint32_t m_pc;
  uint32_t m_waitUntil;
  uint32_t m_lastTickMs;
  bool m_running;
  bool m_persistent;
  bool m_boundsEnabled;
  int16_t m_boundsMinX;
  int16_t m_boundsMaxX;
  int16_t m_boundsMinY;
  int16_t m_boundsMaxY;
  bool m_wrapEnabled;
  int16_t m_wrapMinX;
  int16_t m_wrapMaxX;
  int16_t m_wrapMinY;
  int16_t m_wrapMaxY;
  ObjectState m_objects[kMaxObjects];
  // Callbacks hacia AudioApi, el runtime no toca hardware directo
  void (*m_audioCb)(uint8_t);
  void (*m_beepCb)(uint16_t, uint16_t);
  void (*m_beepExCb)(uint8_t, uint16_t, uint16_t);
  const uint8_t *m_rooms;
  // Room metadata actual, leida de la seccion tilemap/rooms del .masa
  uint32_t m_roomsSize;
  uint8_t m_roomCount;
  uint8_t m_roomIndex;
  uint8_t m_roomBg;
  uint8_t m_roomBgColor;
  uint8_t m_roomTilemap;
  uint32_t m_roomSongHash;
  MusicCmd m_musicCmd;
  bool m_musicPlaying;
  bool m_musicLoop;
  uint8_t m_musicSong;
};
}
