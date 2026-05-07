#pragma once

#include <Arduino.h>
#include "MasaRuntime.h"

namespace MasaSpiLink
{
// Paquete SPI activo del runtime MASA
// Master/logica envia una foto del frame; slave/video la valida por magic/version/checksum y dibuja
static const uint16_t kMagic = 0x4D53; // "MS"
static const uint8_t kVersion = 7;
static const int kMaxCmds = MasaRuntime::kMaxCommands;

#pragma pack(push, 1)
struct Packet
{
  uint16_t magic;
  uint8_t version;
  uint8_t count;
  uint8_t bgIndex;
  uint8_t bgColor;
  uint8_t tilemapIndex;
  uint8_t flags;
  uint16_t seq;
  uint16_t checksum;
  int16_t bgScrollX;
  int16_t bgScrollY;
  MasaRuntime::RenderCmd cmds[kMaxCmds];
  uint8_t textCount;
  MasaRuntime::TextCmd texts[MasaRuntime::kMaxTextSlots];
  uint8_t shapeCount;
  MasaRuntime::ShapeCmd shapes[MasaRuntime::kMaxShapeSlots];
};
#pragma pack(pop)

void begin_master(int sclkPin, int misoPin, int mosiPin, int csPin, uint32_t hz = 2000000);
bool send_master(const MasaRuntime::CommandQueue &queue, uint8_t bgIndex, uint8_t bgColor, uint8_t flags, uint8_t tilemapIndex);

void begin_slave(int sclkPin, int misoPin, int mosiPin, int csPin);
bool recv_slave(Packet &out, uint32_t timeoutMs = 0);
}
