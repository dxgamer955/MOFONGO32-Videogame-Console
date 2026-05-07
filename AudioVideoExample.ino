// Base de video por bitluni, adaptada para MOFONGO32.
// Sketch principal: selecciona rol del ESP32, carga MASA, mueve input/audio/video y sincroniza por SPI
//
// Librerias externas usadas:
// - ESP32 Arduino core: SPIFFS, WiFi, Bluetooth, power management y registros SoC.
// - Bluepad32: controles Bluetooth en el ESP32 de logica.
// - ESP32CompositeColorVideo-master: backend de video compuesto NTSC.
//
// Codigo propio del proyecto:
// - MasaLoader/MasaRuntime/MasaSpiLink: carga, interpreta y envia juegos .masa.
// - Graphics/GameApi/BackgroundApi/AudioApi: capa simple estilo GameMaker para dibujar y sonar.
#include "esp_pm.h"
#include <soc/rtc.h>
#include <math.h>
#include <string.h>
#if ENABLE_WEB_CONTROLLER
#include <WiFi.h>
#endif
#include "esp_bt.h"

#include "Graphics.h"
#include <SPIFFS.h>
#define SUPPORT_AUDIO 0
#include "ESP32CompositeColorVideo-master/src/CompositeColorOutput.h"
#include "Font.h"
#include "Sprites.h"
#include "GameApi.h"
#include "AudioApi.h"
#include "BackgroundApi.h"
#include "DualEspLink.h"
#include "MasaFormat.h"
#include "MasaLoader.h"
#include "MasaRuntime.h"
#include "MasaSpiLink.h"
#include "WebInput.h"
#include "gfx/sprites.h"
#include "gfx/my_sprites.h"
#if __has_include("gfx/tilemaps.h")
#include "gfx/tilemaps.h"
#define HAS_TILEMAPS 1
#else
#define HAS_TILEMAPS 0
#endif
#if __has_include("generated/program_logic.h")
#include "generated/program_logic.h"
#define HAS_PROGRAM_LOGIC 1
#else
#define HAS_PROGRAM_LOGIC 0
#endif
#if HAS_PROGRAM_LOGIC
void room_cycle_next();
#endif

// Dual-ESP mode:
// 0 = normal single ESP32
// 1 = divide runtime en dos ESP32 usando SPI
#define USE_DUAL_ESP 1
// Mofongo MASA runtime:
// 1 = carga /game.masa y manda comandos de render por SPI
#define USE_MASA_RUNTIME 1
// When USE_DUAL_ESP=1:
// 1 = este board es Video SPI Slave
// 0 = este board es Logic SPI Master
// En dual mode el audio se puede enrutar al master para liberar el ESP de video
#define DUAL_ESP_ROLE_VIDEO 0
// Route audio to logic/master board in dual mode
#define DUAL_AUDIO_ON_LOGIC 1
// Bluetooth controller input (logic board only)
#define ENABLE_BT_CONTROLLER 1

// Web controller (logic board only)
#define ENABLE_WEB_CONTROLLER 0
// Show BT connection status on overlay (video board)
#define SHOW_BT_STATUS_UI 0

#if ENABLE_BT_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO)
#include <Bluepad32.h>
#endif

#if USE_DUAL_ESP
#if DUAL_AUDIO_ON_LOGIC
#define AUDIO_ON_THIS_ROLE (!DUAL_ESP_ROLE_VIDEO)
#else
#define AUDIO_ON_THIS_ROLE (DUAL_ESP_ROLE_VIDEO)
#endif
#else
#define AUDIO_ON_THIS_ROLE 1
#endif

// never play audio on the video board in dual-ESP mode
#if USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
#undef AUDIO_ON_THIS_ROLE
#define AUDIO_ON_THIS_ROLE 0
#endif
#if __has_include("gfx/rooms.h")
#include "gfx/rooms.h"
#define HAS_ROOMS_ATLAS 1
#else
#define HAS_ROOMS_ATLAS 0
#endif

#if !HAS_PROGRAM_LOGIC
#include "ObjectBehaviors.h"
#include "gfx/rm_test.h"

// Active room aliases (change these when switching to another exported room header)
#define ACTIVE_ROOM_NAME "rm_test"
#define ACTIVE_ROOM_BG_INDEX rm_testBackgroundIndex
#define ACTIVE_ROOM_OBJECTS rm_testObjects
#define ACTIVE_ROOM_OBJECT_COUNT rm_testObjectCount
#endif


namespace font88
{
#include "gfx/font.h"
}
Font font(8, 8, font88::pixels);

// Logical game resolution (keeps room editor coordinates consistent)
const int XRES = 320;
const int YRES = 200;
// Physical framebuffer required by color backend
const int FB_XRES = CompositeColorOutput::XRES;
const int FB_YRES = CompositeColorOutput::YRES;

// Objetos globales de framebuffer y salida compuesta. En el slave de video esto es el corazon del render
Graphics graphics(FB_XRES, FB_YRES);
CompositeColorOutput composite(CompositeColorOutput::NTSC);
const int AUDIO_OUT_PIN = 21; //// prev 26
const int AUDIO_CH = 1;
// Higher PWM carrier helps move switching noise away from visible video bands
const int AUDIO_PWM_FREQ = 156250;
const int SPI_SCLK_PIN = 18;
const int SPI_MISO_PIN = 19;
const int SPI_MOSI_PIN = 23;
const int SPI_CS_PIN = 5;
const uint32_t SPI_LINK_HZ = 4000000; //// prev 2000000
const int SPRITES_A_COUNT = (sizeof(my_spritesOffsets) / sizeof(my_spritesOffsets[0])) - 1;
#if HAS_PROGRAM_LOGIC
const bool ENABLE_ROOM_CYCLE_TEST = true;
const unsigned long ROOM_CYCLE_MS = 3000;
const int ROOM_ACTIVE_MAX = 64;
#endif
#if !HAS_PROGRAM_LOGIC
const int GG_BALL_FRAME = 10;
const int GG_BALL_COUNT = 5;
const bool ROOM_ENABLE_BG_SCROLL = false;
const bool ROOM_ENABLE_GGBALLS = false;
#endif

// Simple once-per-second FPS counter
unsigned long fpsLastMs = 0;
int fpsFrameCounter = 0;
int fpsValue = 0;
#if HAS_PROGRAM_LOGIC
unsigned long roomCycleLastMs = 0;
int roomCycleIndex = 0;
bool roomObjectActive[ROOM_ACTIVE_MAX];
bool roomObjectPersistent[ROOM_ACTIVE_MAX];
#endif

#if USE_DUAL_ESP
// logic envia transforms y video los dibuja
DualEspLink::FrameState gSpiFrameState = {};
bool gSpiHaveFrame = false;
unsigned long gSpiSendLastMs = 0;
const unsigned long SPI_SEND_MS = 16; // ~60 Hz state sync for smoother remote transforms
portMUX_TYPE gSpiMux = portMUX_INITIALIZER_UNLOCKED;
#endif

