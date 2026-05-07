#include "MasaLoader.h"
#include "MasaFormat.h"

#include <FS.h>
#include <SPIFFS.h>
#include <stdlib.h>

namespace MasaLoader
{
static bool read_exact(File &f, void *dst, size_t len)
{
  // SPIFFS read() puede devolver menos bytes; el loader exige lectura exacta para no correr bytecode corrupto
  return f.read((uint8_t *)dst, len) == (int)len;
}

bool load_from_spiffs(const char *path, GameData &out,
                      uint8_t *scriptBuf, size_t scriptBufSize,
                      uint8_t *roomsBuf, size_t roomsBufSize)
{
  // Ruta conservadora: usa buffers del sketch y valida offsets antes de copiar
  out.valid = false;
  out.entryPoint = 0;
  out.scriptSize = 0;
  out.bgIndex = 0;
  out.songHash = 0;
  out.rooms = NULL;
  out.roomsSize = 0;
  out.script = NULL;

  if(scriptBuf == NULL || scriptBufSize == 0)
    return false;

  File f = SPIFFS.open(path, "r");
  if(!f)
    return false;

  MasaFormat::Header hdr = {};
  if(!read_exact(f, &hdr, sizeof(hdr)))
    return false;

  if(hdr.magic != MasaFormat::kMagic || hdr.version != MasaFormat::kVersion)
    return false;

  if(hdr.scriptSize == 0 || hdr.scriptSize > scriptBufSize)
    return false;

  size_t fileSize = (size_t)f.size();
  if(hdr.scriptOffset + hdr.scriptSize > fileSize)
    return false;

  if(!f.seek(hdr.scriptOffset, SeekSet))
    return false;

  if(!read_exact(f, scriptBuf, hdr.scriptSize))
    return false;

  out.valid = true;
  out.entryPoint = hdr.entryPoint;
  out.scriptSize = hdr.scriptSize;
  out.bgIndex = hdr.reserved;
  out.songHash = hdr.reserved2;
  out.script = scriptBuf;
  out.rooms = NULL;
  out.roomsSize = 0;

  // Rooms are stored in tilemap section
  // En el formato actual la seccion tilemap tambien carga la tabla de rooms
  if(hdr.tilemapSize > 0 && roomsBuf != NULL && roomsBufSize > 0)
  {
    if(hdr.tilemapSize <= roomsBufSize && hdr.tilemapOffset + hdr.tilemapSize <= fileSize)
    {
      if(f.seek(hdr.tilemapOffset, SeekSet))
      {
        if(read_exact(f, roomsBuf, hdr.tilemapSize))
        {
          out.rooms = roomsBuf;
          out.roomsSize = hdr.tilemapSize;
        }
      }
    }
  }
  return true;
}

bool load_from_spiffs_alloc(const char *path, GameData &out)
{
  // Ruta usada por el build principal: baja el .bss reservando script/rooms en heap
  out.valid = false;
  out.entryPoint = 0;
  out.scriptSize = 0;
  out.bgIndex = 0;
  out.songHash = 0;
  out.rooms = NULL;
  out.roomsSize = 0;
  out.script = NULL;

  File f = SPIFFS.open(path, "r");
  if(!f)
    return false;

  MasaFormat::Header hdr = {};
  if(!read_exact(f, &hdr, sizeof(hdr)))
    return false;

  if(hdr.magic != MasaFormat::kMagic || hdr.version != MasaFormat::kVersion)
    return false;

  size_t fileSize = (size_t)f.size();
  if(hdr.scriptSize == 0 || hdr.scriptOffset + hdr.scriptSize > fileSize)
    return false;

  uint8_t *scriptPtr = (uint8_t *)malloc(hdr.scriptSize);
  if(scriptPtr == NULL)
    return false;

  if(!f.seek(hdr.scriptOffset, SeekSet) || !read_exact(f, scriptPtr, hdr.scriptSize))
  {
    free(scriptPtr);
    return false;
  }

  uint8_t *roomsPtr = NULL;
  uint32_t roomsSize = 0;
  if(hdr.tilemapSize > 0 && hdr.tilemapOffset + hdr.tilemapSize <= fileSize)
  {
    roomsPtr = (uint8_t *)malloc(hdr.tilemapSize);
    if(roomsPtr != NULL)
    {
      if(f.seek(hdr.tilemapOffset, SeekSet) && read_exact(f, roomsPtr, hdr.tilemapSize))
      {
        roomsSize = hdr.tilemapSize;
      }
      else
      {
        free(roomsPtr);
        roomsPtr = NULL;
      }
    }
  }

  out.valid = true;
  out.entryPoint = hdr.entryPoint;
  out.scriptSize = hdr.scriptSize;
  out.bgIndex = hdr.reserved;
  out.songHash = hdr.reserved2;
  out.script = scriptPtr;
  out.rooms = roomsPtr;
  out.roomsSize = roomsSize;
  return true;
}

void free_game_data_alloc(GameData &io)
{
  // Limpieza para poder recargar game.masa sin leaks
  if(io.script != NULL)
  {
    free((void *)io.script);
    io.script = NULL;
  }
  if(io.rooms != NULL)
  {
    free((void *)io.rooms);
    io.rooms = NULL;
  }
  io.valid = false;
  io.entryPoint = 0;
  io.scriptSize = 0;
  io.bgIndex = 0;
  io.songHash = 0;
  io.roomsSize = 0;
}
}
