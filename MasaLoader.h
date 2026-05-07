#pragma once

#include <Arduino.h>

namespace MasaLoader
{
// Limites del loader de buffers fijos. La ruta alloc ignora estos y reserva el tamano exacto
static const size_t kMaxScriptSize = 8192;
static const size_t kMaxRoomsSize = 4096;

// Vista en memoria de un .masa ya cargado
// script apunta al bytecode; rooms apunta a la seccion de rooms/tilemaps cuando existe
struct GameData
{
  bool valid;
  uint32_t entryPoint;
  uint32_t scriptSize;
  uint32_t bgIndex;
  uint32_t songHash;
  const uint8_t *rooms;
  uint32_t roomsSize;
  const uint8_t *script;
};

// Carga usando buffers que entrega el caller. Util cuando se quiere controlar RAM estatica
bool load_from_spiffs(const char *path, GameData &out,
                      uint8_t *scriptBuf, size_t scriptBufSize,
                      uint8_t *roomsBuf, size_t roomsBufSize);

// Dynamic loader: allocates exact-size buffers from heap for script/rooms
// Call free_game_data_alloc() when done or before reloading
bool load_from_spiffs_alloc(const char *path, GameData &out);
void free_game_data_alloc(GameData &io);
}