#if USE_MASA_RUNTIME
// Estado MASA compartido entre loop principal e ISR/tarea SPI. El mutex protege el paquete final
MasaLoader::GameData gMasaGame = {};
MasaRuntime::Runtime gMasaRuntime;
MasaRuntime::CommandQueue gMasaCmdQueue = {};
MasaSpiLink::Packet gMasaPacket = {};
bool gMasaHavePacket = false;
uint8_t gMasaBgIndex = 0;
uint8_t gMasaBgColor = 12;
uint32_t gMasaSongHash = 0;
uint8_t gMasaRoomIndex = 0;
uint8_t gMasaTilemapIndex = 0xFF;
bool gMasaBtConnected = false;
unsigned long gMasaSelectLastMs = 0;
unsigned long gMasaSendLastMs = 0;
const unsigned long MASA_SEND_MS = 16;
portMUX_TYPE gMasaMux = portMUX_INITIALIZER_UNLOCKED;
#endif

#if HAS_TILEMAPS
int gTilemapActive = -1;
#endif

#if USE_MASA_RUNTIME
static void spiffs_list_files()
{
  // Debug rapido para confirmar que /game.masa realmente esta en la particion SPIFFS del ESP32
  File root = SPIFFS.open("/");
  if(!root)
  {
    Serial.println("[Mofongo] SPIFFS list failed");
    return;
  }
  File file = root.openNextFile();
  while(file)
  {
    Serial.print("[Mofongo] SPIFFS file: ");
    Serial.print(file.name());
    Serial.print(" (");
    Serial.print((int)file.size());
    Serial.println(" bytes)");
    file = root.openNextFile();
  }
}

#endif

#if HAS_TILEMAPS
static void draw_tilemap_layer(Graphics &g, const TilemapDef &tm, const unsigned short *layer)
{
  // Tilemaps exportados usan 0xFFFF como tile vacio; el color transparente viene del header generado
  const int kTransparentColor =
#if defined(backgroundsTransparentIndex)
    backgroundsTransparentIndex;
#else
    104; // Fallback for older backgrounds headers
#endif
  const int size = (int)tm.tileSize;
  const int w = (int)tm.width;
  const int h = (int)tm.height;
  if(size <= 0 || w <= 0 || h <= 0)
    return;
  if(tm.tilesetIndex >= backgroundsCount)
    return;
  const int cols = backgroundsWidth / size;
  const int rows = backgroundsHeight / size;
  if(cols <= 0 || rows <= 0)
    return;
  if(layer == NULL)
    return;
  int bgOffset = backgroundsOffsets[tm.tilesetIndex];
  for(int y = 0; y < h; y++)
  {
    for(int x = 0; x < w; x++)
    {
      int tid = layer[y * w + x];
      if(tid <= 0)
        continue;
      int idx = tid - 1;
      int tx = idx % cols;
      int ty = idx / cols;
      if(ty >= rows)
        continue;
      int srcX = tx * size;
      int srcY = ty * size;
      for(int py = 0; py < size; py++)
      {
        int sy = srcY + py;
        int row = (bgOffset + sy * backgroundsWidth);
        for(int px = 0; px < size; px++)
        {
          int sx = srcX + px;
        int color = backgroundsPixels[row + sx];
        if(color != kTransparentColor)
          g.dot(x * size + px, y * size + py, color);
        }
      }
    }
  }
}

static void draw_tilemap_layer_u8(Graphics &g, const TilemapDef &tm, const unsigned char *layer)
{
  const int kTransparentColor =
#if defined(backgroundsTransparentIndex)
    backgroundsTransparentIndex;
#else
    104; // Fallback for older backgrounds headers
#endif
  const int size = (int)tm.tileSize;
  const int w = (int)tm.width;
  const int h = (int)tm.height;
  if(size <= 0 || w <= 0 || h <= 0)
    return;
  if(tm.tilesetIndex >= backgroundsCount)
    return;
  const int cols = backgroundsWidth / size;
  const int rows = backgroundsHeight / size;
  if(cols <= 0 || rows <= 0)
    return;
  if(layer == NULL)
    return;
  int bgOffset = backgroundsOffsets[tm.tilesetIndex];
  for(int y = 0; y < h; y++)
  {
    for(int x = 0; x < w; x++)
    {
      int tid = (int)layer[y * w + x];
      if(tid <= 0)
        continue;
      int idx = tid - 1;
      int tx = idx % cols;
      int ty = idx / cols;
      if(ty >= rows)
        continue;
      int srcX = tx * size;
      int srcY = ty * size;
      for(int py = 0; py < size; py++)
      {
        int sy = srcY + py;
        int row = (bgOffset + sy * backgroundsWidth);
        for(int px = 0; px < size; px++)
        {
          int sx = srcX + px;
        int color = backgroundsPixels[row + sx];
        if(color != kTransparentColor)
          g.dot(x * size + px, y * size + py, color);
        }
      }
    }
  }
}
#endif

#if ENABLE_BT_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO)
GamepadPtr gBtPad = nullptr;
bool gBtSelectPrev = false;
// lock to a specific controller MAC address
// Format: {0x98, 0xB6, 0xE9, 0x36, 0xCE, 0xFF}
static const uint8_t kBtAllowedAddr[6] = {0x98, 0xB6, 0xE9, 0x36, 0xCE, 0xFF};
static const bool kBtRestrictToAddr = false;
// If true, clears stored pairings on boot
static const bool kBtForgetKeysOnBoot = true;

static bool bt_addr_matches(const uint8_t *addr)
{
  if(!kBtRestrictToAddr)
    return true;
  bool match = true;
  for(int i = 0; i < 6; i++)
  {
    if(addr[i] != kBtAllowedAddr[i])
    {
      match = false;
      break;
    }
  }
  if(match)
    return true;
  // Also accept reversed byte order just in case
  for(int i = 0; i < 6; i++)
  {
    if(addr[i] != kBtAllowedAddr[5 - i])
      return false;
  }
  return true;
}

static void bt_print_addr(const uint8_t *addr)
{
  for(int i = 0; i < 6; i++)
  {
    if(i) Serial.print(":");
    if(addr[i] < 0x10) Serial.print("0");
    Serial.print(addr[i], HEX);
  }
}

static void bt_on_connected(GamepadPtr gp)
{
  ControllerProperties props = gp->getProperties();
  Serial.print("[Mofongo] BT pad connected, addr=");
  bt_print_addr(props.btaddr);
  Serial.println();

  if(!bt_addr_matches(props.btaddr))
  {
    Serial.println("[Mofongo] BT pad rejected (not allowed)");
    gp->disconnect();
    return;
  }

  gBtPad = gp;
  Serial.println("[Mofongo] BT pad accepted");
}

static void bt_on_disconnected(GamepadPtr gp)
{
  if(gBtPad == gp)
    gBtPad = nullptr;
  Serial.println("[Mofongo] BT pad disconnected");
}

