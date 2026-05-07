#pragma once

#include <Arduino.h>

namespace DualEspLink
{
// Link SPI viejo/simple para el demo de sprites. MASA usa MasaSpiLink para paquetes mas abundantes
static const uint16_t kMagic = 0xC0DE;
static const uint8_t kVersion = 1;
static const int kMaxObjects = 16;

struct ObjectState
{
  int16_t x;
  int16_t y;
  int16_t angle10;
  uint16_t scale1000;
  uint8_t frame;
  uint8_t mode;
  uint8_t state;
  uint8_t visible;
};

struct FrameState
{
  uint16_t magic;
  uint8_t version;
  uint8_t objectCount;
  uint16_t seq;
  uint8_t bgIndex;
  uint8_t reserved;
  uint16_t checksum;
  ObjectState objects[kMaxObjects];
};

void begin_master(int sclkPin, int misoPin, int mosiPin, int csPin, uint32_t hz = 2000000);
bool send_master(FrameState &state);

void begin_slave(int sclkPin, int misoPin, int mosiPin, int csPin);
bool recv_slave(FrameState &state, uint32_t timeoutMs = 0);
}