static uint16_t bt_input_mask()
{
  if(!gBtPad || !gBtPad->isConnected())
    return 0;

  uint16_t mask = 0;
  const int axisDead = 200;
  const bool axisYNegativeIsUp = false;
  int lx = gBtPad->axisX();
  int ly = gBtPad->axisY();
  int rx = gBtPad->axisRX();
  int ry = gBtPad->axisRY();
  uint8_t dpad = gBtPad->dpad();

  if(dpad & DPAD_UP) mask |= MasaRuntime::INPUT_UP;
  if(dpad & DPAD_DOWN) mask |= MasaRuntime::INPUT_DOWN;
  if(dpad & DPAD_LEFT) mask |= MasaRuntime::INPUT_LEFT;
  if(dpad & DPAD_RIGHT) mask |= MasaRuntime::INPUT_RIGHT;

  int h = 0;
  if(abs(lx) > axisDead)
    h = lx;
  else if(abs(rx) > axisDead)
    h = rx;
  if(h < -axisDead) mask |= MasaRuntime::INPUT_LEFT;
  if(h > axisDead) mask |= MasaRuntime::INPUT_RIGHT;

  int v = 0;
  if(abs(ly) > axisDead)
    v = ly;
  else if(abs(ry) > axisDead)
    v = ry;
  bool vUp = axisYNegativeIsUp ? (v < -axisDead) : (v > axisDead);
  bool vDown = axisYNegativeIsUp ? (v > axisDead) : (v < -axisDead);
  // Some gamepads report inverted Y or mixed axis conventions
  // For gameplay (thrust), treat any strong vertical stick push as UP
  if(vUp || vDown) mask |= MasaRuntime::INPUT_UP;
  if(gBtPad->a()) mask |= MasaRuntime::INPUT_A;
  if(gBtPad->b()) mask |= MasaRuntime::INPUT_B;
  if(gBtPad->x()) mask |= MasaRuntime::INPUT_X;
  if(gBtPad->y()) mask |= MasaRuntime::INPUT_Y;
  if(gBtPad->l1()) mask |= MasaRuntime::INPUT_L;
  if(gBtPad->r1()) mask |= MasaRuntime::INPUT_R;
  if(gBtPad->miscStart()) mask |= MasaRuntime::INPUT_START;
  if(gBtPad->miscSelect()) mask |= MasaRuntime::INPUT_SELECT;

  return mask;
}
#endif

#if USE_MASA_RUNTIME
static uint8_t masa_link_flags()
{
  uint8_t flags = 0;
#if ENABLE_BT_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO)
  if(gBtPad && gBtPad->isConnected())
    flags |= 0x01;
#endif
  return flags;
}
#endif

void fps_update()
{
  unsigned long now = millis();
  fpsFrameCounter++;
  if(now - fpsLastMs >= 1000)
  {
    fpsValue = fpsFrameCounter;
    fpsFrameCounter = 0;
    fpsLastMs = now;
  }
}

#if USE_DUAL_ESP
void spi_pack_logic_state()
{
#if HAS_PROGRAM_LOGIC
  DualEspLink::FrameState &p = gSpiFrameState;
  p.seq++;
  int bg = BackgroundApi::current_image();
  if(bg < 0)
    bg = 0;
  p.bgIndex = (uint8_t)bg;

  int n = ProgramLogic::program_logic_object_count();
  if(n > DualEspLink::kMaxObjects)
    n = DualEspLink::kMaxObjects;
  p.objectCount = (uint8_t)n;

  for(int i = 0; i < n; i++)
  {
    ProgramLogic::ProgramObject &o = ProgramLogic::objects[i];
    bool isVisible = o.inst.visible;
#if HAS_PROGRAM_LOGIC
    if(i < ROOM_ACTIVE_MAX && !roomObjectActive[i])
      isVisible = false;
#endif
    int frame = 0;
    if(o.inst.clip != NULL && o.inst.clip->frameCount > 0 && o.inst.frameIndex >= 0 && o.inst.frameIndex < o.inst.clip->frameCount)
      frame = o.inst.clip->frames[o.inst.frameIndex];

    p.objects[i].x = (int16_t)o.inst.x;
    p.objects[i].y = (int16_t)o.inst.y;
    p.objects[i].angle10 = (int16_t)(o.angle * 10.0f);
    p.objects[i].scale1000 = (uint16_t)(o.scale * 1000.0f);
    p.objects[i].frame = (uint8_t)frame;
    p.objects[i].mode = (uint8_t)o.drawMode;
    p.objects[i].state = (uint8_t)o.state;
    p.objects[i].visible = isVisible ? 1 : 0;
  }
#else
  gSpiFrameState.objectCount = 0;
#endif
}

void spi_send_logic_state()
{
  unsigned long now = millis();
  if(now - gSpiSendLastMs < SPI_SEND_MS)
    return;
  gSpiSendLastMs = now;
  spi_pack_logic_state();
  DualEspLink::send_master(gSpiFrameState);
}

void spi_recv_video_state()
{
  DualEspLink::FrameState tmp = {};
  if(!DualEspLink::recv_slave(tmp, 1000))
    return;

  portENTER_CRITICAL(&gSpiMux);
  gSpiFrameState = tmp;
  gSpiHaveFrame = true;
  portEXIT_CRITICAL(&gSpiMux);

  if(BackgroundApi::image_count() > 0)
  {
    int bg = (int)gSpiFrameState.bgIndex;
    if(bg < 0 || bg >= BackgroundApi::image_count())
      bg = 0;
    BackgroundApi::set_image(bg);
  }
}

void spi_video_rx_task(void *param)
{
  while(true)
    spi_recv_video_state();
}
#endif

#if USE_MASA_RUNTIME
void masa_audio_cb(uint8_t songId)
{
#if AUDIO_ON_THIS_ROLE
  if(songId < songsCount)
    AudioApi::play_sound(songs[songId], false);
#else
  (void)songId;
#endif
}

void masa_beep_cb(uint16_t hz, uint16_t durationMs)
{
#if AUDIO_ON_THIS_ROLE
  AudioApi::beep_hz((int)hz, (int)durationMs);
#else
  (void)hz;
  (void)durationMs;
#endif
}

void masa_beep_ex_cb(uint8_t wave, uint16_t hz, uint16_t durationMs)
{
#if AUDIO_ON_THIS_ROLE
  AudioApi::beep_wave_hz(wave, (int)hz, (int)durationMs);
#else
  (void)wave;
  (void)hz;
  (void)durationMs;
#endif
}

void masa_apply_music_cmds()
{
#if AUDIO_ON_THIS_ROLE
  MasaRuntime::Runtime::MusicCmd cmd = {};
  while(gMasaRuntime.poll_music_cmd(cmd))
  {
    if(cmd.type == 1)
    {
      if(cmd.song < songsCount)
        AudioApi::play_sound(songs[cmd.song], cmd.loop != 0);
    }
    else if(cmd.type == 2)
    {
      if(cmd.song < songsCount)
        AudioApi::stop_sound(songs[cmd.song]);
    }
    else if(cmd.type == 3)
    {
      if(cmd.song < songsCount)
        AudioApi::pause_sound(songs[cmd.song]);
    }
    else if(cmd.type == 4)
    {
      if(gMasaRuntime.music_playing() && cmd.song < songsCount)
        AudioApi::play_sound(songs[cmd.song], cmd.loop != 0);
    }
  }
#endif
}

void masa_send_logic_state()
{
  unsigned long now = millis();
  if(now - gMasaSendLastMs < MASA_SEND_MS)
    return;
  gMasaSendLastMs = now;
  MasaSpiLink::send_master(gMasaCmdQueue, gMasaBgIndex, gMasaBgColor, masa_link_flags(), gMasaTilemapIndex);
  gMasaCmdQueue.reset();
}

void masa_recv_video_state()
{
  MasaSpiLink::Packet tmp = {};
  if(!MasaSpiLink::recv_slave(tmp, 1000))
    return;

  portENTER_CRITICAL(&gMasaMux);
  gMasaPacket = tmp;
  gMasaHavePacket = true;
  gMasaBtConnected = (tmp.flags & 0x01) != 0;
  portEXIT_CRITICAL(&gMasaMux);

  if(BackgroundApi::image_count() > 0 && gMasaPacket.bgIndex != 0xFF)
  {
    int bg = (int)gMasaPacket.bgIndex;
    if(bg < 0 || bg >= BackgroundApi::image_count())
      bg = 0;
    BackgroundApi::set_image(bg);
    BackgroundApi::clear_color();
  }
  else
  {
    BackgroundApi::clear_image();
    BackgroundApi::set_color((int)gMasaPacket.bgColor);
  }
#if HAS_TILEMAPS
  if(gMasaPacket.tilemapIndex != 0xFF && gMasaPacket.tilemapIndex < tilemapsCount)
    gTilemapActive = (int)gMasaPacket.tilemapIndex;
  else
    gTilemapActive = -1;
#endif
}

void masa_video_rx_task(void *param)
{
  while(true)
    masa_recv_video_state();
}
#endif

#if HAS_PROGRAM_LOGIC
#if HAS_ROOMS_ATLAS
const int kRoomCycleCount = roomsAtlasCount;
#else
struct RoomCyclePose
{
  int x;
  int y;
  int state;   // 0 idle, 1 walk, 2 run, 3 jump
  int mode;    // 0 normal, 1 rotated, 2 scaled
  float angle;
  float scale;
};

struct RoomCycleDef
{
  int bgIndex;
  RoomCyclePose pose[3];
};

const RoomCycleDef kRoomCycleDefs[] = {
  {1, {{70, 136, 1, 0, 0.0f, 1.0f}, {236, 132, 0, 0, 0.0f, 1.0f}, {39, 32, 0, 0, 0.0f, 1.0f}}},
  {0, {{110, 136, 2, 0, 0.0f, 1.0f}, {180, 118, 0, 1, 30.0f, 1.0f}, {272, 40, 0, 2, 0.0f, 1.5f}}},
  {1, {{38, 150, 1, 0, 0.0f, 1.0f}, {286, 150, 0, 0, 0.0f, 1.0f}, {160, 76, 0, 2, 0.0f, 2.0f}}},
};
const int kRoomCycleCount = sizeof(kRoomCycleDefs) / sizeof(kRoomCycleDefs[0]);
#endif

void apply_room_cycle(int idx)
{
  if(kRoomCycleCount <= 0)
    return;
  int roomIdx = idx % kRoomCycleCount;
  if(roomIdx < 0)
    roomIdx += kRoomCycleCount;

  // Reset visibility every room switch so only active-room objects are shown
  int nAll = ProgramLogic::program_logic_object_count();
  for(int i = 0; i < nAll; i++)
  {
    bool keep = (i < ROOM_ACTIVE_MAX && roomObjectPersistent[i]);
    if(!keep)
    {
      ProgramLogic::objects[i].inst.visible = false;
      if(i < ROOM_ACTIVE_MAX)
        roomObjectActive[i] = false;
    }
  }

#if HAS_ROOMS_ATLAS
  const RoomsAtlasRoom &r = roomsAtlas[roomIdx];
  if(BackgroundApi::image_count() > 0)
  {
    int bg = r.background_index;
    if(bg < 0 || bg >= BackgroundApi::image_count())
      bg = 0;
    BackgroundApi::set_image(bg);
  }

  int n = ProgramLogic::program_logic_object_count();

#if defined(ROOMS_ATLAS_V2)
  for(int i = 0; i < r.object_count; i++)
  {
    const RoomsAtlasObject &ro = r.objects[i];
    int dst = -1;
    for(int j = 0; j < n; j++)
    {
      if(ProgramLogic::objects[j].name && ro.name && strcmp(ProgramLogic::objects[j].name, ro.name) == 0)
      {
        dst = j;
        break;
      }
    }
    if(dst < 0 && i < n)
      dst = i;
    if(dst < 0 || dst >= n)
      continue;

    ProgramLogic::ProgramObject &o = ProgramLogic::objects[dst];
    o.inst.x = ro.x;
    o.inst.y = ro.y;
    o.drawMode = ro.mode;
    o.angle = ro.angle;
    o.scale = ro.scale;
    o.inst.visible = true;
    if(dst < ROOM_ACTIVE_MAX)
    {
      roomObjectActive[dst] = true;
    }
    ProgramLogic::set_state(o, ro.state);
  }
#else
  int legacyN = n;
  if(legacyN > r.object_count)
    legacyN = r.object_count;
  for(int i = 0; i < legacyN; i++)
  {
    ProgramLogic::ProgramObject &o = ProgramLogic::objects[i];
    const RoomsAtlasObject &ro = r.objects[i];
    o.inst.x = ro.x;
    o.inst.y = ro.y;
    o.drawMode = ro.mode;
    o.angle = ro.angle;
    o.scale = ro.scale;
    o.inst.visible = true;
    if(i < ROOM_ACTIVE_MAX)
    {
      roomObjectActive[i] = true;
    }
  }
#endif

#if defined(ROOMS_ATLAS_V3)
  if(r.song && r.song[0] != '\0')
  {
    const char *curSong = AudioApi::current_song_name();
    if(curSong == NULL || strcmp(curSong, r.song) != 0)
    {
      const SongDef *roomSong = AudioApi::get_sound(r.song);
      if(roomSong != NULL)
        AudioApi::play_sound(*roomSong, true);
    }
  }
#endif
#else
  const RoomCycleDef &r = kRoomCycleDefs[roomIdx];

  if(BackgroundApi::image_count() > 0)
  {
    int bg = r.bgIndex;
    if(bg < 0 || bg >= BackgroundApi::image_count())
      bg = 0;
    BackgroundApi::set_image(bg);
  }

  int n = ProgramLogic::program_logic_object_count();
  if(n > 3)
    n = 3;
  for(int i = 0; i < n; i++)
  {
    ProgramLogic::ProgramObject &o = ProgramLogic::objects[i];
    o.inst.x = r.pose[i].x;
    o.inst.y = r.pose[i].y;
    o.drawMode = r.pose[i].mode;
    o.angle = r.pose[i].angle;
    o.scale = r.pose[i].scale;
    o.inst.visible = true;
    if(i < ROOM_ACTIVE_MAX)
      roomObjectActive[i] = true;
    ProgramLogic::set_state(o, r.pose[i].state);
  }
#endif
}

void room_cycle_next()
{
  if(kRoomCycleCount <= 0)
    return;
  roomCycleIndex = (roomCycleIndex + 1) % kRoomCycleCount;
  apply_room_cycle(roomCycleIndex);
  roomCycleLastMs = millis();
}
#endif

// Mini web server disabled to avoid RF interference on composite output
// #include <WebServer.h>
// WebServer remoteServer(80);

#if !HAS_PROGRAM_LOGIC
// Bouncing ball runtime state for fallback room mode
float ggBallX[GG_BALL_COUNT];
float ggBallY[GG_BALL_COUNT];
float ggBallVx[GG_BALL_COUNT];
float ggBallVy[GG_BALL_COUNT];

void init_ggballs()
{
  // Skip if the atlas does not contain p_ggball
  if(SPRITES_A_COUNT <= GG_BALL_FRAME)
    return;

  // Randomize initial positions and velocities
  randomSeed((unsigned long)micros());
  int halfW = my_sprites.xres(GG_BALL_FRAME) / 2;
  int halfH = my_sprites.yres(GG_BALL_FRAME) / 2;
  int minX = halfW;
  int maxX = XRES - halfW;
  int minY = halfH;
  int maxY = YRES - halfH;

  for(int i = 0; i < GG_BALL_COUNT; i++)
  {
    ggBallX[i] = (float)random(minX, maxX);
    ggBallY[i] = (float)random(minY, maxY);
    ggBallVx[i] = (random(0, 2) == 0 ? -1.0f : 1.0f) * (0.7f + (float)random(0, 170) / 100.0f);
    ggBallVy[i] = (random(0, 2) == 0 ? -1.0f : 1.0f) * (0.7f + (float)random(0, 170) / 100.0f);
  }
}

void update_draw_ggballs()
{
  // Skip if the atlas does not contain p_ggball
  if(SPRITES_A_COUNT <= GG_BALL_FRAME)
    return;

  int halfW = my_sprites.xres(GG_BALL_FRAME) / 2;
  int halfH = my_sprites.yres(GG_BALL_FRAME) / 2;
  int minX = halfW;
  int maxX = XRES - halfW;
  int minY = halfH;
  int maxY = YRES - halfH;

  for(int i = 0; i < GG_BALL_COUNT; i++)
  {
    // Integrate velocity
    ggBallX[i] += ggBallVx[i];
    ggBallY[i] += ggBallVy[i];

    // Bounce on screen bounds
    if(ggBallX[i] <= minX)
    {
      ggBallX[i] = (float)minX;
      ggBallVx[i] = fabsf(ggBallVx[i]);
    }
    else if(ggBallX[i] >= maxX)
    {
      ggBallX[i] = (float)maxX;
      ggBallVx[i] = -fabsf(ggBallVx[i]);
    }

    if(ggBallY[i] <= minY)
    {
      ggBallY[i] = (float)minY;
      ggBallVy[i] = fabsf(ggBallVy[i]);
    }
    else if(ggBallY[i] >= maxY)
    {
      ggBallY[i] = (float)maxY;
      ggBallVy[i] = -fabsf(ggBallVy[i]);
    }

    // Draw centered so the sprite pivot behaves correctly
    draw_sprite_center(graphics, my_sprites, (int)ggBallX[i], (int)ggBallY[i], GG_BALL_FRAME);
  }
}
#endif

// Layer 1: background
void draw_layer_background()
{
#if USE_MASA_RUNTIME && USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
  if(gMasaPacket.bgScrollX != 0 || gMasaPacket.bgScrollY != 0)
    BackgroundApi::add_scroll((int)gMasaPacket.bgScrollX, (int)gMasaPacket.bgScrollY);
#endif
  BackgroundApi::draw(graphics, millis());
#if HAS_TILEMAPS
  if(gTilemapActive >= 0 && gTilemapActive < (int)tilemapsCount)
    draw_tilemap_layer(graphics, tilemaps[gTilemapActive], tilemaps[gTilemapActive].back);
  if(gTilemapActive >= 0 && gTilemapActive < (int)tilemapsCount)
    draw_tilemap_layer(graphics, tilemaps[gTilemapActive], tilemaps[gTilemapActive].mid);
#endif
}

// Layer 2: gameplay sprites and effects
void draw_layer_sprites()
{
  unsigned long now = millis();
#if USE_MASA_RUNTIME && USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
  MasaSpiLink::Packet snap = {};
  bool have = false;
  portENTER_CRITICAL(&gMasaMux);
  have = gMasaHavePacket;
  if(have)
    snap = gMasaPacket;
  portEXIT_CRITICAL(&gMasaMux);
  if(!have)
    return;

  int n = (int)snap.count;
  if(n > MasaSpiLink::kMaxCmds)
    n = MasaSpiLink::kMaxCmds;
  for(int i = 0; i < n; i++)
  {
    const MasaRuntime::RenderCmd &cmd = snap.cmds[i];
    if(cmd.op == MasaRuntime::RENDER_DRAW_SPRITE || cmd.op == MasaRuntime::RENDER_DRAW_SPRITE_XFORM)
    {
      int frame = (int)cmd.sprite;
      if(frame < 0 || frame >= SPRITES_A_COUNT)
        continue;
        if(cmd.op == MasaRuntime::RENDER_DRAW_SPRITE_XFORM)
        {
          float angle = ((float)cmd.angle10) * 0.1f;
          float scale = ((float)cmd.scale1000) * 0.001f;
          bool hasAngle = fabsf(angle) > 0.001f;
          bool hasScale = fabsf(scale - 1.0f) > 0.001f;
          if(hasAngle && hasScale)
            draw_sprite_rotated_scaled_center(graphics, my_sprites, (int)cmd.x, (int)cmd.y, frame, angle, scale);
          else if(hasAngle)
            draw_sprite_rotated_center(graphics, my_sprites, (int)cmd.x, (int)cmd.y, frame, angle);
          else if(hasScale)
            draw_sprite_scaled_center(graphics, my_sprites, (int)cmd.x, (int)cmd.y, frame, scale);
          else
            draw_sprite_center(graphics, my_sprites, (int)cmd.x, (int)cmd.y, frame);
        }
      else
      {
        draw_sprite_center(graphics, my_sprites, (int)cmd.x, (int)cmd.y, frame);
      }
    }
  }
  return;
#endif
#if !USE_MASA_RUNTIME
#if HAS_PROGRAM_LOGIC
#if USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
  DualEspLink::FrameState snap = {};
  bool have = false;
  portENTER_CRITICAL(&gSpiMux);
  have = gSpiHaveFrame;
  if(have)
    snap = gSpiFrameState;
  portEXIT_CRITICAL(&gSpiMux);
  if(!have)
    return;
  int n = (int)snap.objectCount;
  if(n > DualEspLink::kMaxObjects)
    n = DualEspLink::kMaxObjects;
  for(int i = 0; i < n; i++)
  {
    const DualEspLink::ObjectState &o = snap.objects[i];
    if(!o.visible)
      continue;
    int frame = (int)o.frame;
    if(frame < 0 || frame >= SPRITES_A_COUNT)
      continue;
    float angle = ((float)o.angle10) * 0.1f;
    float scale = ((float)o.scale1000) * 0.001f;
    if(o.mode == 1)
      draw_sprite_rotated_center(graphics, my_sprites, (int)o.x, (int)o.y, frame, angle);
    else if(o.mode == 2)
      draw_sprite_scaled_center(graphics, my_sprites, (int)o.x, (int)o.y, frame, scale);
    else
      draw_sprite_center(graphics, my_sprites, (int)o.x, (int)o.y, frame);
  }
#else
  ProgramLogic::program_logic_update(now);
  // Keep non-room objects hidden even if scripts try to re-enable them
  int n = ProgramLogic::program_logic_object_count();
  if(n > ROOM_ACTIVE_MAX)
    n = ROOM_ACTIVE_MAX;
  for(int i = 0; i < n; i++)
  {
    if(!roomObjectActive[i])
      ProgramLogic::objects[i].inst.visible = false;
  }
  ProgramLogic::program_logic_draw(graphics);
#endif
#else
  // Draw objects from exported room data
  for(int i = 0; i < ACTIVE_ROOM_OBJECT_COUNT; i++)
  {
    const RoomObjectDef &o = ACTIVE_ROOM_OBJECTS[i];
    ObjectRenderState s = {
      .frame = o.frame,
      .mode = o.mode,
      .x = o.x,
      .y = o.y,
      .angle = o.angle,
      .scale = o.scale,
      .visible = true,
    };
    apply_object_behavior(i, now, s);

    if(!s.visible)
      continue;
    if(s.frame < 0 || s.frame >= SPRITES_A_COUNT)
      continue;

    if(s.mode == 1)
    {
      draw_sprite_rotated_center(graphics, my_sprites, s.x, s.y, s.frame, s.angle);
    }
    else if(s.mode == 2)
    {
      draw_sprite_scaled_center(graphics, my_sprites, s.x, s.y, s.frame, s.scale);
    }
    else
    {
      draw_sprite_center(graphics, my_sprites, s.x, s.y, s.frame);
    }
  }

  // Optional effect layer for manual testing
  if(ROOM_ENABLE_GGBALLS)
    update_draw_ggballs();
#endif
#endif
}

// Layer 3: debug/UI overlay
void draw_layer_ui()
{
  #if USE_MASA_RUNTIME && USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
    if(!gMasaHavePacket)
    {
      auto draw_center_text = [&](int y, const char *text)
      {
        int len = (int)strlen(text);
        int x = (XRES - (len * 8)) / 2;
        if(x < 0) x = 0;
        graphics.setCursor(x, y);
        graphics.print(text);
      };

      graphics.fillRect(0, 0, XRES, YRES, 20);
      int boxW = 252;
      int boxH = 78;
      int boxX = (XRES - boxW) / 2;
      int boxY = (YRES - boxH) / 2;
      graphics.fillRect(boxX, boxY, boxW, boxH, 10);
      graphics.rect(boxX, boxY, boxW, boxH, 15);
      graphics.rect(boxX + 2, boxY + 2, boxW - 4, boxH - 4, 14);
      graphics.setTextColor(15);
      draw_center_text(boxY + 12, "*** MOFONGO32 .MASA LOADER ***");

      unsigned long tick = millis() / 400;
      int dots = (int)(tick % 4);
      char msg[32] = "WAITING FOR THE FOOD";
      int baseLen = (int)strlen(msg);
      for(int i = 0; i < dots; i++)
        msg[baseLen + i] = '.';
      msg[baseLen + dots] = '\0';
      draw_center_text(boxY + 40, msg);
      return;
    }
  #endif
#if USE_MASA_RUNTIME && USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
  if(gMasaHavePacket)
  {
    if(gMasaPacket.shapeCount > 0)
    {
      for(uint8_t i = 0; i < gMasaPacket.shapeCount; i++)
      {
        const MasaRuntime::ShapeCmd &s = gMasaPacket.shapes[i];
        int color = s.color & 0x0F;
        switch(s.type)
        {
          case MasaRuntime::SHAPE_LINE:
            graphics.line(s.x1, s.y1, s.x2, s.y2, color);
            break;
          case MasaRuntime::SHAPE_RECT:
            graphics.rect(s.x1, s.y1, s.x2, s.y2, color);
            break;
          case MasaRuntime::SHAPE_FILL_RECT:
            graphics.fillRect(s.x1, s.y1, s.x2, s.y2, color);
            break;
          case MasaRuntime::SHAPE_TRI:
          {
            short v0[2] = {s.x1, s.y1};
            short v1[2] = {s.x2, s.y2};
            short v2[2] = {s.x3, s.y3};
            graphics.triangle(v0, v1, v2, color);
            break;
          }
          case MasaRuntime::SHAPE_CIRCLE:
            graphics.circle(s.x1, s.y1, s.x2, color);
            break;
          default:
            break;
        }
      }
    }
    if(gMasaPacket.textCount > 0)
    {
      char txtBuf[MasaRuntime::kMaxTextLen + 1];
      for(uint8_t i = 0; i < gMasaPacket.textCount; i++)
      {
        const MasaRuntime::TextCmd &t = gMasaPacket.texts[i];
        uint8_t len = t.len;
        if(len > MasaRuntime::kMaxTextLen)
          len = MasaRuntime::kMaxTextLen;
        if(len == 0)
          continue;
        for(uint8_t j = 0; j < len; j++)
          txtBuf[j] = t.text[j];
        txtBuf[len] = '\0';
        graphics.setTextColor(t.color & 0x0F);
        graphics.setCursor(t.x, t.y);
        graphics.print(txtBuf);
      }
    }
  }
#endif
  return;
}

void setup()
{
  Serial.begin(115200);
  delay(100);
  Serial.println();
  Serial.println("[Mofongo] boot");

  // Lock CPU at max frequency for stable composite timing
  esp_pm_lock_handle_t powerManagementLock = NULL;
  if(esp_pm_lock_create(ESP_PM_CPU_FREQ_MAX, 0, "compositeCorePerformanceLock", &powerManagementLock) == ESP_OK && powerManagementLock != NULL)
    esp_pm_lock_acquire(powerManagementLock);
  #if defined(ARDUINO_ARCH_ESP32)
  setCpuFrequencyMhz(240);
  #else
  rtc_clk_cpu_freq_set(RTC_CPU_FREQ_240M);
  #endif

  // Disable radio features to reduce interference on composite output
#if ENABLE_WEB_CONTROLLER
  WiFi.mode(WIFI_OFF);
#endif
#if !(ENABLE_BT_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO))
  btStop();
#endif

  // Initialize core APIs shared by logic/video roles
  BackgroundApi::init(XRES, YRES);

#if !(USE_DUAL_ESP && !DUAL_ESP_ROLE_VIDEO)
  // Video role (single-ESP or dual-ESP video board)
  composite.init();
  Graphics::setColorModeAtari(true);
  Graphics::setLegacyGrayMapping(false);
  Graphics::setGlobalHue(0);
  Graphics::setDrawOffset((FB_XRES - XRES) / 2, (FB_YRES - YRES) / 2);
  // Speed up heavy sprite transforms on video board
  set_transform_step(0);
  graphics.init();
  graphics.setFont(font);
#endif

#if AUDIO_ON_THIS_ROLE
  AudioApi::init(AUDIO_OUT_PIN, AUDIO_CH, AUDIO_PWM_FREQ);
#endif

#if USE_DUAL_ESP
#if USE_MASA_RUNTIME
#if DUAL_ESP_ROLE_VIDEO
  MasaSpiLink::begin_slave(SPI_SCLK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN, SPI_CS_PIN);
  xTaskCreatePinnedToCore(masa_video_rx_task, "masaVideoRx", 4096, NULL, 2, NULL, 0);
  Serial.println("[Mofongo] role=video, spi=slave");
#else
  MasaSpiLink::begin_master(SPI_SCLK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN, SPI_CS_PIN, SPI_LINK_HZ);
  Serial.println("[Mofongo] role=logic, spi=master");
#endif
#else
#if DUAL_ESP_ROLE_VIDEO
  DualEspLink::begin_slave(SPI_SCLK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN, SPI_CS_PIN);
  xTaskCreatePinnedToCore(spi_video_rx_task, "spiVideoRx", 4096, NULL, 2, NULL, 0);
  Serial.println("[Mofongo] role=video, spi=slave (legacy)");
#else
  DualEspLink::begin_master(SPI_SCLK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN, SPI_CS_PIN, SPI_LINK_HZ);
  Serial.println("[Mofongo] role=logic, spi=master (legacy)");
#endif
#endif

#if ENABLE_WEB_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO)
  WebInput::begin();
#endif
#if ENABLE_BT_CONTROLLER && (!USE_DUAL_ESP || !DUAL_ESP_ROLE_VIDEO)
  BP32.setup(&bt_on_connected, &bt_on_disconnected);
  BP32.enableNewBluetoothConnections(true);
  if(kBtForgetKeysOnBoot)
    BP32.forgetBluetoothKeys();
  Serial.println("[Mofongo] BT input ready");
#endif
#endif

#if USE_MASA_RUNTIME
  if(!(USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO))
  {
    if(SPIFFS.begin(true))
    {
      Serial.println("[Mofongo] SPIFFS ok");
      MasaLoader::free_game_data_alloc(gMasaGame);
      if(MasaLoader::load_from_spiffs_alloc("/game.masa", gMasaGame))
      {
        gMasaRuntime.begin(gMasaGame);
        gMasaRuntime.set_audio_callback(masa_audio_cb);
        gMasaRuntime.set_beep_callback(masa_beep_cb);
        gMasaRuntime.set_beep_ex_callback(masa_beep_ex_cb);
        Serial.print("[Mofongo] MASA loaded, bytes=");
        Serial.println((int)gMasaGame.scriptSize);
        Serial.print("[Mofongo] MASA rooms bytes=");
        Serial.println((int)gMasaGame.roomsSize);
        if(gMasaRuntime.room_count() > 0)
        {
          gMasaRoomIndex = 0;
          gMasaBgIndex = gMasaRuntime.room_bg();
          gMasaBgColor = gMasaRuntime.room_bg_color();
          gMasaSongHash = gMasaRuntime.room_song_hash();
#if HAS_TILEMAPS
          gMasaTilemapIndex = gMasaRuntime.room_tilemap();
          gTilemapActive = (gMasaTilemapIndex != 0xFF) ? (int)gMasaTilemapIndex : -1;
#endif
        }
        else
        {
          gMasaBgIndex = (uint8_t)gMasaGame.bgIndex;
          gMasaBgColor = 12;
          gMasaSongHash = gMasaGame.songHash;
#if HAS_TILEMAPS
          gTilemapActive = -1;
          gMasaTilemapIndex = 0xFF;
#endif
        }
        if(BackgroundApi::image_count() > 0 && gMasaBgIndex < BackgroundApi::image_count())
        {
          int bg = (int)gMasaBgIndex;
          if(bg < 0 || bg >= BackgroundApi::image_count())
            bg = 0;
          BackgroundApi::set_image(bg);
          BackgroundApi::clear_color();
        }
        else
        {
          BackgroundApi::clear_image();
          BackgroundApi::set_color((int)gMasaBgColor);
        }
#if AUDIO_ON_THIS_ROLE
        if(gMasaSongHash != 0 && songsCount > 0)
        {
          for(int i = 0; i < songsCount; i++)
          {
            const char *nm = songs[i].name;
            if(nm == NULL)
              continue;
            uint32_t h = 0x811C9DC5;
            for(const char *p = nm; *p; p++)
            {
              h ^= (uint32_t)(*p) & 0xFF;
              h *= 0x01000193;
            }
            if(h == gMasaSongHash)
            {
              AudioApi::play_sound(songs[i], true);
              break;
            }
          }
        }
#endif
      }
      else
      {
        Serial.println("[Mofongo] MASA load failed");
        spiffs_list_files();
      }
    }
    else
    {
      Serial.println("[Mofongo] SPIFFS init failed");
    }
  }
#endif

  // Select initial background
#if HAS_PROGRAM_LOGIC
  if(!(USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO))
  {
    if(BackgroundApi::image_count() > 0)
      BackgroundApi::set_image(0);
    ProgramLogic::program_logic_setup();
    if(ENABLE_ROOM_CYCLE_TEST)
    {
      apply_room_cycle(0);
      roomCycleIndex = 0;
      roomCycleLastMs = millis();
    }
  }
#else
  if(ACTIVE_ROOM_BG_INDEX >= 0 && ACTIVE_ROOM_BG_INDEX < BackgroundApi::image_count())
    BackgroundApi::set_image(ACTIVE_ROOM_BG_INDEX);
  else if(BackgroundApi::image_count() > 0)
    BackgroundApi::set_image(0);
  if(ROOM_ENABLE_GGBALLS)
    init_ggballs();
#endif
}

void draw()
{
#if USE_MASA_RUNTIME && USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO
  if(!gMasaHavePacket)
  {
    graphics.begin(0);
    draw_layer_ui();
    graphics.end();
    return;
  }
#endif
  // Build one full frame using the 3-layer pipeline
  graphics.begin(0);
  draw_layer_background();
  draw_layer_sprites();
  draw_layer_ui();

  // Swap back/front buffers for display
  graphics.end();
}

void loop()
{
  // Dual-ESP logic role: run game logic and stream state over SPI
#if USE_DUAL_ESP && !DUAL_ESP_ROLE_VIDEO
#if ENABLE_WEB_CONTROLLER || ENABLE_BT_CONTROLLER
  uint16_t mask = 0;
  bool selectPressed = false;
#if ENABLE_WEB_CONTROLLER
  WebInput::handle();
  if(WebInput::down(WebInput::BTN_UP)) mask |= MasaRuntime::INPUT_UP;
  if(WebInput::down(WebInput::BTN_DOWN)) mask |= MasaRuntime::INPUT_DOWN;
  if(WebInput::down(WebInput::BTN_LEFT)) mask |= MasaRuntime::INPUT_LEFT;
  if(WebInput::down(WebInput::BTN_RIGHT)) mask |= MasaRuntime::INPUT_RIGHT;
  if(WebInput::down(WebInput::BTN_A)) mask |= MasaRuntime::INPUT_A;
  if(WebInput::down(WebInput::BTN_B)) mask |= MasaRuntime::INPUT_B;
  if(WebInput::down(WebInput::BTN_X)) mask |= MasaRuntime::INPUT_X;
  if(WebInput::down(WebInput::BTN_Y)) mask |= MasaRuntime::INPUT_Y;
  if(WebInput::down(WebInput::BTN_L)) mask |= MasaRuntime::INPUT_L;
  if(WebInput::down(WebInput::BTN_R)) mask |= MasaRuntime::INPUT_R;
  if(WebInput::down(WebInput::BTN_START)) mask |= MasaRuntime::INPUT_START;
  if(WebInput::down(WebInput::BTN_SELECT)) mask |= MasaRuntime::INPUT_SELECT;
  if(WebInput::pressed(WebInput::BTN_SELECT))
    selectPressed = true;
#endif
#if ENABLE_BT_CONTROLLER
  BP32.update();
  uint16_t btMask = bt_input_mask();
  mask |= btMask;
  bool btSelectNow = (btMask & MasaRuntime::INPUT_SELECT) != 0;
  if(btSelectNow && !gBtSelectPrev)
    selectPressed = true;
  gBtSelectPrev = btSelectNow;
#endif
  gMasaRuntime.set_input_mask(mask);
  if(selectPressed)
  {
    unsigned long now = millis();
    if(now - gMasaSelectLastMs > 250)
    {
      gMasaSelectLastMs = now;
        if(gMasaRuntime.room_count() > 0)
        {
          gMasaRoomIndex = (uint8_t)((gMasaRoomIndex + 1) % gMasaRuntime.room_count());
          gMasaRuntime.set_room(gMasaRoomIndex);
          gMasaBgIndex = gMasaRuntime.room_bg();
          gMasaBgColor = gMasaRuntime.room_bg_color();
          gMasaSongHash = gMasaRuntime.room_song_hash();
#if HAS_TILEMAPS
          gMasaTilemapIndex = gMasaRuntime.room_tilemap();
          gTilemapActive = (gMasaTilemapIndex != 0xFF) ? (int)gMasaTilemapIndex : -1;
#endif
        }
        else
        {
        int bgCount = BackgroundApi::image_count();
        if(bgCount > 0)
        {
          gMasaRoomIndex = (uint8_t)((gMasaRoomIndex + 1) % bgCount);
          gMasaBgIndex = gMasaRoomIndex;
        }
        gMasaRuntime.begin(gMasaGame);
#if HAS_TILEMAPS
        gTilemapActive = -1;
        gMasaTilemapIndex = 0xFF;
#endif
        }
      if(BackgroundApi::image_count() > 0 && gMasaBgIndex < BackgroundApi::image_count())
      {
        int bg = (int)gMasaBgIndex;
        if(bg < 0 || bg >= BackgroundApi::image_count())
          bg = 0;
        BackgroundApi::set_image(bg);
        BackgroundApi::clear_color();
      }
      else
      {
        BackgroundApi::clear_image();
        BackgroundApi::set_color((int)gMasaBgColor);
      }
#if HAS_TILEMAPS
      gMasaTilemapIndex = (gMasaRuntime.room_count() > 0) ? gMasaRuntime.room_tilemap() : 0xFF;
      gTilemapActive = (gMasaTilemapIndex != 0xFF) ? (int)gMasaTilemapIndex : -1;
#endif
#if AUDIO_ON_THIS_ROLE
      if(gMasaSongHash != 0 && songsCount > 0)
      {
        for(int i = 0; i < songsCount; i++)
        {
          const char *nm = songs[i].name;
          if(nm == NULL)
            continue;
          uint32_t h = 0x811C9DC5;
          for(const char *p = nm; *p; p++)
          {
            h ^= (uint32_t)(*p) & 0xFF;
            h *= 0x01000193;
          }
          if(h == gMasaSongHash)
          {
            AudioApi::play_sound(songs[i], true);
            break;
          }
        }
      }
#endif
    }
  }
#endif
#if USE_MASA_RUNTIME
  gMasaCmdQueue.reset();
  gMasaRuntime.step(millis(), gMasaCmdQueue);
  if(gMasaRuntime.room_count() > 0)
  {
    uint8_t runtimeRoom = gMasaRuntime.room_index();
    if(runtimeRoom != gMasaRoomIndex)
    {
      gMasaRoomIndex = runtimeRoom;
      gMasaBgIndex = gMasaRuntime.room_bg();
      gMasaBgColor = gMasaRuntime.room_bg_color();
      gMasaSongHash = gMasaRuntime.room_song_hash();
#if HAS_TILEMAPS
      gMasaTilemapIndex = gMasaRuntime.room_tilemap();
      gTilemapActive = (gMasaTilemapIndex != 0xFF) ? (int)gMasaTilemapIndex : -1;
#endif
      if(BackgroundApi::image_count() > 0 && gMasaBgIndex < BackgroundApi::image_count())
      {
        int bg = (int)gMasaBgIndex;
        if(bg < 0 || bg >= BackgroundApi::image_count())
          bg = 0;
        BackgroundApi::set_image(bg);
        BackgroundApi::clear_color();
      }
      else
      {
        BackgroundApi::clear_image();
        BackgroundApi::set_color((int)gMasaBgColor);
      }
#if AUDIO_ON_THIS_ROLE
      if(gMasaSongHash != 0 && songsCount > 0)
      {
        for(int i = 0; i < songsCount; i++)
        {
          const char *nm = songs[i].name;
          if(nm == NULL)
            continue;
          uint32_t h = 0x811C9DC5;
          for(const char *p = nm; *p; p++)
          {
            h ^= (uint32_t)(*p) & 0xFF;
            h *= 0x01000193;
          }
          if(h == gMasaSongHash)
          {
            AudioApi::play_sound(songs[i], true);
            break;
          }
        }
      }
#endif
    }
  }
  if(!gMasaRuntime.running() && gMasaGame.valid && !gMasaRuntime.persistent())
  {
    // Loop MASA scripts during hardware testing
    gMasaRuntime.begin(gMasaGame);
  }
#if AUDIO_ON_THIS_ROLE
  masa_apply_music_cmds();
  AudioApi::update();
#endif
  masa_send_logic_state();
  delay(1);
  return;
#endif
#if HAS_PROGRAM_LOGIC
  ProgramLogic::program_logic_update(millis());
  if(ENABLE_ROOM_CYCLE_TEST)
  {
    unsigned long now = millis();
    if(now - roomCycleLastMs >= ROOM_CYCLE_MS)
    {
      roomCycleLastMs = now;
      roomCycleIndex = (roomCycleIndex + 1) % kRoomCycleCount;
      apply_room_cycle(roomCycleIndex);
    }
  }
#endif
#if AUDIO_ON_THIS_ROLE
  AudioApi::update();
#endif
  spi_send_logic_state();
  delay(1);
  return;
#endif

  // Video role update (single-ESP or dual-ESP video board)
#if AUDIO_ON_THIS_ROLE
  AudioApi::update();
#endif
#if HAS_PROGRAM_LOGIC && !(USE_DUAL_ESP && DUAL_ESP_ROLE_VIDEO)
  if(ENABLE_ROOM_CYCLE_TEST)
  {
    unsigned long now = millis();
    if(now - roomCycleLastMs >= ROOM_CYCLE_MS)
    {
      roomCycleLastMs = now;
      roomCycleIndex = (roomCycleIndex + 1) % kRoomCycleCount;
      apply_room_cycle(roomCycleIndex);
    }
  }
#endif
#if !HAS_PROGRAM_LOGIC
  if(ROOM_ENABLE_BG_SCROLL && BackgroundApi::current_image() >= 0)
    BackgroundApi::add_scroll(1, 0);
#endif

  // Update diagnostics and render
  fps_update();
  draw();
  composite.sendFrameHalfResolution(&graphics.frame);
}
