#include "MasaRuntime.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

namespace MasaRuntime
{
static const bool kDebugAsteroids = false;
static const bool kDebugProjectileSlots = true;
#define MASA_DBG(...) do { if(kDebugAsteroids) { Serial.printf(__VA_ARGS__); } } while(0)
static inline bool masa_dbg_slot(uint8_t slot)
{
  // Support both common collision slot layouts:
  // - 0/1/2 (legacy or compact setups)
  // - 3 (player damage/debug)
  // - 8/9/10 (separated projectile slots)
  return (slot <= 3) || (slot >= 8 && slot <= 10);
}
#define MASA_DBG_SLOT(slot, ...) do { if(kDebugProjectileSlots && masa_dbg_slot((uint8_t)(slot))) { Serial.printf(__VA_ARGS__); } } while(0)
static const uint8_t kMaxHudTemplateLen = kMaxTextBoxLen;

static inline uint16_t read_u16(const uint8_t *p)
{
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static inline int16_t read_s16(const uint8_t *p)
{
  return (int16_t)read_u16(p);
}

static inline int32_t read_s32(const uint8_t *p)
{
  return (int32_t)p[0] | ((int32_t)p[1] << 8) | ((int32_t)p[2] << 16) | ((int32_t)p[3] << 24);
}

static inline float read_f32(const uint8_t *p)
{
  float v = 0.0f;
  memcpy(&v, p, sizeof(float));
  return v;
}

static int16_t s_vx10[kMaxObjects];
static int16_t s_vy10[kMaxObjects];
static float s_vxCarry[kMaxObjects];
static float s_vyCarry[kMaxObjects];
static int16_t s_angle10[kMaxObjects];
static int16_t s_angleSpeed10[kMaxObjects];
static int16_t s_turnSpeed10[kMaxObjects];
static float s_posX[kMaxObjects];
static float s_posY[kMaxObjects];
static float s_prevPosX[kMaxObjects];
static float s_prevPosY[kMaxObjects];
static uint8_t s_renderSprite[kMaxObjects];
static int16_t s_renderAngle10[kMaxObjects];
static uint16_t s_renderScale1000[kMaxObjects];
static int16_t s_inputSpeed10[kMaxObjects];
static int16_t s_accel10[kMaxObjects];
static uint16_t s_friction1000[kMaxObjects];
static int16_t s_thrust10[kMaxObjects];
static bool s_noWrap[kMaxObjects];
static bool s_bounceEnabled[kMaxObjects];
static bool s_isProjectile[kMaxObjects];
static bool s_velRandomEnabled[kMaxObjects];
static int16_t s_velRandomMin10[kMaxObjects];
static int16_t s_velRandomMax10[kMaxObjects];
static uint16_t s_inputMask = 0;
static bool s_roomPersistent[kMaxObjects];
static uint16_t s_scaleBase1000[kMaxObjects];
static uint16_t s_scaleAmp1000[kMaxObjects];
static float s_scalePhase[kMaxObjects];
static float s_scaleSpeedRadPerMs[kMaxObjects];
static uint8_t s_animFrames[kMaxObjects][16];
static uint8_t s_animCount[kMaxObjects];
static uint8_t s_animIndex[kMaxObjects];
static uint8_t s_animFps[kMaxObjects];
static uint32_t s_animNextMs[kMaxObjects];
static bool s_textVisible[kMaxTextSlots];
static int16_t s_textX[kMaxTextSlots];
static int16_t s_textY[kMaxTextSlots];
static uint8_t s_textColor[kMaxTextSlots];
static uint8_t s_textLen[kMaxTextSlots];
static char s_textStr[kMaxTextSlots][kMaxTextLen + 1];
static uint8_t s_textSpan[kMaxTextSlots];
static bool s_shapeVisible[kMaxShapeSlots];
static uint8_t s_shapeType[kMaxShapeSlots];
static int16_t s_shapeX1[kMaxShapeSlots];
static int16_t s_shapeY1[kMaxShapeSlots];
static int16_t s_shapeX2[kMaxShapeSlots];
static int16_t s_shapeY2[kMaxShapeSlots];
static int16_t s_shapeX3[kMaxShapeSlots];
static int16_t s_shapeY3[kMaxShapeSlots];
static uint8_t s_shapeColor[kMaxShapeSlots];
static bool s_textBoxVisible[kMaxTextBoxes];
static int16_t s_textBoxX[kMaxTextBoxes];
static int16_t s_textBoxY[kMaxTextBoxes];
static int16_t s_textBoxW[kMaxTextBoxes];
static int16_t s_textBoxH[kMaxTextBoxes];
static uint8_t s_textBoxColor[kMaxTextBoxes];
static uint8_t s_textBoxLen[kMaxTextBoxes];
static char s_textBoxStr[kMaxTextBoxes][kMaxTextBoxLen + 1];
static bool s_choiceVisible[kMaxChoiceSlots];
static int16_t s_choiceX[kMaxChoiceSlots];
static int16_t s_choiceY[kMaxChoiceSlots];
static uint8_t s_choiceColor[kMaxChoiceSlots];
static uint8_t s_choiceCount[kMaxChoiceSlots];
static uint8_t s_choiceSelected[kMaxChoiceSlots];
static uint8_t s_choiceBaseSignal[kMaxChoiceSlots];
static uint8_t s_choiceLen[kMaxChoiceSlots][kMaxChoiceItems];
static char s_choiceText[kMaxChoiceSlots][kMaxChoiceItems][kMaxChoiceLen + 1];
static bool s_choicePrevUp[kMaxChoiceSlots];
static bool s_choicePrevDown[kMaxChoiceSlots];
static bool s_choicePrevConfirm[kMaxChoiceSlots];
static uint8_t s_hitW[kMaxObjects];
static uint8_t s_hitH[kMaxObjects];
static int8_t s_hitOffX[kMaxObjects];
static int8_t s_hitOffY[kMaxObjects];
static uint8_t s_defaultSprite[kMaxObjects];
static uint8_t *s_collideSlot = NULL;
static uint8_t *s_collideA = NULL;
static uint8_t *s_collideB = NULL;
static uint8_t s_collideCount = 0;
static bool s_signalActive[kMaxSignals];
static bool s_signalPrev[kMaxSignals];
static bool s_signalForce[kMaxSignals];
static uint8_t s_signalOther[kMaxSignals];
static uint8_t s_signalSource[kMaxSignals];
static bool s_signalSourceProjectile[kMaxSignals];
static uint8_t *s_actionSlot = NULL;
static uint8_t *s_actionType = NULL;
static uint8_t *s_actionObj = NULL;
static int16_t *s_actionX = NULL;
static int16_t *s_actionY = NULL;
static uint8_t *s_actionSprite = NULL;
static uint8_t *s_actionSound = NULL;
static int16_t *s_actionW = NULL;
static int16_t *s_actionH = NULL;
static uint8_t *s_actionColor = NULL;
static uint8_t *s_actionCountItems = NULL;
static uint8_t *s_actionBaseSignal = NULL;
static uint8_t *s_actionTextLen = NULL;
static char (*s_actionText)[kMaxTextBoxLen + 1] = NULL;
static uint8_t *s_actionChoiceCount = NULL;
static uint8_t (*s_actionChoiceLen)[kMaxChoiceItems] = NULL;
static char (*s_actionChoiceText)[kMaxChoiceItems][kMaxChoiceLen + 1] = NULL;
static int16_t *s_actionSpeed10 = NULL;
static int16_t *s_actionOffset = NULL;
static uint8_t *s_actionOwner = NULL;
static uint16_t *s_actionBeepHz = NULL;
static uint16_t *s_actionBeepMs = NULL;
static uint8_t *s_actionBeepWave = NULL;
static bool s_spawnTargetAllowed[kMaxSignals][kMaxObjects];
static bool s_slotSpawnBulletSeen[kMaxSignals];
static bool s_slotSpawnBulletFired[kMaxSignals];
static uint8_t *s_inputBindSlot = NULL;
static uint8_t *s_inputBindEvent = NULL;
static uint8_t *s_inputBindButton = NULL;
static uint8_t *s_inputBindOwner = NULL;
static uint8_t s_choiceOwner[kMaxChoiceSlots];
static uint8_t s_inputBindCount = 0;
static uint16_t s_prevInputMask = 0;
static int16_t s_bgScrollX10 = 0;
static int16_t s_bgScrollY10 = 0;
static float s_bgScrollAccX = 0.0f;
static float s_bgScrollAccY = 0.0f;
static int16_t s_bgScrollStepX = 0;
static int16_t s_bgScrollStepY = 0;
static bool s_alarmActive[kMaxObjects][kMaxAlarms];
static bool s_alarmRepeat[kMaxObjects][kMaxAlarms];
static uint16_t s_alarmPeriodMs[kMaxObjects][kMaxAlarms];
static uint32_t s_alarmNextMs[kMaxObjects][kMaxAlarms];
static uint8_t s_alarmSignal[kMaxObjects][kMaxAlarms];
static uint16_t s_alarmDefaultMs[kMaxObjects][kMaxAlarms];
static bool s_alarmDefaultRepeat[kMaxObjects][kMaxAlarms];
static uint8_t s_musicSignalSlot = 0xFF;
static uint8_t s_musicSignalOwner = 0xFF;
static uint8_t s_actionCount = 0;
static uint8_t s_actionOwnerCur = 0xFF;
static bool s_stateInit = false;
static bool s_hudEnabled = false;
static int16_t s_hudX = 8;
static int16_t s_hudY = 8;
static uint8_t s_hudColor = 15;
static uint8_t s_hudAlign = 0;      // 0 left, 1 center, 2 right
static uint8_t s_hudBgColor = 0xFF; // 0xFF = no background
static int16_t s_hudPadX = 2;
static int16_t s_hudPadY = 1;
static char s_hudFormat[kMaxHudTemplateLen + 1];
static int32_t s_hudLife = 3;
static int32_t s_hudScore = 0;
static int32_t s_hudCoins = 0;
static bool s_gameOverArmed = false;
static uint16_t s_gameOverPrevMask = 0;
static char s_gameOverText[kMaxTextLen + 1];
static char s_gameOverScorePrefix[kMaxTextLen + 1];
static char s_gameOverRestartText[kMaxTextLen + 1];
static const int kMaxVarsPerObj = 12;
static const int kMaxGlobalVars = 32;
static int32_t s_varGlobal[kMaxGlobalVars];
static int32_t s_varObj[kMaxObjects][kMaxVarsPerObj];
static bool s_varTextVisible[kMaxTextSlots];
static int16_t s_varTextX[kMaxTextSlots];
static int16_t s_varTextY[kMaxTextSlots];
static uint8_t s_varTextColor[kMaxTextSlots];
static uint8_t s_varTextScope[kMaxTextSlots];
static uint8_t s_varTextObj[kMaxTextSlots];
static uint8_t s_varTextIndex[kMaxTextSlots];
static char s_varTextLabel[kMaxTextSlots][kMaxTextLen + 1];
static float s_varfGlobal[kMaxGlobalVars];
static float s_varfObj[kMaxObjects][kMaxVarsPerObj];
static bool s_varfTextVisible[kMaxTextSlots];
static int16_t s_varfTextX[kMaxTextSlots];
static int16_t s_varfTextY[kMaxTextSlots];
static uint8_t s_varfTextColor[kMaxTextSlots];
static uint8_t s_varfTextScope[kMaxTextSlots];
static uint8_t s_varfTextObj[kMaxTextSlots];
static uint8_t s_varfTextIndex[kMaxTextSlots];
static char s_varfTextLabel[kMaxTextSlots][kMaxTextLen + 1];

static int16_t random_vel10_for_obj(uint8_t obj)
{
  if(obj >= kMaxObjects || !s_velRandomEnabled[obj])
    return 0;
  int16_t lo = s_velRandomMin10[obj];
  int16_t hi = s_velRandomMax10[obj];
  if(lo > hi)
  {
    int16_t t = lo;
    lo = hi;
    hi = t;
  }
  long v = random((long)lo, (long)hi + 1L);
  if(v == 0 && lo < 0 && hi > 0)
  {
    v = (random(0, 2) == 0) ? -1 : 1;
  }
  return (int16_t)v;
}

static void replace_token_i32(char *buf, size_t cap, const char *token, int32_t value)
{
  if(buf == NULL || token == NULL || cap == 0)
    return;
  size_t tokLen = strlen(token);
  if(tokLen == 0)
    return;
  char num[24];
  snprintf(num, sizeof(num), "%ld", (long)value);
  while(true)
  {
    char *pos = strstr(buf, token);
    if(pos == NULL)
      break;
    char out[kMaxTextBoxLen + 1];
    int pre = (int)(pos - buf);
    if(pre < 0) pre = 0;
    if(pre > (int)(cap - 1)) pre = (int)(cap - 1);
    for(int i = 0; i < pre; i++)
      out[i] = buf[i];
    out[pre] = '\0';
    strncat(out, num, sizeof(out) - strlen(out) - 1);
    strncat(out, pos + tokLen, sizeof(out) - strlen(out) - 1);
    strncpy(buf, out, cap - 1);
    buf[cap - 1] = '\0';
  }
}
static char s_strGlobal[kMaxGlobalVars][kMaxTextLen + 1];
static char s_strObj[kMaxObjects][kMaxVarsPerObj][kMaxTextLen + 1];
static bool s_strTextVisible[kMaxTextSlots];
static int16_t s_strTextX[kMaxTextSlots];
static int16_t s_strTextY[kMaxTextSlots];
static uint8_t s_strTextColor[kMaxTextSlots];
static uint8_t s_strTextScope[kMaxTextSlots];
static uint8_t s_strTextObj[kMaxTextSlots];
static uint8_t s_strTextIndex[kMaxTextSlots];
static char s_strTextLabel[kMaxTextSlots][kMaxTextLen + 1];

static const uint32_t kRoomObjSize = 13;
static const uint32_t kRoomHeaderSize = 8; // bg (1) + bgColor (1) + song hash (4) + tilemap (1) + objCount (1)
static const uint8_t kSignalActionDestroy = 1;
static const uint8_t kSignalActionSpawn = 2;
static const uint8_t kSignalActionSound = 3;
static const uint8_t kSignalActionDestroyOther = 4;
static const uint8_t kSignalActionRoomNext = 5;
static const uint8_t kSignalActionStop = 6;
static const uint8_t kSignalActionTextBox = 7;
static const uint8_t kSignalActionChoices = 8;
static const uint8_t kSignalActionTextBoxClear = 9;
static const uint8_t kSignalActionChoicesClear = 10;
static const uint8_t kSignalActionSetInput = 11;
static const uint8_t kSignalActionRoomGoto = 12;
static const uint8_t kSignalActionSpawnBullet = 13;
static const uint8_t kSignalActionBeep = 14;
static const uint8_t kSignalActionHudAdd = 15;
static const uint8_t kSignalActionShowText = 16;
static const uint8_t kSignalActionShowTextClear = 17;

static bool ensure_runtime_dynamic_pools()
{
  if(s_collideSlot == NULL) s_collideSlot = (uint8_t *)malloc((size_t)kMaxColliders);
  if(s_collideA == NULL) s_collideA = (uint8_t *)malloc((size_t)kMaxColliders);
  if(s_collideB == NULL) s_collideB = (uint8_t *)malloc((size_t)kMaxColliders);

  if(s_actionSlot == NULL) s_actionSlot = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionType == NULL) s_actionType = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionObj == NULL) s_actionObj = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionX == NULL) s_actionX = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionY == NULL) s_actionY = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionSprite == NULL) s_actionSprite = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionSound == NULL) s_actionSound = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionW == NULL) s_actionW = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionH == NULL) s_actionH = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionColor == NULL) s_actionColor = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionCountItems == NULL) s_actionCountItems = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionBaseSignal == NULL) s_actionBaseSignal = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionTextLen == NULL) s_actionTextLen = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionText == NULL) s_actionText = (char (*)[kMaxTextBoxLen + 1])malloc((size_t)kMaxSignalActions * (size_t)(kMaxTextBoxLen + 1));
  if(s_actionChoiceCount == NULL) s_actionChoiceCount = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionChoiceLen == NULL) s_actionChoiceLen = (uint8_t (*)[kMaxChoiceItems])malloc((size_t)kMaxSignalActions * (size_t)kMaxChoiceItems);
  if(s_actionChoiceText == NULL) s_actionChoiceText = (char (*)[kMaxChoiceItems][kMaxChoiceLen + 1])malloc((size_t)kMaxSignalActions * (size_t)kMaxChoiceItems * (size_t)(kMaxChoiceLen + 1));
  if(s_actionSpeed10 == NULL) s_actionSpeed10 = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionOffset == NULL) s_actionOffset = (int16_t *)malloc((size_t)kMaxSignalActions * sizeof(int16_t));
  if(s_actionOwner == NULL) s_actionOwner = (uint8_t *)malloc((size_t)kMaxSignalActions);
  if(s_actionBeepHz == NULL) s_actionBeepHz = (uint16_t *)malloc((size_t)kMaxSignalActions * sizeof(uint16_t));
  if(s_actionBeepMs == NULL) s_actionBeepMs = (uint16_t *)malloc((size_t)kMaxSignalActions * sizeof(uint16_t));
  if(s_actionBeepWave == NULL) s_actionBeepWave = (uint8_t *)malloc((size_t)kMaxSignalActions);

  if(s_inputBindSlot == NULL) s_inputBindSlot = (uint8_t *)malloc((size_t)kMaxInputBinds);
  if(s_inputBindEvent == NULL) s_inputBindEvent = (uint8_t *)malloc((size_t)kMaxInputBinds);
  if(s_inputBindButton == NULL) s_inputBindButton = (uint8_t *)malloc((size_t)kMaxInputBinds);
  if(s_inputBindOwner == NULL) s_inputBindOwner = (uint8_t *)malloc((size_t)kMaxInputBinds);

  return s_collideSlot && s_collideA && s_collideB &&
         s_actionSlot && s_actionType && s_actionObj && s_actionX && s_actionY &&
         s_actionSprite && s_actionSound && s_actionW && s_actionH && s_actionColor &&
         s_actionCountItems && s_actionBaseSignal && s_actionTextLen && s_actionText &&
         s_actionChoiceCount && s_actionChoiceLen && s_actionChoiceText &&
         s_actionSpeed10 && s_actionOffset && s_actionOwner && s_actionBeepHz &&
         s_actionBeepMs && s_actionBeepWave &&
         s_inputBindSlot && s_inputBindEvent && s_inputBindButton && s_inputBindOwner;
}

static bool hitbox_overlap(float ax, float ay, uint8_t aw, uint8_t ah,
                           float bx, float by, uint8_t bw, uint8_t bh)
{
  float halfAw = aw * 0.5f;
  float halfAh = ah * 0.5f;
  float halfBw = bw * 0.5f;
  float halfBh = bh * 0.5f;
  return (fabsf(ax - bx) <= (halfAw + halfBw)) && (fabsf(ay - by) <= (halfAh + halfBh));
}

static bool hitbox_overlap_swept(float ax0, float ay0, float ax1, float ay1, uint8_t aw, uint8_t ah,
                                 float bx, float by, uint8_t bw, uint8_t bh)
{
  float halfAw = aw * 0.5f;
  float halfAh = ah * 0.5f;
  float halfBw = bw * 0.5f;
  float halfBh = bh * 0.5f;

  float aLeft = min(ax0, ax1) - halfAw;
  float aRight = max(ax0, ax1) + halfAw;
  float aTop = min(ay0, ay1) - halfAh;
  float aBottom = max(ay0, ay1) + halfAh;

  float bLeft = bx - halfBw;
  float bRight = bx + halfBw;
  float bTop = by - halfBh;
  float bBottom = by + halfBh;

  return !(aRight < bLeft || aLeft > bRight || aBottom < bTop || aTop > bBottom);
}

static void scan_room_persistent(const uint8_t *data, uint32_t size)
{
  for(int i = 0; i < kMaxObjects; i++)
    s_roomPersistent[i] = false;
  if(data == NULL || size < 2)
    return;

  uint16_t count = read_u16(data);
  uint32_t off = 2;
  for(uint16_t r = 0; r < count; r++)
  {
    if(off + kRoomHeaderSize > size)
      break;
    off += 1; // bg
    off += 1; // bg color
    off += 4; // song hash
    off += 1; // tilemap
    uint8_t objCount = data[off++];
    for(uint8_t i = 0; i < objCount; i++)
    {
      if(off + kRoomObjSize > size)
        return;
      uint8_t objId = data[off];
      uint8_t persistent = data[off + 12];
      if(persistent && objId < kMaxObjects)
        s_roomPersistent[objId] = true;
      off += kRoomObjSize;
    }
  }
}

static void behavior_reset()
{
  if(!ensure_runtime_dynamic_pools())
  {
    Serial.println("[MasaRuntime] OOM: dynamic pools alloc failed");
    delay(1000);
    return;
  }
  for(int i = 0; i < kMaxObjects; i++)
  {
    s_vx10[i] = 0;
    s_vy10[i] = 0;
    s_vxCarry[i] = 0.0f;
    s_vyCarry[i] = 0.0f;
    s_angle10[i] = 0;
    s_angleSpeed10[i] = 0;
    s_turnSpeed10[i] = 0;
    s_posX[i] = 0.0f;
    s_posY[i] = 0.0f;
    s_prevPosX[i] = 0.0f;
    s_prevPosY[i] = 0.0f;
    s_renderSprite[i] = 0;
    s_renderAngle10[i] = 0;
    s_renderScale1000[i] = 1000;
    s_inputSpeed10[i] = 0;
    s_accel10[i] = 0;
    s_friction1000[i] = 1000;
    s_thrust10[i] = 0;
    s_noWrap[i] = false;
    s_bounceEnabled[i] = false;
    s_isProjectile[i] = false;
    s_velRandomEnabled[i] = false;
    s_velRandomMin10[i] = 0;
    s_velRandomMax10[i] = 0;
    s_roomPersistent[i] = false;
    s_scaleBase1000[i] = 1000;
    s_scaleAmp1000[i] = 0;
    s_scalePhase[i] = 0.0f;
    s_scaleSpeedRadPerMs[i] = 0.0f;
    s_animCount[i] = 0;
    s_animIndex[i] = 0;
    s_animFps[i] = 0;
    s_animNextMs[i] = 0;
    s_hitW[i] = 16;
    s_hitH[i] = 16;
    s_hitOffX[i] = 0;
    s_hitOffY[i] = 0;
  }
  for(int i = 0; i < kMaxTextSlots; i++)
  {
    s_textVisible[i] = false;
    s_textX[i] = 0;
    s_textY[i] = 0;
    s_textColor[i] = 15;
    s_textLen[i] = 0;
    s_textStr[i][0] = '\0';
    s_textSpan[i] = 1;
  }
  for(int i = 0; i < kMaxShapeSlots; i++)
  {
    s_shapeVisible[i] = false;
    s_shapeType[i] = 0;
    s_shapeX1[i] = 0;
    s_shapeY1[i] = 0;
    s_shapeX2[i] = 0;
    s_shapeY2[i] = 0;
    s_shapeX3[i] = 0;
    s_shapeY3[i] = 0;
    s_shapeColor[i] = 15;
  }
  for(int i = 0; i < kMaxTextBoxes; i++)
  {
    s_textBoxVisible[i] = false;
    s_textBoxX[i] = 0;
    s_textBoxY[i] = 0;
    s_textBoxW[i] = 0;
    s_textBoxH[i] = 0;
    s_textBoxColor[i] = 15;
    s_textBoxLen[i] = 0;
    s_textBoxStr[i][0] = '\0';
  }
  for(int i = 0; i < kMaxChoiceSlots; i++)
  {
    s_choiceVisible[i] = false;
    s_choiceX[i] = 0;
    s_choiceY[i] = 0;
    s_choiceColor[i] = 15;
    s_choiceCount[i] = 0;
    s_choiceSelected[i] = 0;
    s_choiceBaseSignal[i] = 0;
    s_choicePrevUp[i] = false;
    s_choicePrevDown[i] = false;
    s_choicePrevConfirm[i] = false;
    s_choiceOwner[i] = 0xFF;
    for(int j = 0; j < kMaxChoiceItems; j++)
    {
      s_choiceLen[i][j] = 0;
      s_choiceText[i][j][0] = '\0';
    }
  }
  for(int i = 0; i < kMaxSignals; i++)
  {
    s_signalActive[i] = false;
    s_signalPrev[i] = false;
    s_signalForce[i] = false;
    s_signalOther[i] = 0xFF;
    s_signalSource[i] = 0xFF;
    s_slotSpawnBulletSeen[i] = false;
    s_slotSpawnBulletFired[i] = false;
    for(int o = 0; o < kMaxObjects; o++)
      s_spawnTargetAllowed[i][o] = false;
  }
  s_collideCount = 0;
  s_actionCount = 0;
  s_actionOwnerCur = 0xFF;
  for(int i = 0; i < kMaxSignalActions; i++)
  {
    s_actionOwner[i] = 0xFF;
    s_actionBeepHz[i] = 0;
    s_actionBeepMs[i] = 0;
  }
  s_inputBindCount = 0;
  for(int i = 0; i < kMaxInputBinds; i++)
    s_inputBindOwner[i] = 0xFF;
  s_prevInputMask = 0;
  s_bgScrollX10 = 0;
  s_bgScrollY10 = 0;
  s_bgScrollAccX = 0.0f;
  s_bgScrollAccY = 0.0f;
  s_bgScrollStepX = 0;
  s_bgScrollStepY = 0;
  for(int o = 0; o < kMaxObjects; o++)
  {
    for(int i = 0; i < kMaxAlarms; i++)
    {
      s_alarmActive[o][i] = false;
      s_alarmRepeat[o][i] = false;
      s_alarmPeriodMs[o][i] = 0;
      s_alarmNextMs[o][i] = 0;
      s_alarmSignal[o][i] = 0;
      s_alarmDefaultMs[o][i] = 0;
      s_alarmDefaultRepeat[o][i] = false;
    }
  }
  for(int i = 0; i < kMaxGlobalVars; i++)
    s_varGlobal[i] = 0;
  for(int i = 0; i < kMaxObjects; i++)
    for(int j = 0; j < kMaxVarsPerObj; j++)
      s_varObj[i][j] = 0;
  for(int i = 0; i < kMaxGlobalVars; i++)
    s_varfGlobal[i] = 0.0f;
  for(int i = 0; i < kMaxObjects; i++)
    for(int j = 0; j < kMaxVarsPerObj; j++)
      s_varfObj[i][j] = 0.0f;
  for(int i = 0; i < kMaxTextSlots; i++)
  {
    s_varTextVisible[i] = false;
    s_varTextX[i] = 0;
    s_varTextY[i] = 0;
    s_varTextColor[i] = 15;
    s_varTextScope[i] = 0;
    s_varTextObj[i] = 0;
    s_varTextIndex[i] = 0;
    s_varTextLabel[i][0] = '\0';
    s_varfTextVisible[i] = false;
    s_varfTextX[i] = 0;
    s_varfTextY[i] = 0;
    s_varfTextColor[i] = 15;
    s_varfTextScope[i] = 0;
    s_varfTextObj[i] = 0;
    s_varfTextIndex[i] = 0;
    s_varfTextLabel[i][0] = '\0';
    s_strTextVisible[i] = false;
    s_strTextX[i] = 0;
    s_strTextY[i] = 0;
    s_strTextColor[i] = 15;
    s_strTextScope[i] = 0;
    s_strTextObj[i] = 0;
    s_strTextIndex[i] = 0;
    s_strTextLabel[i][0] = '\0';
  }
  for(int i = 0; i < kMaxGlobalVars; i++)
    s_strGlobal[i][0] = '\0';
  for(int i = 0; i < kMaxObjects; i++)
    for(int j = 0; j < kMaxVarsPerObj; j++)
      s_strObj[i][j][0] = '\0';
  s_hudEnabled = false;
  s_hudX = 8;
  s_hudY = 8;
  s_hudColor = 15;
  s_hudAlign = 0;
  s_hudBgColor = 0xFF;
  s_hudPadX = 2;
  s_hudPadY = 1;
  strncpy(s_hudFormat, "L:{LIFE} S:{SCORE} C:{COINS}", kMaxHudTemplateLen);
  s_hudFormat[kMaxHudTemplateLen] = '\0';
  s_hudLife = 3;
  s_hudScore = 0;
  s_hudCoins = 0;
  s_gameOverArmed = false;
  s_gameOverPrevMask = 0;
  strncpy(s_gameOverText, "GAME OVER", kMaxTextLen);
  s_gameOverText[kMaxTextLen] = '\0';
  strncpy(s_gameOverScorePrefix, "SCORE:", kMaxTextLen);
  s_gameOverScorePrefix[kMaxTextLen] = '\0';
  strncpy(s_gameOverRestartText, "PRESS ANY BUTTON TO RESTART", kMaxTextLen);
  s_gameOverRestartText[kMaxTextLen] = '\0';
  s_musicSignalSlot = 0xFF;
  s_musicSignalOwner = 0xFF;
  for(int i = 0; i < kMaxSignalActions; i++)
  {
    s_actionChoiceCount[i] = 0;
    for(int j = 0; j < kMaxChoiceItems; j++)
    {
      s_actionChoiceLen[i][j] = 0;
      s_actionChoiceText[i][j][0] = '\0';
    }
  }
  s_stateInit = true;
}

Runtime::Runtime()
{
  m_script = NULL;
  m_scriptSize = 0;
  m_pc = 0;
  m_waitUntil = 0;
  m_lastTickMs = 0;
  m_running = false;
  m_persistent = false;
  m_boundsEnabled = false;
  m_boundsMinX = 0;
  m_boundsMaxX = 0;
  m_boundsMinY = 0;
  m_boundsMaxY = 0;
  m_wrapEnabled = false;
  m_wrapMinX = 0;
  m_wrapMaxX = 0;
  m_wrapMinY = 0;
  m_wrapMaxY = 0;
  m_audioCb = NULL;
  m_beepCb = NULL;
  m_beepExCb = NULL;
  m_rooms = NULL;
  m_roomsSize = 0;
  m_roomCount = 0;
  m_roomIndex = 0;
  m_roomBg = 0;
  m_roomBgColor = 12;
  m_roomTilemap = 0xFF;
  m_roomSongHash = 0;
  m_musicCmd = {0, 0, 0};
  m_musicPlaying = false;
  m_musicLoop = false;
  m_musicSong = 0;
  for(int i = 0; i < kMaxObjects; i++)
  {
    m_objects[i].x = 0;
    m_objects[i].y = 0;
    m_objects[i].spriteId = 0;
    s_defaultSprite[i] = 0;
    m_objects[i].active = false;
  }
  if(!s_stateInit)
    behavior_reset();
}

void Runtime::set_input_mask(uint16_t mask)
{
  s_inputMask = mask;
}

static void alarm_start_defaults_for_obj(uint8_t obj, uint32_t nowMs)
{
  if(obj >= kMaxObjects)
    return;
  for(int i = 0; i < kMaxAlarms; i++)
  {
    if(s_alarmDefaultMs[obj][i] == 0)
      continue;
    s_alarmActive[obj][i] = true;
    s_alarmRepeat[obj][i] = s_alarmDefaultRepeat[obj][i];
    s_alarmPeriodMs[obj][i] = s_alarmDefaultMs[obj][i];
    s_alarmNextMs[obj][i] = nowMs + (uint32_t)s_alarmPeriodMs[obj][i];
  }
}

void Runtime::set_rooms(const uint8_t *data, uint32_t size)
{
  m_rooms = data;
  m_roomsSize = size;
  m_roomCount = 0;
  m_roomIndex = 0;
  m_roomBg = 0;
  m_roomBgColor = 12;
  m_roomTilemap = 0xFF;
  m_roomSongHash = 0;
  if(data == NULL || size < 2)
    return;
  m_roomCount = (uint8_t)(read_u16(data) & 0xFF);
  scan_room_persistent(data, size);
  if(m_roomCount > 0)
    m_persistent = true;
  if(m_roomCount > 0)
    set_room(0);
}

bool Runtime::set_room(uint8_t idx)
{
  if(m_rooms == NULL || m_roomsSize < 2)
    return false;
  uint16_t count = read_u16(m_rooms);
  if(count == 0)
    return false;
  if(idx >= count)
    idx = 0;

  uint32_t off = 2;
  uint8_t roomBg = 0;
  uint8_t roomBgColor = 12;
  uint8_t roomTilemap = 0xFF;
  uint32_t roomSong = 0;
  uint8_t objCount = 0;
  for(uint16_t r = 0; r < count; r++)
  {
    if(off + kRoomHeaderSize > m_roomsSize)
      return false;
    roomBg = m_rooms[off++];
    roomBgColor = m_rooms[off++];
    roomSong = (uint32_t)m_rooms[off] | ((uint32_t)m_rooms[off + 1] << 8) | ((uint32_t)m_rooms[off + 2] << 16) | ((uint32_t)m_rooms[off + 3] << 24);
    off += 4;
    roomTilemap = m_rooms[off++];
    objCount = m_rooms[off++];
    if(r == idx)
      break;
    uint32_t skip = (uint32_t)objCount * kRoomObjSize;
    if(off + skip > m_roomsSize)
      return false;
    off += skip;
  }

  for(int i = 0; i < kMaxObjects; i++)
  {
    if(!s_roomPersistent[i])
      m_objects[i].active = false;
  }

  for(uint8_t i = 0; i < objCount; i++)
  {
    if(off + kRoomObjSize > m_roomsSize)
      break;
    uint8_t objId = m_rooms[off++];
    int16_t x = read_s16(&m_rooms[off]); off += 2;
    int16_t y = read_s16(&m_rooms[off]); off += 2;
    uint8_t frame = m_rooms[off++];
    uint8_t state = m_rooms[off++];
    uint8_t mode = m_rooms[off++];
    int16_t angle10 = read_s16(&m_rooms[off]); off += 2;
    uint16_t scale1000 = read_u16(&m_rooms[off]); off += 2;
    uint8_t persistent = m_rooms[off++];
    if(objId >= kMaxObjects)
      continue;

    m_objects[objId].x = x;
    m_objects[objId].y = y;
    s_posX[objId] = (float)x;
    s_posY[objId] = (float)y;
    m_objects[objId].spriteId = frame;
    s_defaultSprite[objId] = frame;
    m_objects[objId].active = true;
    s_isProjectile[objId] = false;
    alarm_start_defaults_for_obj(objId, millis());
    s_angle10[objId] = (mode == 1) ? angle10 : 0;
    s_scaleBase1000[objId] = (mode == 2) ? scale1000 : 1000;
    s_scaleAmp1000[objId] = 0;
    (void)state;
    (void)persistent;
  }

  m_roomIndex = idx;
  m_roomBg = roomBg;
  m_roomBgColor = roomBgColor;
  m_roomTilemap = roomTilemap;
  m_roomSongHash = roomSong;
  return true;
}

void Runtime::begin(const MasaLoader::GameData &game)
{
  m_script = game.script;
  m_scriptSize = game.scriptSize;
  m_pc = game.entryPoint;
  m_waitUntil = 0;
  m_lastTickMs = 0;
  m_running = game.valid && m_script != NULL && m_scriptSize > 0 && m_pc < m_scriptSize;
  m_persistent = false;
  m_boundsEnabled = false;
  m_wrapEnabled = false;
  m_wrapMinX = 0;
  m_wrapMaxX = 0;
  m_wrapMinY = 0;
  m_wrapMaxY = 0;
  m_musicCmd = {0, 0, 0};
  m_musicPlaying = false;
  m_musicLoop = false;
  m_musicSong = 0;
  m_roomBgColor = 12;
  m_roomTilemap = 0xFF;
  for(int i = 0; i < kMaxObjects; i++)
    m_objects[i].active = false;
  behavior_reset();
  set_rooms(game.rooms, game.roomsSize);
}

void Runtime::reset()
{
  m_pc = 0;
  m_waitUntil = 0;
  m_lastTickMs = 0;
  m_running = m_script != NULL && m_scriptSize > 0;
  m_persistent = false;
  m_boundsEnabled = false;
  m_wrapEnabled = false;
  m_wrapMinX = 0;
  m_wrapMaxX = 0;
  m_wrapMinY = 0;
  m_wrapMaxY = 0;
  m_musicCmd = {0, 0, 0};
  m_musicPlaying = false;
  m_musicLoop = false;
  m_musicSong = 0;
  m_roomBgColor = 12;
  m_roomTilemap = 0xFF;
  for(int i = 0; i < kMaxObjects; i++)
    m_objects[i].active = false;
  behavior_reset();
  if(m_roomCount > 0)
  {
    m_persistent = true;
    set_room(0);
  }
}

void Runtime::set_audio_callback(void (*cb)(uint8_t))
{
  m_audioCb = cb;
}

void Runtime::set_beep_callback(void (*cb)(uint16_t, uint16_t))
{
  m_beepCb = cb;
}

void Runtime::set_beep_ex_callback(void (*cb)(uint8_t, uint16_t, uint16_t))
{
  m_beepExCb = cb;
}

bool Runtime::poll_music_cmd(MusicCmd &out)
{
  if(m_musicCmd.type == 0)
    return false;
  out = m_musicCmd;
  m_musicCmd.type = 0;
  return true;
}

void Runtime::step(uint32_t nowMs, CommandQueue &out)
{
  if(!m_running && !m_persistent)
    return;
  if(m_running && nowMs < m_waitUntil)
    return;

  const uint32_t kMaxOpsPerStep = 32;
  uint32_t ops = 0;

  while(m_running && m_pc < m_scriptSize && ops < kMaxOpsPerStep)
  {
    ops++;
    uint8_t op = m_script[m_pc++];
    switch(op)
    {
      case MasaFormat::OP_NOP:
        break;
      case MasaFormat::OP_DRAW_SPRITE:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t id = m_script[m_pc++];
        out.push(RENDER_DRAW_SPRITE, x, y, id, 0, 1000);
        break;
      }
      case MasaFormat::OP_DRAW_SPRITE_XFORM:
      {
        if(m_pc + 9 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t id = m_script[m_pc++];
        int16_t angle10 = read_s16(&m_script[m_pc]); m_pc += 2;
        uint16_t scale1000 = read_u16(&m_script[m_pc]); m_pc += 2;
        out.push(RENDER_DRAW_SPRITE_XFORM, x, y, id, angle10, scale1000);
        break;
      }
      case 6: // OP_SET_OBJECT
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t spr = m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          m_objects[obj].x = x;
          m_objects[obj].y = y;
          s_posX[obj] = (float)x;
          s_posY[obj] = (float)y;
          s_prevPosX[obj] = s_posX[obj];
          s_prevPosY[obj] = s_posY[obj];
          m_objects[obj].spriteId = spr;
          s_defaultSprite[obj] = spr;
          m_objects[obj].active = true;
          s_isProjectile[obj] = false;
          alarm_start_defaults_for_obj(obj, nowMs);
          s_accel10[obj] = 0;
          s_friction1000[obj] = 1000;
          s_turnSpeed10[obj] = 0;
          s_thrust10[obj] = 0;
          s_angle10[obj] = 0;
          s_angleSpeed10[obj] = 0;
          s_turnSpeed10[obj] = 0;
          s_vx10[obj] = 0;
          s_vy10[obj] = 0;
          s_vxCarry[obj] = 0.0f;
          s_vyCarry[obj] = 0.0f;
          s_inputSpeed10[obj] = 0;
          s_accel10[obj] = 0;
          s_friction1000[obj] = 1000;
          s_thrust10[obj] = 0;
          s_scaleBase1000[obj] = 1000;
          s_scaleAmp1000[obj] = 0;
          s_scalePhase[obj] = 0.0f;
          s_scaleSpeedRadPerMs[obj] = 0.0f;
          s_animCount[obj] = 0;
          s_animIndex[obj] = 0;
          s_animFps[obj] = 0;
          s_animNextMs[obj] = 0;
        }
        m_persistent = true;
        break;
      }
      case 7: // OP_SET_VEL
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t vx10 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t vy10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_vx10[obj] = vx10;
          s_vy10[obj] = vy10;
          s_vxCarry[obj] = 0.0f;
          s_vyCarry[obj] = 0.0f;
        }
        m_persistent = true;
        break;
      }
      case 8: // OP_SET_BOUNDS
      {
        if(m_pc + 8 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        m_boundsMinX = read_s16(&m_script[m_pc]); m_pc += 2;
        m_boundsMaxX = read_s16(&m_script[m_pc]); m_pc += 2;
        m_boundsMinY = read_s16(&m_script[m_pc]); m_pc += 2;
        m_boundsMaxY = read_s16(&m_script[m_pc]); m_pc += 2;
        m_boundsEnabled = true;
        m_persistent = true;
        break;
      }
      case 9: // OP_SET_ROT_SPEED
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t ang10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_angleSpeed10[obj] = ang10;
        }
        m_persistent = true;
        break;
      }
      case 10: // OP_SET_SCALE_PULSE
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint16_t base1000 = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t amp1000 = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t speed10 = read_u16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_scaleBase1000[obj] = base1000;
          s_scaleAmp1000[obj] = amp1000;
          float speedDegPerFrame = ((float)speed10) * 0.1f;
          const float kPi = 3.14159265f;
          float speedRadPerMs = (speedDegPerFrame * kPi / 180.0f) / 16.0f;
          s_scaleSpeedRadPerMs[obj] = speedRadPerMs;
        }
        m_persistent = true;
        break;
      }
      case 11: // OP_SET_ANIM
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t fps = m_script[m_pc++];
        uint8_t count = m_script[m_pc++];
        if(m_pc + count > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(obj < kMaxObjects)
        {
          if(count > 16)
            count = 16;
          s_animCount[obj] = count;
          s_animIndex[obj] = 0;
          s_animFps[obj] = fps;
          s_animNextMs[obj] = 0;
          for(uint8_t i = 0; i < count; i++)
            s_animFrames[obj][i] = m_script[m_pc + i];
        }
        m_pc += count;
        m_persistent = true;
        break;
      }
      case 12: // OP_SET_INPUT
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t speed10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_inputSpeed10[obj] = speed10;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_ROTATE:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t speed10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
          s_turnSpeed10[obj] = speed10;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_THRUST:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t thrust10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
          s_thrust10[obj] = thrust10;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_WRAP:
      {
        if(m_pc + 8 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        m_wrapMinX = read_s16(&m_script[m_pc]); m_pc += 2;
        m_wrapMaxX = read_s16(&m_script[m_pc]); m_pc += 2;
        m_wrapMinY = read_s16(&m_script[m_pc]); m_pc += 2;
        m_wrapMaxY = read_s16(&m_script[m_pc]); m_pc += 2;
        m_wrapEnabled = true;
        m_boundsEnabled = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_NO_WRAP:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t noWrap = m_script[m_pc++];
        if(obj < kMaxObjects)
          s_noWrap[obj] = (noWrap != 0);
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_BOUNCE:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t enabled = m_script[m_pc++];
        if(obj < kMaxObjects)
          s_bounceEnabled[obj] = (enabled != 0);
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_VEL_RANDOM:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t vmin10 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t vmax10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_velRandomEnabled[obj] = true;
          s_velRandomMin10[obj] = vmin10;
          s_velRandomMax10[obj] = vmax10;
          s_vx10[obj] = random_vel10_for_obj(obj);
          s_vy10[obj] = random_vel10_for_obj(obj);
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_SPRITE:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t spr = m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          m_objects[obj].spriteId = spr;
          s_defaultSprite[obj] = spr;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_POS_X:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_posX[obj] = (float)x;
          m_objects[obj].x = x;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_POS_Y:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          s_posY[obj] = (float)y;
          m_objects[obj].y = y;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_ACCEL:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t accel10 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t friction1000 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          if(friction1000 < 0)
            friction1000 = 0;
          if(friction1000 > 1000)
            friction1000 = 1000;
          s_accel10[obj] = accel10;
          s_friction1000[obj] = (uint16_t)friction1000;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_TEXT_SET:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(slot < kMaxTextSlots)
        {
          if(len > kMaxTextLen)
            len = kMaxTextLen;
          s_textVisible[slot] = true;
          s_textX[slot] = x;
          s_textY[slot] = y;
          s_textColor[slot] = color;
          s_textLen[slot] = len;
          for(uint8_t i = 0; i < len; i++)
            s_textStr[slot][i] = (char)m_script[m_pc + i];
          s_textStr[slot][len] = '\0';
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_TEXT_CLEAR:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxTextSlots)
          s_textVisible[slot] = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SHAPE_SET:
      {
        if(m_pc + 15 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t type = m_script[m_pc++];
        int16_t x1 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y1 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t x2 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y2 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t x3 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y3 = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        if(slot < kMaxShapeSlots)
        {
          s_shapeVisible[slot] = true;
          s_shapeType[slot] = type;
          s_shapeX1[slot] = x1;
          s_shapeY1[slot] = y1;
          s_shapeX2[slot] = x2;
          s_shapeY2[slot] = y2;
          s_shapeX3[slot] = x3;
          s_shapeY3[slot] = y3;
          s_shapeColor[slot] = color;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SHAPE_CLEAR:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxShapeSlots)
          s_shapeVisible[slot] = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SPAWN_OBJECT:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t spr = m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          m_objects[obj].x = x;
          m_objects[obj].y = y;
          s_posX[obj] = (float)x;
          s_posY[obj] = (float)y;
          s_prevPosX[obj] = s_posX[obj];
          s_prevPosY[obj] = s_posY[obj];
          m_objects[obj].spriteId = spr;
          s_defaultSprite[obj] = spr;
          m_objects[obj].active = true;
          s_isProjectile[obj] = false;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_DESTROY_OBJECT:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          m_objects[obj].active = false;
          s_isProjectile[obj] = false;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_HITBOX:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t w = m_script[m_pc++];
        uint8_t h = m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          s_hitW[obj] = (w == 0) ? 1 : w;
          s_hitH[obj] = (h == 0) ? 1 : h;
          s_hitOffX[obj] = 0;
          s_hitOffY[obj] = 0;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_HITBOX_EX:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t w = m_script[m_pc++];
        uint8_t h = m_script[m_pc++];
        int8_t offX = (int8_t)m_script[m_pc++];
        int8_t offY = (int8_t)m_script[m_pc++];
        if(obj < kMaxObjects)
        {
          s_hitW[obj] = (w == 0) ? 1 : w;
          s_hitH[obj] = (h == 0) ? 1 : h;
          s_hitOffX[obj] = offX;
          s_hitOffY[obj] = offY;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_COLLIDE_SIGNAL:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t objA = m_script[m_pc++];
        uint8_t objB = m_script[m_pc++];
        if(s_collideCount < kMaxColliders && slot < kMaxSignals)
        {
          s_collideSlot[s_collideCount] = slot;
          s_collideA[s_collideCount] = objA;
          s_collideB[s_collideCount] = objB;
          s_collideCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_DESTROY:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = (obj == 0xFF) ? kSignalActionDestroyOther : kSignalActionDestroy;
          s_actionObj[s_actionCount] = obj;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_SPAWN:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t spr = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionSpawn;
          s_actionObj[s_actionCount] = obj;
          s_actionX[s_actionCount] = x;
          s_actionY[s_actionCount] = y;
          s_actionSprite[s_actionCount] = spr;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
          if(obj < kMaxObjects)
            s_spawnTargetAllowed[slot][obj] = true;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_SOUND:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t sid = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionSound;
          s_actionSound[s_actionCount] = sid;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_TEXTBOX_SET:
      {
        if(m_pc + 11 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t w = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t h = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(slot < kMaxTextBoxes)
        {
          if(len > kMaxTextBoxLen)
            len = kMaxTextBoxLen;
          s_textBoxVisible[slot] = true;
          s_textBoxX[slot] = x;
          s_textBoxY[slot] = y;
          s_textBoxW[slot] = w;
          s_textBoxH[slot] = h;
          s_textBoxColor[slot] = color;
          s_textBoxLen[slot] = len;
          for(uint8_t i = 0; i < len; i++)
            s_textBoxStr[slot][i] = (char)m_script[m_pc + i];
          s_textBoxStr[slot][len] = '\0';
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_TEXTBOX_CLEAR:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxTextBoxes)
          s_textBoxVisible[slot] = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_CHOICES_SET:
      {
        if(m_pc + 8 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t count = m_script[m_pc++];
        uint8_t baseSignal = m_script[m_pc++];
        if(slot < kMaxChoiceSlots)
        {
          s_choiceVisible[slot] = true;
          s_choiceX[slot] = x;
          s_choiceY[slot] = y;
          s_choiceColor[slot] = color;
          s_choiceCount[slot] = (count > kMaxChoiceItems) ? kMaxChoiceItems : count;
          s_choiceSelected[slot] = 0;
          s_choiceBaseSignal[slot] = baseSignal;
          s_choicePrevUp[slot] = false;
          s_choicePrevDown[slot] = false;
          s_choicePrevConfirm[slot] = false;
          s_choiceOwner[slot] = s_actionOwnerCur;
        }
        for(uint8_t i = 0; i < count; i++)
        {
          if(m_pc + 1 > m_scriptSize)
          {
            m_running = false;
            return;
          }
          uint8_t len = m_script[m_pc++];
          if(m_pc + len > m_scriptSize)
          {
            m_running = false;
            return;
          }
          if(slot < kMaxChoiceSlots && i < kMaxChoiceItems)
          {
            if(len > kMaxChoiceLen)
              len = kMaxChoiceLen;
            s_choiceLen[slot][i] = len;
            for(uint8_t j = 0; j < len; j++)
              s_choiceText[slot][i][j] = (char)m_script[m_pc + j];
            s_choiceText[slot][i][len] = '\0';
          }
          m_pc += len;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_CHOICES_CLEAR:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxChoiceSlots)
          s_choiceVisible[slot] = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_ROOM_NEXT:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionRoomNext;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_ROOM_GOTO:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t room = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionRoomGoto;
          s_actionObj[s_actionCount] = room;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_SPAWN_BULLET:
      {
        if(m_pc + 8 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t srcObj = m_script[m_pc++];
        uint8_t bulletObj = m_script[m_pc++];
        int16_t speed10 = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t offset = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t frame = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionSpawnBullet;
          s_actionObj[s_actionCount] = srcObj;
          s_actionSprite[s_actionCount] = bulletObj;
          s_actionSpeed10[s_actionCount] = speed10;
          s_actionOffset[s_actionCount] = offset;
          s_actionColor[s_actionCount] = frame;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_BEEP:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint16_t hz = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionBeep;
          s_actionBeepWave[s_actionCount] = 0;
          s_actionBeepHz[s_actionCount] = hz;
          s_actionBeepMs[s_actionCount] = ms;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_BEEP_WAVE:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t wave = m_script[m_pc++];
        uint16_t hz = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionBeep;
          s_actionBeepWave[s_actionCount] = wave;
          s_actionBeepHz[s_actionCount] = hz;
          s_actionBeepMs[s_actionCount] = ms;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_BEEP:
      {
        if(m_pc + 4 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint16_t hz = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        if(hz > 0 && ms > 0)
        {
          if(m_beepExCb)
            m_beepExCb(0, hz, ms);
          else if(m_beepCb)
            m_beepCb(hz, ms);
        }
        break;
      }
      case MasaFormat::OP_BEEP_WAVE:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t wave = m_script[m_pc++];
        uint16_t hz = read_u16(&m_script[m_pc]); m_pc += 2;
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        if(hz > 0 && ms > 0)
        {
          if(m_beepExCb)
            m_beepExCb(wave, hz, ms);
          else if(m_beepCb)
            m_beepCb(hz, ms);
        }
        break;
      }
      case MasaFormat::OP_SIGNAL_STOP:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionStop;
          s_actionObj[s_actionCount] = obj;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_TEXTBOX:
      {
        if(m_pc + 12 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t boxSlot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t w = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t h = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionTextBox;
          s_actionObj[s_actionCount] = boxSlot;
          s_actionX[s_actionCount] = x;
          s_actionY[s_actionCount] = y;
          s_actionW[s_actionCount] = w;
          s_actionH[s_actionCount] = h;
          s_actionColor[s_actionCount] = color;
          if(len > kMaxTextBoxLen)
            len = kMaxTextBoxLen;
          s_actionTextLen[s_actionCount] = len;
          for(uint8_t i = 0; i < len; i++)
            s_actionText[s_actionCount][i] = (char)m_script[m_pc + i];
          s_actionText[s_actionCount][len] = '\0';
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_CHOICES:
      {
        if(m_pc + 9 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t choiceSlot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t count = m_script[m_pc++];
        uint8_t baseSignal = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionChoices;
          s_actionObj[s_actionCount] = choiceSlot;
          s_actionX[s_actionCount] = x;
          s_actionY[s_actionCount] = y;
          s_actionColor[s_actionCount] = color;
          s_actionCountItems[s_actionCount] = count;
          s_actionBaseSignal[s_actionCount] = baseSignal;
          s_actionChoiceCount[s_actionCount] = (count > kMaxChoiceItems) ? kMaxChoiceItems : count;
          for(uint8_t j = 0; j < kMaxChoiceItems; j++)
          {
            s_actionChoiceLen[s_actionCount][j] = 0;
            s_actionChoiceText[s_actionCount][j][0] = '\0';
          }
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
        }
        for(uint8_t i = 0; i < count; i++)
        {
          if(m_pc + 1 > m_scriptSize)
          {
            m_running = false;
            return;
          }
          uint8_t len = m_script[m_pc++];
          if(m_pc + len > m_scriptSize)
          {
            m_running = false;
            return;
          }
          if(s_actionCount < kMaxSignalActions && slot < kMaxSignals && i < kMaxChoiceItems)
          {
            if(len > kMaxChoiceLen)
              len = kMaxChoiceLen;
            s_actionChoiceLen[s_actionCount][i] = len;
            for(uint8_t j = 0; j < len; j++)
              s_actionChoiceText[s_actionCount][i][j] = (char)m_script[m_pc + j];
            s_actionChoiceText[s_actionCount][i][len] = '\0';
          }
          m_pc += len;
        }
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
          s_actionCount++;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_TEXTBOX_CLEAR:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t boxSlot = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionTextBoxClear;
          s_actionObj[s_actionCount] = boxSlot;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_CHOICES_CLEAR:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t choiceSlot = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionChoicesClear;
          s_actionObj[s_actionCount] = choiceSlot;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_SET_INPUT:
      {
        if(m_pc + 4 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        int16_t speed10 = read_s16(&m_script[m_pc]); m_pc += 2;
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionSetInput;
          s_actionObj[s_actionCount] = obj;
          s_actionSpeed10[s_actionCount] = speed10;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_HUD_ADD:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t life = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t score = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t coins = read_s16(&m_script[m_pc]); m_pc += 2;
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionHudAdd;
          s_actionX[s_actionCount] = life;
          s_actionY[s_actionCount] = score;
          s_actionW[s_actionCount] = coins;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_GAME_OVER_UI:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t l1 = m_script[m_pc++];
        uint8_t l2 = m_script[m_pc++];
        uint8_t l3 = m_script[m_pc++];
        if(m_pc + (uint32_t)l1 + (uint32_t)l2 + (uint32_t)l3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t c1 = (l1 > kMaxTextLen) ? kMaxTextLen : l1;
        uint8_t c2 = (l2 > kMaxTextLen) ? kMaxTextLen : l2;
        uint8_t c3 = (l3 > kMaxTextLen) ? kMaxTextLen : l3;
        memcpy(s_gameOverText, &m_script[m_pc], c1);
        s_gameOverText[c1] = '\0';
        m_pc += l1;
        memcpy(s_gameOverScorePrefix, &m_script[m_pc], c2);
        s_gameOverScorePrefix[c2] = '\0';
        m_pc += l2;
        memcpy(s_gameOverRestartText, &m_script[m_pc], c3);
        s_gameOverRestartText[c3] = '\0';
        m_pc += l3;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_TEXT_SET:
      {
        if(m_pc + 8 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t textSlot = m_script[m_pc++];
        int16_t tx = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t ty = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t col = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionShowText;
          s_actionObj[s_actionCount] = textSlot;
          s_actionX[s_actionCount] = tx;
          s_actionY[s_actionCount] = ty;
          s_actionW[s_actionCount] = 0;
          s_actionColor[s_actionCount] = col;
          uint8_t cpy = (len > kMaxTextBoxLen) ? kMaxTextBoxLen : len;
          s_actionTextLen[s_actionCount] = cpy;
          for(uint8_t j = 0; j < cpy; j++)
            s_actionText[s_actionCount][j] = (char)m_script[m_pc + j];
          s_actionText[s_actionCount][cpy] = '\0';
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_TEXT_SET_EX:
      {
        if(m_pc + 9 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t textSlot = m_script[m_pc++];
        int16_t tx = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t ty = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t col = m_script[m_pc++];
        uint8_t align = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionShowText;
          s_actionObj[s_actionCount] = textSlot;
          s_actionX[s_actionCount] = tx;
          s_actionY[s_actionCount] = ty;
          s_actionColor[s_actionCount] = col;
          s_actionW[s_actionCount] = (int16_t)(align > 2 ? 0 : align);
          uint8_t cpy = (len > kMaxTextBoxLen) ? kMaxTextBoxLen : len;
          s_actionTextLen[s_actionCount] = cpy;
          for(uint8_t j = 0; j < cpy; j++)
            s_actionText[s_actionCount][j] = (char)m_script[m_pc + j];
          s_actionText[s_actionCount][cpy] = '\0';
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SIGNAL_TEXT_CLEAR:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t textSlot = m_script[m_pc++];
        if(s_actionCount < kMaxSignalActions && slot < kMaxSignals)
        {
          s_actionSlot[s_actionCount] = slot;
          s_actionType[s_actionCount] = kSignalActionShowTextClear;
          s_actionObj[s_actionCount] = textSlot;
          s_actionOwner[s_actionCount] = s_actionOwnerCur;
          s_actionCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_INPUT_BIND:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint8_t ev = m_script[m_pc++];
        uint8_t btn = m_script[m_pc++];
        if(s_inputBindCount < kMaxInputBinds && slot < kMaxSignals)
        {
          s_inputBindSlot[s_inputBindCount] = slot;
          s_inputBindEvent[s_inputBindCount] = ev;
          s_inputBindButton[s_inputBindCount] = btn;
          s_inputBindOwner[s_inputBindCount] = s_actionOwnerCur;
          s_inputBindCount++;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SET_ACTION_OWNER:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        s_actionOwnerCur = (obj < kMaxObjects) ? obj : 0xFF;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_BG_SCROLL_X:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        int16_t vx10 = read_s16(&m_script[m_pc]); m_pc += 2;
        s_bgScrollX10 = vx10;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_BG_SCROLL_Y:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        int16_t vy10 = read_s16(&m_script[m_pc]); m_pc += 2;
        s_bgScrollY10 = vy10;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_START:
      {
        if(m_pc + 4 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        uint8_t repeat = m_script[m_pc++];
        // Legacy global alarm (use object 0).
        if(slot < kMaxAlarms)
        {
          s_alarmActive[0][slot] = true;
          s_alarmRepeat[0][slot] = repeat ? true : false;
          s_alarmPeriodMs[0][slot] = ms;
          s_alarmNextMs[0][slot] = nowMs + (uint32_t)ms;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_STOP:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxAlarms)
          s_alarmActive[0][slot] = false;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_SIGNAL:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t alarm = m_script[m_pc++];
        uint8_t signal = m_script[m_pc++];
        if(alarm < kMaxAlarms)
          s_alarmSignal[0][alarm] = signal;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_START_OBJ:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t slot = m_script[m_pc++];
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        uint8_t repeat = m_script[m_pc++];
        if(obj < kMaxObjects && slot < kMaxAlarms)
        {
          s_alarmDefaultMs[obj][slot] = ms;
          s_alarmDefaultRepeat[obj][slot] = repeat ? true : false;
          if(m_objects[obj].active)
          {
            s_alarmActive[obj][slot] = true;
            s_alarmRepeat[obj][slot] = s_alarmDefaultRepeat[obj][slot];
            s_alarmPeriodMs[obj][slot] = s_alarmDefaultMs[obj][slot];
            s_alarmNextMs[obj][slot] = nowMs + (uint32_t)ms;
          }
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_STOP_OBJ:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t slot = m_script[m_pc++];
        if(obj < kMaxObjects && slot < kMaxAlarms)
        {
          s_alarmActive[obj][slot] = false;
          s_alarmDefaultMs[obj][slot] = 0;
          s_alarmDefaultRepeat[obj][slot] = false;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_ALARM_SIGNAL_OBJ:
      {
        if(m_pc + 3 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        uint8_t alarm = m_script[m_pc++];
        uint8_t signal = m_script[m_pc++];
        if(obj < kMaxObjects && alarm < kMaxAlarms)
          s_alarmSignal[obj][alarm] = signal;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_MUSIC_SIGNAL:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        if(slot < kMaxSignals)
        {
          s_musicSignalSlot = slot;
          s_musicSignalOwner = s_actionOwnerCur;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_PLAY_MUSIC:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t song = m_script[m_pc++];
        m_musicSong = song;
        m_musicPlaying = true;
        m_musicCmd = {1, song, (uint8_t)(m_musicLoop ? 1 : 0)};
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_STOP_MUSIC:
      {
        m_musicPlaying = false;
        m_musicCmd = {2, m_musicSong, (uint8_t)(m_musicLoop ? 1 : 0)};
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_PAUSE_MUSIC:
      {
        m_musicPlaying = false;
        m_musicCmd = {3, m_musicSong, (uint8_t)(m_musicLoop ? 1 : 0)};
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SONG_LOOP:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t loop = m_script[m_pc++];
        m_musicLoop = loop ? true : false;
        m_musicCmd = {4, m_musicSong, (uint8_t)(m_musicLoop ? 1 : 0)};
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_HUD_SET:
      {
        if(m_pc + 12 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        s_hudLife = read_s32(&m_script[m_pc]); m_pc += 4;
        s_hudScore = read_s32(&m_script[m_pc]); m_pc += 4;
        s_hudCoins = read_s32(&m_script[m_pc]); m_pc += 4;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_HUD_ADD:
      {
        if(m_pc + 12 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        s_hudLife += read_s32(&m_script[m_pc]); m_pc += 4;
        s_hudScore += read_s32(&m_script[m_pc]); m_pc += 4;
        s_hudCoins += read_s32(&m_script[m_pc]); m_pc += 4;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_HUD_DRAW:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        s_hudX = read_s16(&m_script[m_pc]); m_pc += 2;
        s_hudY = read_s16(&m_script[m_pc]); m_pc += 2;
        s_hudColor = m_script[m_pc++];
        s_hudEnabled = true;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_HUD_STYLE:
      {
        if(m_pc + 12 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        s_hudX = read_s16(&m_script[m_pc]); m_pc += 2;
        s_hudY = read_s16(&m_script[m_pc]); m_pc += 2;
        s_hudColor = m_script[m_pc++];
        s_hudAlign = m_script[m_pc++];
        s_hudBgColor = m_script[m_pc++];
        s_hudPadX = read_s16(&m_script[m_pc]); m_pc += 2;
        s_hudPadY = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(len > kMaxHudTemplateLen)
          len = kMaxHudTemplateLen;
        for(uint8_t i = 0; i < len; i++)
          s_hudFormat[i] = (char)m_script[m_pc + i];
        s_hudFormat[len] = '\0';
        m_pc += len;
        if(s_hudAlign > 2)
          s_hudAlign = 0;
        if(s_hudPadX < 0) s_hudPadX = 0;
        if(s_hudPadY < 0) s_hudPadY = 0;
        s_hudEnabled = true;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_SET:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t val = read_s32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varGlobal[idx] = val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varObj[obj][idx] = val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_ADD:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t val = read_s32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varGlobal[idx] += val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varObj[obj][idx] += val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_TEXT:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(slot < kMaxTextSlots)
        {
          s_varTextVisible[slot] = true;
          s_varTextX[slot] = x;
          s_varTextY[slot] = y;
          s_varTextColor[slot] = color;
          s_varTextScope[slot] = scope;
          s_varTextObj[slot] = obj;
          s_varTextIndex[slot] = idx;
          if(len > kMaxTextLen)
            len = kMaxTextLen;
          for(uint8_t i = 0; i < len; i++)
            s_varTextLabel[slot][i] = (char)m_script[m_pc + i];
          s_varTextLabel[slot][len] = '\0';
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_SET:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float val = read_f32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varfGlobal[idx] = val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varfObj[obj][idx] = val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_ADD:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float val = read_f32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varfGlobal[idx] += val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varfObj[obj][idx] += val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_TEXT:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(slot < kMaxTextSlots)
        {
          s_varfTextVisible[slot] = true;
          s_varfTextX[slot] = x;
          s_varfTextY[slot] = y;
          s_varfTextColor[slot] = color;
          s_varfTextScope[slot] = scope;
          s_varfTextObj[slot] = obj;
          s_varfTextIndex[slot] = idx;
          if(len > kMaxTextLen)
            len = kMaxTextLen;
          for(uint8_t i = 0; i < len; i++)
            s_varfTextLabel[slot][i] = (char)m_script[m_pc + i];
          s_varfTextLabel[slot][len] = '\0';
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_IF_EQ:
      case MasaFormat::OP_IF_GT:
      case MasaFormat::OP_IF_LT:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t val = read_s32(&m_script[m_pc]); m_pc += 4;
        uint8_t sig = m_script[m_pc++];
        int32_t cur = 0;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            cur = s_varGlobal[idx];
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            cur = s_varObj[obj][idx];
        }
        bool pass = false;
        if(op == MasaFormat::OP_IF_EQ) pass = (cur == val);
        else if(op == MasaFormat::OP_IF_GT) pass = (cur > val);
        else if(op == MasaFormat::OP_IF_LT) pass = (cur < val);
        if(sig < kMaxSignals)
        {
          s_signalActive[sig] = pass;
          s_signalSource[sig] = s_actionOwnerCur;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_IF_EQF:
      case MasaFormat::OP_IF_GTF:
      case MasaFormat::OP_IF_LTF:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float val = read_f32(&m_script[m_pc]); m_pc += 4;
        uint8_t sig = m_script[m_pc++];
        float cur = 0.0f;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            cur = s_varfGlobal[idx];
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            cur = s_varfObj[obj][idx];
        }
        bool pass = false;
        if(op == MasaFormat::OP_IF_EQF) pass = (fabsf(cur - val) < 0.0001f);
        else if(op == MasaFormat::OP_IF_GTF) pass = (cur > val);
        else if(op == MasaFormat::OP_IF_LTF) pass = (cur < val);
        if(sig < kMaxSignals)
        {
          s_signalActive[sig] = pass;
          s_signalSource[sig] = s_actionOwnerCur;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_CLAMP:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t minv = read_s16(&m_script[m_pc]); m_pc += 2;
        int32_t maxv = read_s16(&m_script[m_pc]); m_pc += 2;
        if(minv > maxv)
        {
          int32_t t = minv;
          minv = maxv;
          maxv = t;
        }
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
          {
            if(s_varGlobal[idx] < minv) s_varGlobal[idx] = minv;
            if(s_varGlobal[idx] > maxv) s_varGlobal[idx] = maxv;
          }
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
          {
            if(s_varObj[obj][idx] < minv) s_varObj[obj][idx] = minv;
            if(s_varObj[obj][idx] > maxv) s_varObj[obj][idx] = maxv;
          }
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_CLAMP:
      {
        if(m_pc + 11 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float minv = read_f32(&m_script[m_pc]); m_pc += 4;
        float maxv = read_f32(&m_script[m_pc]); m_pc += 4;
        if(minv > maxv)
        {
          float t = minv;
          minv = maxv;
          maxv = t;
        }
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
          {
            if(s_varfGlobal[idx] < minv) s_varfGlobal[idx] = minv;
            if(s_varfGlobal[idx] > maxv) s_varfGlobal[idx] = maxv;
          }
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
          {
            if(s_varfObj[obj][idx] < minv) s_varfObj[obj][idx] = minv;
            if(s_varfObj[obj][idx] > maxv) s_varfObj[obj][idx] = maxv;
          }
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_RAND:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t minv = read_s16(&m_script[m_pc]); m_pc += 2;
        int32_t maxv = read_s16(&m_script[m_pc]); m_pc += 2;
        if(minv > maxv)
        {
          int32_t t = minv;
          minv = maxv;
          maxv = t;
        }
        int32_t val = minv;
        if(maxv > minv)
          val = minv + (int32_t)(random((int)(maxv - minv + 1)));
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varGlobal[idx] = val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varObj[obj][idx] = val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_LERP:
      {
        if(m_pc + 15 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float a = read_f32(&m_script[m_pc]); m_pc += 4;
        float b = read_f32(&m_script[m_pc]); m_pc += 4;
        float t = read_f32(&m_script[m_pc]); m_pc += 4;
        if(t < 0.0f) t = 0.0f;
        if(t > 1.0f) t = 1.0f;
        float val = a + (b - a) * t;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varfGlobal[idx] = val;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varfObj[obj][idx] = val;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VAR_MIN:
      case MasaFormat::OP_VAR_MAX:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t val = read_s32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varGlobal[idx] = (op == MasaFormat::OP_VAR_MIN) ? min(s_varGlobal[idx], val) : max(s_varGlobal[idx], val);
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varObj[obj][idx] = (op == MasaFormat::OP_VAR_MIN) ? min(s_varObj[obj][idx], val) : max(s_varObj[obj][idx], val);
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_MIN:
      case MasaFormat::OP_VARF_MAX:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float val = read_f32(&m_script[m_pc]); m_pc += 4;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varfGlobal[idx] = (op == MasaFormat::OP_VARF_MIN) ? min(s_varfGlobal[idx], val) : max(s_varfGlobal[idx], val);
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varfObj[obj][idx] = (op == MasaFormat::OP_VARF_MIN) ? min(s_varfObj[obj][idx], val) : max(s_varfObj[obj][idx], val);
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_VARF_SIN:
      case MasaFormat::OP_VARF_COS:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        float val = read_f32(&m_script[m_pc]); m_pc += 4;
        float rad = val * 0.0174532925f;
        float out = (op == MasaFormat::OP_VARF_SIN) ? sinf(rad) : cosf(rad);
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            s_varfGlobal[idx] = out;
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            s_varfObj[obj][idx] = out;
        }
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_STR_SET:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(len > kMaxTextLen)
          len = kMaxTextLen;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
          {
            for(uint8_t i = 0; i < len; i++)
              s_strGlobal[idx][i] = (char)m_script[m_pc + i];
            s_strGlobal[idx][len] = '\0';
          }
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
          {
            for(uint8_t i = 0; i < len; i++)
              s_strObj[obj][idx][i] = (char)m_script[m_pc + i];
            s_strObj[obj][idx][len] = '\0';
          }
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_STR_TEXT:
      {
        if(m_pc + 7 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t slot = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        uint8_t color = m_script[m_pc++];
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        uint8_t len = m_script[m_pc++];
        if(m_pc + len > m_scriptSize)
        {
          m_running = false;
          return;
        }
        if(slot < kMaxTextSlots)
        {
          s_strTextVisible[slot] = true;
          s_strTextX[slot] = x;
          s_strTextY[slot] = y;
          s_strTextColor[slot] = color;
          s_strTextScope[slot] = scope;
          s_strTextObj[slot] = obj;
          s_strTextIndex[slot] = idx;
          if(len > kMaxTextLen)
            len = kMaxTextLen;
          for(uint8_t i = 0; i < len; i++)
            s_strTextLabel[slot][i] = (char)m_script[m_pc + i];
          s_strTextLabel[slot][len] = '\0';
        }
        m_pc += len;
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_SWITCH:
      {
        if(m_pc + 6 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t scope = m_script[m_pc++];
        uint8_t obj = m_script[m_pc++];
        uint8_t idx = m_script[m_pc++];
        int32_t val = read_s32(&m_script[m_pc]); m_pc += 4;
        uint8_t sig = m_script[m_pc++];
        int32_t cur = 0;
        if(scope == 0)
        {
          if(idx < kMaxGlobalVars)
            cur = s_varGlobal[idx];
        }
        else
        {
          if(obj < kMaxObjects && idx < kMaxVarsPerObj)
            cur = s_varObj[obj][idx];
        }
        if(sig < kMaxSignals)
          s_signalActive[sig] = (cur == val);
        m_persistent = true;
        break;
      }
      case MasaFormat::OP_MOVE_OBJECT:
      {
        if(m_pc + 5 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t obj = m_script[m_pc++];
        int16_t x = read_s16(&m_script[m_pc]); m_pc += 2;
        int16_t y = read_s16(&m_script[m_pc]); m_pc += 2;
        if(obj < kMaxObjects)
        {
          m_objects[obj].x = x;
          m_objects[obj].y = y;
          s_posX[obj] = (float)x;
          s_posY[obj] = (float)y;
          s_prevPosX[obj] = s_posX[obj];
          s_prevPosY[obj] = s_posY[obj];
          m_objects[obj].active = true;
        }
        break;
      }
      case MasaFormat::OP_PLAY_SOUND:
      {
        if(m_pc + 1 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint8_t sid = m_script[m_pc++];
        if(m_audioCb)
          m_audioCb(sid);
        break;
      }
      case MasaFormat::OP_WAIT:
      {
        if(m_pc + 2 > m_scriptSize)
        {
          m_running = false;
          return;
        }
        uint16_t ms = read_u16(&m_script[m_pc]); m_pc += 2;
        m_waitUntil = nowMs + (uint32_t)ms;
        break;
      }
      case MasaFormat::OP_END:
      default:
        m_running = false;
        break;
    }
  }

  if(m_persistent)
  {
    if(m_lastTickMs == 0)
      m_lastTickMs = nowMs;
    uint32_t dtMs = nowMs - m_lastTickMs;
    if(dtMs == 0)
      dtMs = 1;
    m_lastTickMs = nowMs;

    float t = (float)dtMs / 16.0f;
    for(int i = 0; i < kMaxObjects; i++)
    {
      if(!m_objects[i].active)
        continue;

      if(s_inputSpeed10[i] != 0)
      {
        float move = ((float)s_inputSpeed10[i]) * 0.1f * t;
        if(s_inputMask & INPUT_LEFT)
          s_posX[i] -= move;
        if(s_inputMask & INPUT_RIGHT)
          s_posX[i] += move;
        if(s_inputMask & INPUT_UP)
          s_posY[i] -= move;
        if(s_inputMask & INPUT_DOWN)
          s_posY[i] += move;
      }
      if(s_turnSpeed10[i] != 0)
      {
        float turn = ((float)s_turnSpeed10[i]) * t;
        if(s_inputMask & INPUT_LEFT)
          s_angle10[i] = (int16_t)(s_angle10[i] - turn);
        if(s_inputMask & INPUT_RIGHT)
          s_angle10[i] = (int16_t)(s_angle10[i] + turn);
      }
      if(s_thrust10[i] != 0 && (s_inputMask & INPUT_UP))
      {
        float deg = ((float)s_angle10[i]) * 0.1f;
        float rad = deg * 3.14159265f / 180.0f;
        // OP_SET_THRUST stores value in hundredths to allow finer decimals.
        float accel10 = ((float)s_thrust10[i]) * 0.1f * t;
        float addX = cosf(rad) * accel10 + s_vxCarry[i];
        float addY = sinf(rad) * accel10 + s_vyCarry[i];
        int16_t dX = (int16_t)roundf(addX);
        int16_t dY = (int16_t)roundf(addY);
        s_vxCarry[i] = addX - (float)dX;
        s_vyCarry[i] = addY - (float)dY;
        s_vx10[i] = (int16_t)(s_vx10[i] + dX);
        s_vy10[i] = (int16_t)(s_vy10[i] + dY);
      }
      if(s_accel10[i] != 0)
      {
        float accel = (float)s_accel10[i] * t;
        float addX = 0.0f;
        float addY = 0.0f;
        if(s_inputMask & INPUT_LEFT)
          addX -= accel;
        if(s_inputMask & INPUT_RIGHT)
          addX += accel;
        if(s_inputMask & INPUT_UP)
          addY -= accel;
        if(s_inputMask & INPUT_DOWN)
          addY += accel;
        addX += s_vxCarry[i];
        addY += s_vyCarry[i];
        int16_t dX = (int16_t)roundf(addX);
        int16_t dY = (int16_t)roundf(addY);
        s_vxCarry[i] = addX - (float)dX;
        s_vyCarry[i] = addY - (float)dY;
        s_vx10[i] = (int16_t)(s_vx10[i] + dX);
        s_vy10[i] = (int16_t)(s_vy10[i] + dY);
      }
      if(s_friction1000[i] != 1000)
      {
        float f = (float)s_friction1000[i] * 0.001f;
        s_vx10[i] = (int16_t)roundf((float)s_vx10[i] * f);
        s_vy10[i] = (int16_t)roundf((float)s_vy10[i] * f);
      }
      s_prevPosX[i] = s_posX[i];
      s_prevPosY[i] = s_posY[i];
      float dx = ((float)s_vx10[i]) * t * 0.1f;
      float dy = ((float)s_vy10[i]) * t * 0.1f;
      float nx = s_posX[i] + dx;
      float ny = s_posY[i] + dy;

      // Projectiles spawned by OP_SIGNAL_SPAWN_BULLET can opt out of wrap and
      // despawn once they leave the wrap bounds.
      if(s_isProjectile[i] && s_noWrap[i] && m_wrapEnabled)
      {
        if(nx < m_wrapMinX || nx > m_wrapMaxX || ny < m_wrapMinY || ny > m_wrapMaxY)
        {
          m_objects[i].active = false;
          s_isProjectile[i] = false;
          continue;
        }
      }

      if(m_wrapEnabled && !s_noWrap[i])
      {
        if(nx < m_wrapMinX)
          nx = (float)m_wrapMaxX;
        else if(nx > m_wrapMaxX)
          nx = (float)m_wrapMinX;
        if(ny < m_wrapMinY)
          ny = (float)m_wrapMaxY;
        else if(ny > m_wrapMaxY)
          ny = (float)m_wrapMinY;
      }
      else if(m_boundsEnabled)
      {
        if(nx < m_boundsMinX)
        {
          nx = (float)m_boundsMinX;
          s_vx10[i] = (int16_t)abs(s_vx10[i]);
          s_vxCarry[i] = 0.0f;
        }
        else if(nx > m_boundsMaxX)
        {
          nx = (float)m_boundsMaxX;
          s_vx10[i] = (int16_t)-abs(s_vx10[i]);
          s_vxCarry[i] = 0.0f;
        }
        if(ny < m_boundsMinY)
        {
          ny = (float)m_boundsMinY;
          s_vy10[i] = (int16_t)abs(s_vy10[i]);
          s_vyCarry[i] = 0.0f;
        }
        else if(ny > m_boundsMaxY)
        {
          ny = (float)m_boundsMaxY;
          s_vy10[i] = (int16_t)-abs(s_vy10[i]);
          s_vyCarry[i] = 0.0f;
        }
      }

      s_posX[i] = nx;
      s_posY[i] = ny;
      m_objects[i].x = (int16_t)roundf(nx);
      m_objects[i].y = (int16_t)roundf(ny);

      float ang = (float)s_angle10[i] + (float)s_angleSpeed10[i] * t;
      if(ang > 3600.0f || ang < -3600.0f)
        ang = fmodf(ang, 3600.0f);
      s_angle10[i] = (int16_t)ang;

      if(s_scaleAmp1000[i] > 0)
      {
        s_scalePhase[i] += s_scaleSpeedRadPerMs[i] * (float)dtMs;
      }
      float scale = (float)s_scaleBase1000[i] + (float)s_scaleAmp1000[i] * (0.5f + 0.5f * sinf(s_scalePhase[i]));
      if(scale < 1.0f)
        scale = 1.0f;

      uint8_t spriteId = m_objects[i].spriteId;
      if(s_animCount[i] > 0 && s_animFps[i] > 0)
      {
        if(s_animNextMs[i] == 0)
          s_animNextMs[i] = nowMs;
        uint32_t frameMs = 1000U / (uint32_t)s_animFps[i];
        if(nowMs >= s_animNextMs[i])
        {
          s_animNextMs[i] = nowMs + frameMs;
          s_animIndex[i] = (uint8_t)((s_animIndex[i] + 1) % s_animCount[i]);
        }
        spriteId = s_animFrames[i][s_animIndex[i]];
      }

      s_renderSprite[i] = spriteId;
      s_renderAngle10[i] = s_angle10[i];
      s_renderScale1000[i] = (uint16_t)scale;
    }

    // Optional per-object AABB bounce.
    // Build a compact list first to reduce needless scans when only a subset
    // of objects actually participates in bounce this frame.
    uint8_t bounceList[kMaxObjects];
    uint8_t bounceCount = 0;
    for(int a = 0; a < kMaxObjects; a++)
    {
      if(m_objects[a].active && s_bounceEnabled[a])
        bounceList[bounceCount++] = (uint8_t)a;
    }
    for(uint8_t ai = 0; ai < bounceCount; ai++)
    {
      int a = (int)bounceList[ai];
      for(uint8_t bi = (uint8_t)(ai + 1); bi < bounceCount; bi++)
      {
        int b = (int)bounceList[bi];

        float ax = s_posX[a] + (float)s_hitOffX[a];
        float ay = s_posY[a] + (float)s_hitOffY[a];
        float bx = s_posX[b] + (float)s_hitOffX[b];
        float by = s_posY[b] + (float)s_hitOffY[b];
        float dx = bx - ax;
        float dy = by - ay;
        float rx = ((float)s_hitW[a] + (float)s_hitW[b]) * 0.5f;
        float ry = ((float)s_hitH[a] + (float)s_hitH[b]) * 0.5f;
        if(fabsf(dx) > rx || fabsf(dy) > ry)
          continue;

        float relx = (float)(s_vx10[b] - s_vx10[a]);
        float rely = (float)(s_vy10[b] - s_vy10[a]);
        bool approaching = (relx * dx + rely * dy) < 0.0f;
        if(approaching)
        {
          int16_t tvx = s_vx10[a];
          int16_t tvy = s_vy10[a];
          s_vx10[a] = s_vx10[b];
          s_vy10[a] = s_vy10[b];
          s_vx10[b] = tvx;
          s_vy10[b] = tvy;
        }

        float ox = rx - fabsf(dx);
        float oy = ry - fabsf(dy);
        if(ox < oy)
        {
          float push = ox * 0.5f + 0.01f;
          float dir = (dx >= 0.0f) ? 1.0f : -1.0f;
          s_posX[a] -= dir * push;
          s_posX[b] += dir * push;
        }
        else
        {
          float push = oy * 0.5f + 0.01f;
          float dir = (dy >= 0.0f) ? 1.0f : -1.0f;
          s_posY[a] -= dir * push;
          s_posY[b] += dir * push;
        }

        m_objects[a].x = (int16_t)roundf(s_posX[a]);
        m_objects[a].y = (int16_t)roundf(s_posY[a]);
        m_objects[b].x = (int16_t)roundf(s_posX[b]);
        m_objects[b].y = (int16_t)roundf(s_posY[b]);
      }
    }

    for(int i = 0; i < kMaxSignals; i++)
    {
      s_signalActive[i] = false;
      s_signalForce[i] = false;
      s_signalOther[i] = 0xFF;
      s_signalSource[i] = 0xFF;
      s_signalSourceProjectile[i] = false;
    }
    if(m_musicPlaying && s_musicSignalSlot < kMaxSignals)
    {
      s_signalActive[s_musicSignalSlot] = true;
      s_signalSource[s_musicSignalSlot] = s_musicSignalOwner;
      s_signalSourceProjectile[s_musicSignalSlot] = false;
    }
    if(s_hudEnabled && s_hudLife <= 0 && kMaxSignals > 7)
    {
      s_signalActive[7] = true;
      // Keep owner-compatible source so per-object signal actions can run.
      s_signalSource[7] = 0;
      s_signalSourceProjectile[7] = false;
    }
    for(uint8_t i = 0; i < s_inputBindCount; i++)
    {
      uint8_t slot = s_inputBindSlot[i];
      if(slot >= kMaxSignals)
        continue;
      uint8_t owner = s_inputBindOwner[i];
      // Ignore input binds declared by inactive objects so helper/debug objects
      // outside the current room don't hijack shared signal slots.
      if(owner < kMaxObjects && !m_objects[owner].active)
        continue;
      uint8_t btn = s_inputBindButton[i];
      uint16_t bit = 0;
      switch(btn)
      {
        case 0: bit = INPUT_UP; break;
        case 1: bit = INPUT_DOWN; break;
        case 2: bit = INPUT_LEFT; break;
        case 3: bit = INPUT_RIGHT; break;
        case 4: bit = INPUT_A; break;
        case 5: bit = INPUT_B; break;
        case 6: bit = INPUT_X; break;
        case 7: bit = INPUT_Y; break;
        case 8: bit = INPUT_START; break;
        case 9: bit = INPUT_SELECT; break;
        case 10: bit = INPUT_L; break;
        case 11: bit = INPUT_R; break;
        default: bit = 0; break;
      }
      bool downNow = (s_inputMask & bit) != 0;
      bool downPrev = (s_prevInputMask & bit) != 0;
      uint8_t ev = s_inputBindEvent[i];
      if(ev == 0 && downNow)
      {
        s_signalActive[slot] = true;
        s_signalSource[slot] = owner;
        s_signalSourceProjectile[slot] = false;
      }
      else if(ev == 1 && downNow && !downPrev)
      {
        s_signalActive[slot] = true;
        s_signalSource[slot] = owner;
        s_signalSourceProjectile[slot] = false;
      }
      else if(ev == 2 && !downNow && downPrev)
      {
        s_signalActive[slot] = true;
        s_signalSource[slot] = owner;
        s_signalSourceProjectile[slot] = false;
      }
    }
    s_prevInputMask = s_inputMask;

    s_bgScrollStepX = 0;
    s_bgScrollStepY = 0;
    if(s_bgScrollX10 != 0)
    {
      s_bgScrollAccX += ((float)s_bgScrollX10) * t * 0.1f;
      int16_t step = (int16_t)roundf(s_bgScrollAccX);
      s_bgScrollAccX -= (float)step;
      s_bgScrollStepX = step;
    }
    if(s_bgScrollY10 != 0)
    {
      s_bgScrollAccY += ((float)s_bgScrollY10) * t * 0.1f;
      int16_t step = (int16_t)roundf(s_bgScrollAccY);
      s_bgScrollAccY -= (float)step;
      s_bgScrollStepY = step;
    }
    out.bgScrollX = s_bgScrollStepX;
    out.bgScrollY = s_bgScrollStepY;

    for(int obj = 0; obj < kMaxObjects; obj++)
    {
      if(!m_objects[obj].active)
        continue;
      for(int i = 0; i < kMaxAlarms; i++)
      {
        if(!s_alarmActive[obj][i] || s_alarmPeriodMs[obj][i] == 0)
          continue;
        if(nowMs >= s_alarmNextMs[obj][i])
        {
          uint8_t slot = s_alarmSignal[obj][i];
          if(slot < kMaxSignals)
          {
            s_signalActive[slot] = true;
            s_signalForce[slot] = true;
            s_signalOther[slot] = (uint8_t)obj;
            s_signalSource[slot] = (uint8_t)obj;
          }
          if(s_alarmRepeat[obj][i])
            s_alarmNextMs[obj][i] = nowMs + (uint32_t)s_alarmPeriodMs[obj][i];
          else
            s_alarmActive[obj][i] = false;
        }
      }
    }
    bool projectileHitConsumed[kMaxObjects];
    for(int i = 0; i < kMaxObjects; i++)
      projectileHitConsumed[i] = false;
    for(uint8_t i = 0; i < s_collideCount; i++)
    {
      uint8_t slot = s_collideSlot[i];
      uint8_t objA = s_collideA[i];
      uint8_t objB = s_collideB[i];
      if(slot >= kMaxSignals)
        continue;
      if(objA >= kMaxObjects || objB >= kMaxObjects)
        continue;
      if(!m_objects[objA].active || !m_objects[objB].active)
        continue;
      // Projectiles should resolve only one collision per frame to avoid
      // triggering multiple signal slots at once (e.g. middle + big).
      if(s_isProjectile[objA] && projectileHitConsumed[objA])
        continue;
      float ax = s_posX[objA] + (float)s_hitOffX[objA];
      float ay = s_posY[objA] + (float)s_hitOffY[objA];
      float apx = s_prevPosX[objA] + (float)s_hitOffX[objA];
      float apy = s_prevPosY[objA] + (float)s_hitOffY[objA];
      float bx = s_posX[objB] + (float)s_hitOffX[objB];
      float by = s_posY[objB] + (float)s_hitOffY[objB];
      bool overlap = false;
      if(s_isProjectile[objA])
        overlap = hitbox_overlap_swept(apx, apy, ax, ay, s_hitW[objA], s_hitH[objA], bx, by, s_hitW[objB], s_hitH[objB]);
      else
        overlap = hitbox_overlap(ax, ay, s_hitW[objA], s_hitH[objA], bx, by, s_hitW[objB], s_hitH[objB]);
      if(overlap)
      {
        if(s_isProjectile[objA])
        {
          MASA_DBG_SLOT(slot, "[MASA] COLLIDE slot=%u src=%u other=%u srcSpr=%u otherSpr=%u\n",
                        (unsigned)slot, (unsigned)objA, (unsigned)objB,
                        (unsigned)m_objects[objA].spriteId, (unsigned)m_objects[objB].spriteId);
        }
        s_signalActive[slot] = true;
        s_signalOther[slot] = objB;
        s_signalSource[slot] = objA;
        s_signalSourceProjectile[slot] = s_isProjectile[objA];
        if(s_isProjectile[objA])
          projectileHitConsumed[objA] = true;
      }
    }

    for(int i = 0; i < kMaxChoiceSlots; i++)
    {
      if(!s_choiceVisible[i] || s_choiceCount[i] == 0)
        continue;
      bool upNow = (s_inputMask & INPUT_UP) != 0;
      bool downNow = (s_inputMask & INPUT_DOWN) != 0;
      bool confirmNow = (s_inputMask & (INPUT_A | INPUT_START)) != 0;
      if(upNow && !s_choicePrevUp[i])
      {
        if(s_choiceSelected[i] == 0)
          s_choiceSelected[i] = (uint8_t)(s_choiceCount[i] - 1);
        else
          s_choiceSelected[i]--;
      }
      if(downNow && !s_choicePrevDown[i])
      {
        s_choiceSelected[i] = (uint8_t)((s_choiceSelected[i] + 1) % s_choiceCount[i]);
      }
      if(confirmNow && !s_choicePrevConfirm[i])
      {
        uint8_t slot = (uint8_t)(s_choiceBaseSignal[i] + s_choiceSelected[i]);
        if(slot < kMaxSignals)
        {
          s_signalActive[slot] = true;
          s_signalOther[slot] = s_choiceSelected[i];
          s_signalSource[slot] = s_choiceOwner[i];
          s_signalSourceProjectile[slot] = false;
        }
      }
      s_choicePrevUp[i] = upNow;
      s_choicePrevDown[i] = downNow;
      s_choicePrevConfirm[i] = confirmNow;
    }

    for(uint8_t i = 0; i < kMaxSignals; i++)
    {
      s_slotSpawnBulletSeen[i] = false;
      s_slotSpawnBulletFired[i] = false;
    }
    for(uint8_t i = 0; i < s_actionCount; i++)
    {
      uint8_t slot = s_actionSlot[i];
      if(slot >= kMaxSignals)
        continue;
      if(!s_signalActive[slot] || (s_signalPrev[slot] && !s_signalForce[slot]))
        continue;
      if(s_actionOwner[i] != 0xFF && s_actionOwner[i] != s_signalSource[slot])
      {
        // Alarm-driven slots are "forced" and can be triggered by multiple
        // instances in the same frame. Keep self-destroy alarms reliable even
        // when another instance writes the same slot/source later in the tick.
        bool allowForcedSelfDestroy =
          s_signalForce[slot] &&
          s_actionType[i] == kSignalActionDestroy &&
          s_actionObj[i] == s_actionOwner[i];
        if(!allowForcedSelfDestroy)
          continue;
      }
      if(s_actionType[i] == kSignalActionSpawnBullet)
        s_slotSpawnBulletSeen[slot] = true;
    }
    uint8_t s_slotSpawnNeed[kMaxSignals];
    uint8_t s_slotSpawnOk[kMaxSignals];
    bool s_slotDeferDestroyOther[kMaxSignals];
    uint8_t s_slotDeferDestroyOtherTarget[kMaxSignals];
    for(uint8_t i = 0; i < kMaxSignals; i++)
    {
      s_slotSpawnNeed[i] = 0;
      s_slotSpawnOk[i] = 0;
      s_slotDeferDestroyOther[i] = false;
      s_slotDeferDestroyOtherTarget[i] = 0xFF;
    }
    for(uint8_t i = 0; i < s_actionCount; i++)
    {
      uint8_t slot = s_actionSlot[i];
      if(slot >= kMaxSignals)
        continue;
      if(!s_signalActive[slot] || (s_signalPrev[slot] && !s_signalForce[slot]))
        continue;
      if(s_actionOwner[i] != 0xFF && s_actionOwner[i] != s_signalSource[slot])
      {
        continue;
      }
      if(s_actionType[i] == kSignalActionSpawn)
      {
        if(s_slotSpawnNeed[slot] < 0xFF)
          s_slotSpawnNeed[slot]++;
      }
    }

    for(uint8_t i = 0; i < s_actionCount; i++)
    {
      uint8_t slot = s_actionSlot[i];
      if(slot >= kMaxSignals)
        continue;
      if(!s_signalActive[slot] || (s_signalPrev[slot] && !s_signalForce[slot]))
        continue;
      if(s_actionOwner[i] != 0xFF && s_actionOwner[i] != s_signalSource[slot])
      {
        continue;
      }
      bool logAction = masa_dbg_slot(slot);
      // In minimal projectile debug, suppress noisy per-frame input/fire traces
      // and keep only collision/split-relevant action traces.
      if(s_actionType[i] == kSignalActionSpawnBullet ||
         s_actionType[i] == kSignalActionBeep)
      {
        logAction = false;
      }
      if(!s_signalSourceProjectile[slot])
        logAction = false;
      if(logAction)
      {
        MASA_DBG_SLOT(slot, "[MASA] ACTION slot=%u type=%u owner=%u src=%u other=%u obj=%u\n",
                      (unsigned)slot, (unsigned)s_actionType[i], (unsigned)s_actionOwner[i],
                      (unsigned)s_signalSource[slot], (unsigned)s_signalOther[slot], (unsigned)s_actionObj[i]);
      }
      uint8_t obj = s_actionObj[i];
      switch(s_actionType[i])
      {
        case kSignalActionDestroy:
          if(obj < kMaxObjects)
          {
            if(s_signalSourceProjectile[slot])
              MASA_DBG_SLOT(slot, "[MASA] DESTROY slot=%u target=%u spr=%u\n",
                            (unsigned)slot, (unsigned)obj, (unsigned)m_objects[obj].spriteId);
            m_objects[obj].active = false;
            s_isProjectile[obj] = false;
          }
          break;
        case kSignalActionDestroyOther:
          if(s_signalOther[slot] < kMaxObjects)
          {
            if(s_slotSpawnNeed[slot] > 0)
            {
              s_slotDeferDestroyOther[slot] = true;
              s_slotDeferDestroyOtherTarget[slot] = s_signalOther[slot];
            }
            else
            {
              if(s_signalSourceProjectile[slot])
                MASA_DBG_SLOT(slot, "[MASA] DESTROY_OTHER slot=%u target=%u spr=%u\n",
                              (unsigned)slot, (unsigned)s_signalOther[slot],
                              (unsigned)m_objects[s_signalOther[slot]].spriteId);
              m_objects[s_signalOther[slot]].active = false;
              s_isProjectile[s_signalOther[slot]] = false;
            }
          }
          break;
        case kSignalActionSpawn:
          if(obj < kMaxObjects)
          {
            uint8_t srcObj = s_signalSource[slot];
            uint8_t otherObj = s_signalOther[slot];
            // If preferred target is busy, fallback to any inactive slot.
            // Prefer matching sprite first, then any free slot.
            if(m_objects[obj].active && obj != srcObj)
            {
              uint8_t fallbackObj = 0xFF;
              bool slotHasDeclaredTargets = false;
              if(s_signalSourceProjectile[slot])
                MASA_DBG_SLOT(slot, "[MASA] SPAWN target busy slot=%u obj=%u spr=%u wantedSpr=%u\n",
                              (unsigned)slot, (unsigned)obj, (unsigned)m_objects[obj].spriteId,
                              (unsigned)s_actionSprite[i]);
              if(slot < kMaxSignals)
              {
                for(uint8_t cand = 0; cand < kMaxObjects; cand++)
                {
                  if(s_spawnTargetAllowed[slot][cand])
                  {
                    slotHasDeclaredTargets = true;
                    break;
                  }
                }
              }
              for(uint8_t cand = 0; cand < kMaxObjects; cand++)
              {
                if(m_objects[cand].active)
                  continue;
                // Never recycle source/other slots for spawned results in the
                // same signal tick; avoids projectile-slot reuse side effects.
                if(cand == srcObj || cand == s_signalOther[slot])
                  continue;
                // Restrict fallback to targets declared for this slot via
                // OP_SIGNAL_SPAWN. This avoids class-mismatch ghost spawns
                // (e.g., small rocks living in unrelated object IDs).
                if(slot < kMaxSignals && s_spawnTargetAllowed[slot][cand])
                {
                  fallbackObj = cand;
                  break;
                }
              }
              // If strict declared-target fallback is exhausted, allow a same-sprite
              // free slot as a secondary fallback. This keeps split-style spawns
              // working when the declared pair is temporarily busy.
              if(fallbackObj == 0xFF && slotHasDeclaredTargets)
              {
                for(uint8_t cand = 0; cand < kMaxObjects; cand++)
                {
                  if(m_objects[cand].active)
                    continue;
                  if(cand == srcObj || cand == s_signalOther[slot])
                    continue;
                  if(m_objects[cand].spriteId == s_actionSprite[i] ||
                     s_defaultSprite[cand] == s_actionSprite[i])
                  {
                    fallbackObj = cand;
                    break;
                  }
                }
              }
              if(fallbackObj == 0xFF)
              {
                if(s_signalSourceProjectile[slot])
                  MASA_DBG_SLOT(slot, "[MASA] SPAWN FAILED slot=%u wantedSpr=%u (no compatible free slot)\n",
                                (unsigned)slot, (unsigned)s_actionSprite[i]);
                break;
              }
              if(s_signalSourceProjectile[slot])
                MASA_DBG_SLOT(slot, "[MASA] SPAWN fallback slot=%u old=%u new=%u wantedSpr=%u\n",
                              (unsigned)slot, (unsigned)obj, (unsigned)fallbackObj, (unsigned)s_actionSprite[i]);
              obj = fallbackObj;
            }
            const int16_t kSpawnSource = 32767;
            const int16_t kSpawnOther = 32766;
            int16_t sx = s_actionX[i];
            int16_t sy = s_actionY[i];
            if(sx == kSpawnSource && srcObj < kMaxObjects)
              sx = m_objects[srcObj].x;
            else if(sx == kSpawnOther && otherObj < kMaxObjects)
              sx = m_objects[otherObj].x;
            if(sy == kSpawnSource && srcObj < kMaxObjects)
              sy = m_objects[srcObj].y;
            else if(sy == kSpawnOther && otherObj < kMaxObjects)
              sy = m_objects[otherObj].y;
            if(s_signalSourceProjectile[slot])
              MASA_DBG_SLOT(slot, "[MASA] SPAWN slot=%u obj=%u x=%d y=%d spr=%u src=%u other=%u\n",
                            (unsigned)slot, (unsigned)obj, (int)sx, (int)sy,
                            (unsigned)s_actionSprite[i], (unsigned)srcObj, (unsigned)otherObj);
            m_objects[obj].x = sx;
            m_objects[obj].y = sy;
            s_posX[obj] = (float)sx;
            s_posY[obj] = (float)sy;
            s_prevPosX[obj] = s_posX[obj];
            s_prevPosY[obj] = s_posY[obj];
            m_objects[obj].spriteId = s_actionSprite[i];
            s_defaultSprite[obj] = s_actionSprite[i];
            m_objects[obj].active = true;
            s_isProjectile[obj] = false;
            alarm_start_defaults_for_obj(obj, nowMs);
            s_angle10[obj] = 0;
            s_angleSpeed10[obj] = 0;
            s_vx10[obj] = 0;
            s_vy10[obj] = 0;
            s_vxCarry[obj] = 0.0f;
            s_vyCarry[obj] = 0.0f;
            s_inputSpeed10[obj] = 0;
            s_accel10[obj] = 0;
            s_friction1000[obj] = 1000;
            // Preserve control tunables when respawning self (e.g. player),
            // otherwise movement can be lost after death/respawn.
            if(obj != srcObj)
            {
              s_turnSpeed10[obj] = 0;
              s_thrust10[obj] = 0;
            }
            s_scaleBase1000[obj] = 1000;
            s_scaleAmp1000[obj] = 0;
            s_scalePhase[obj] = 0.0f;
            s_scaleSpeedRadPerMs[obj] = 0.0f;
            s_animIndex[obj] = 0;
            s_animNextMs[obj] = 0;
            s_renderSprite[obj] = m_objects[obj].spriteId;
            s_renderAngle10[obj] = 0;
            s_renderScale1000[obj] = 1000;
            if(s_velRandomEnabled[obj])
            {
              s_vx10[obj] = random_vel10_for_obj(obj);
              s_vy10[obj] = random_vel10_for_obj(obj);
            }
            s_slotSpawnOk[slot]++;
          }
          break;
        case kSignalActionSound:
          if(m_audioCb)
            m_audioCb(s_actionSound[i]);
          break;
        case kSignalActionRoomNext:
          if(m_roomCount > 0)
            set_room((uint8_t)((m_roomIndex + 1) % m_roomCount));
          break;
        case kSignalActionRoomGoto:
          if(m_roomCount > 0)
          {
            uint8_t target = (uint8_t)s_actionObj[i];
            if(target < m_roomCount)
              set_room(target);
          }
          break;
        case kSignalActionSpawnBullet:
        {
          if(slot < kMaxSignals)
            s_slotSpawnBulletSeen[slot] = true;
          uint8_t src = s_actionObj[i];
          if(slot < kMaxSignals && s_signalSource[slot] < kMaxObjects)
            src = s_signalSource[slot];
          uint8_t bullet = s_actionSprite[i];
          bool fired = false;
          if(src < kMaxObjects && bullet < kMaxObjects)
          {
            // Non-zero speed bullets are single-instance by object id.
            // This avoids per-frame respawn "sticking" a bullet to the player
            // when an input bind is held by mistake.
            if(s_actionSpeed10[i] != 0 && m_objects[bullet].active)
              break;
            float deg = ((float)s_angle10[src]) * 0.1f;
            float rad = deg * 3.14159265f / 180.0f;
            float ox = cosf(rad) * (float)s_actionOffset[i];
            float oy = sinf(rad) * (float)s_actionOffset[i];
            float baseX = s_posX[src];
            float baseY = s_posY[src];
            s_posX[bullet] = baseX + ox;
            s_posY[bullet] = baseY + oy;
            s_prevPosX[bullet] = s_posX[bullet];
            s_prevPosY[bullet] = s_posY[bullet];
            m_objects[bullet].x = (int16_t)roundf(s_posX[bullet]);
            m_objects[bullet].y = (int16_t)roundf(s_posY[bullet]);
            if(s_actionColor[i] != 0xFF)
              m_objects[bullet].spriteId = s_actionColor[i];
            m_objects[bullet].active = true;
            s_isProjectile[bullet] = true;
            alarm_start_defaults_for_obj(bullet, nowMs);
            s_vx10[bullet] = (int16_t)roundf(cosf(rad) * (float)s_actionSpeed10[i]);
            s_vy10[bullet] = (int16_t)roundf(sinf(rad) * (float)s_actionSpeed10[i]);
            s_vxCarry[bullet] = 0.0f;
            s_vyCarry[bullet] = 0.0f;
            s_angle10[bullet] = s_angle10[src];
            s_angleSpeed10[bullet] = 0;
            s_inputSpeed10[bullet] = 0;
            s_accel10[bullet] = 0;
            s_friction1000[bullet] = 1000;
            s_turnSpeed10[bullet] = 0;
            s_thrust10[bullet] = 0;
            s_scaleBase1000[bullet] = 1000;
            s_scaleAmp1000[bullet] = 0;
            s_scalePhase[bullet] = 0.0f;
            s_scaleSpeedRadPerMs[bullet] = 0.0f;
            s_renderSprite[bullet] = m_objects[bullet].spriteId;
            s_renderAngle10[bullet] = s_angle10[src];
            s_renderScale1000[bullet] = 1000;
            fired = true;
          }
          if(slot < kMaxSignals && fired)
            s_slotSpawnBulletFired[slot] = true;
          break;
        }
        case kSignalActionBeep:
          if(slot < kMaxSignals && s_slotSpawnBulletSeen[slot] && !s_slotSpawnBulletFired[slot])
            break;
          if(s_actionBeepHz[i] > 0 && s_actionBeepMs[i] > 0)
          {
            if(m_beepExCb)
              m_beepExCb(s_actionBeepWave[i], s_actionBeepHz[i], s_actionBeepMs[i]);
            else if(m_beepCb)
              m_beepCb(s_actionBeepHz[i], s_actionBeepMs[i]);
          }
          break;
        case kSignalActionStop:
          if(obj < kMaxObjects)
          {
            s_vx10[obj] = 0;
            s_vy10[obj] = 0;
            s_vxCarry[obj] = 0.0f;
            s_vyCarry[obj] = 0.0f;
            s_inputSpeed10[obj] = 0;
            s_angleSpeed10[obj] = 0;
          }
          break;
        case kSignalActionTextBox:
        {
          uint8_t tslot = (uint8_t)(obj % kMaxTextBoxes);
          s_textBoxVisible[tslot] = true;
          s_textBoxX[tslot] = s_actionX[i];
          s_textBoxY[tslot] = s_actionY[i];
          s_textBoxW[tslot] = s_actionW[i];
          s_textBoxH[tslot] = s_actionH[i];
          s_textBoxColor[tslot] = s_actionColor[i];
          uint8_t len = s_actionTextLen[i];
          if(len > kMaxTextBoxLen)
            len = kMaxTextBoxLen;
          s_textBoxLen[tslot] = len;
          for(uint8_t j = 0; j < len; j++)
            s_textBoxStr[tslot][j] = s_actionText[i][j];
          s_textBoxStr[tslot][len] = '\0';
          break;
        }
        case kSignalActionChoices:
        {
          uint8_t cslot = (uint8_t)(obj % kMaxChoiceSlots);
          s_choiceVisible[cslot] = true;
          s_choiceX[cslot] = s_actionX[i];
          s_choiceY[cslot] = s_actionY[i];
          s_choiceColor[cslot] = s_actionColor[i];
          s_choiceBaseSignal[cslot] = s_actionBaseSignal[i];
          s_choiceCount[cslot] = (s_actionChoiceCount[i] > kMaxChoiceItems) ? kMaxChoiceItems : s_actionChoiceCount[i];
          s_choiceSelected[cslot] = 0;
          s_choicePrevUp[cslot] = false;
          s_choicePrevDown[cslot] = false;
          s_choicePrevConfirm[cslot] = false;
          for(uint8_t j = 0; j < s_choiceCount[cslot]; j++)
          {
            s_choiceLen[cslot][j] = s_actionChoiceLen[i][j];
            uint8_t len = s_choiceLen[cslot][j];
            if(len > kMaxChoiceLen)
              len = kMaxChoiceLen;
            for(uint8_t k = 0; k < len; k++)
              s_choiceText[cslot][j][k] = s_actionChoiceText[i][j][k];
            s_choiceText[cslot][j][len] = '\0';
          }
          break;
        }
        case kSignalActionTextBoxClear:
        {
          uint8_t tslot = (uint8_t)(obj % kMaxTextBoxes);
          s_textBoxVisible[tslot] = false;
          break;
        }
        case kSignalActionChoicesClear:
        {
          uint8_t cslot = (uint8_t)(obj % kMaxChoiceSlots);
          s_choiceVisible[cslot] = false;
          break;
        }
        case kSignalActionSetInput:
        {
          if(obj < kMaxObjects)
            s_inputSpeed10[obj] = s_actionSpeed10[i];
          break;
        }
        case kSignalActionHudAdd:
          s_hudLife += (int32_t)s_actionX[i];
          if(s_hudLife < 0)
            s_hudLife = 0;
          s_hudScore += (int32_t)s_actionY[i];
          s_hudCoins += (int32_t)s_actionW[i];
          if(s_hudEnabled && s_hudLife <= 0)
          {
            uint8_t src = s_signalSource[slot];
            if(src < kMaxObjects)
            {
              m_objects[src].active = false;
              s_isProjectile[src] = false;
            }
          }
          break;
        case kSignalActionShowText:
        {
          uint8_t tslot = (uint8_t)(obj % kMaxTextSlots);
          uint8_t oldSpan = s_textSpan[tslot];
          if(oldSpan == 0)
            oldSpan = 1;
          for(uint8_t si = 0; si < oldSpan; si++)
          {
            uint8_t ss = (uint8_t)(tslot + si);
            if(ss >= kMaxTextSlots)
              break;
            s_textVisible[ss] = false;
            s_textLen[ss] = 0;
            s_textStr[ss][0] = '\0';
          }
          int16_t drawX = s_actionX[i];
          int16_t drawY = s_actionY[i];
          uint8_t drawColor = s_actionColor[i];
          char tmp[kMaxTextBoxLen + 1];
          uint8_t len = s_actionTextLen[i];
          if(len > kMaxTextBoxLen)
            len = kMaxTextBoxLen;
          for(uint8_t j = 0; j < len; j++)
            tmp[j] = s_actionText[i][j];
          tmp[len] = '\0';
          replace_token_i32(tmp, sizeof(tmp), "{SCORE}", s_hudScore);
          uint8_t outLen = (uint8_t)strlen(tmp);
          if(outLen > kMaxTextBoxLen)
            outLen = kMaxTextBoxLen;
          uint8_t align = (s_actionW[i] < 0) ? 0 : (uint8_t)s_actionW[i];
          if(align > 2)
            align = 0;
          int16_t baseX = drawX;
          if(align == 1)
            baseX = (int16_t)(drawX - (int16_t)((outLen * 6) / 2));
          else if(align == 2)
            baseX = (int16_t)(drawX - (int16_t)(outLen * 6));

          uint8_t maxSpan = (uint8_t)(kMaxTextSlots - tslot);
          if(maxSpan == 0)
            break;
          uint8_t usedSpan = 0;
          uint8_t cursor = 0;
          uint8_t consumedTotal = 0;
          while(usedSpan < maxSpan)
          {
            uint8_t ss = (uint8_t)(tslot + usedSpan);
            uint8_t chunkLen = 0;
            uint8_t consumed = 0;
            if(cursor < outLen)
            {
              uint8_t rem = (uint8_t)(outLen - cursor);
              uint8_t take = (rem > kMaxTextLen) ? kMaxTextLen : rem;
              if(rem > kMaxTextLen)
              {
                for(int k = (int)take - 1; k > 0; k--)
                {
                  if(tmp[cursor + k] == ' ')
                  {
                    take = (uint8_t)(k + 1);
                    break;
                  }
                }
              }
              chunkLen = take;
              consumed = take;
              while((cursor + consumed) < outLen && tmp[cursor + consumed] == ' ')
                consumed++;
            }
            s_textVisible[ss] = true;
            s_textX[ss] = (int16_t)(baseX + (int16_t)(consumedTotal * 6));
            s_textY[ss] = drawY;
            s_textColor[ss] = drawColor;
            s_textLen[ss] = chunkLen;
            for(uint8_t j = 0; j < chunkLen; j++)
              s_textStr[ss][j] = tmp[cursor + j];
            s_textStr[ss][chunkLen] = '\0';
            usedSpan++;
            if(cursor >= outLen || consumed == 0)
              break;
            cursor = (uint8_t)(cursor + consumed);
            consumedTotal = (uint8_t)(consumedTotal + consumed);
          }
          if(usedSpan == 0)
            usedSpan = 1;
          s_textSpan[tslot] = usedSpan;
          break;
        }
        case kSignalActionShowTextClear:
        {
          uint8_t tslot = (uint8_t)(obj % kMaxTextSlots);
          uint8_t span = s_textSpan[tslot];
          if(span == 0)
            span = 1;
          for(uint8_t si = 0; si < span; si++)
          {
            uint8_t ss = (uint8_t)(tslot + si);
            if(ss >= kMaxTextSlots)
              break;
            s_textVisible[ss] = false;
            s_textLen[ss] = 0;
            s_textStr[ss][0] = '\0';
          }
          s_textSpan[tslot] = 1;
          break;
        }
        default:
          break;
      }
    }
    for(uint8_t slot = 0; slot < kMaxSignals; slot++)
    {
      if(!s_slotDeferDestroyOther[slot])
        continue;
      uint8_t target = s_slotDeferDestroyOtherTarget[slot];
      if(target >= kMaxObjects)
        continue;
      // Hybrid split policy:
      // - no child spawns requested: destroy immediately
      // - all requested children spawned: destroy
      // - projectile-triggered split with at least one spawned child: destroy
      // This avoids "invincible" rocks under pressure while also preventing
      // targets from vanishing with zero gameplay result.
      bool canDestroyOther = (s_slotSpawnNeed[slot] == 0) ||
                             (s_slotSpawnOk[slot] >= s_slotSpawnNeed[slot]) ||
                             (s_slotSpawnNeed[slot] <= 1) ||
                             (s_signalSourceProjectile[slot] && s_slotSpawnOk[slot] > 0);
      if(canDestroyOther)
      {
        if(s_signalSourceProjectile[slot])
          MASA_DBG_SLOT(slot, "[MASA] DESTROY_OTHER(deferred) slot=%u target=%u spr=%u\n",
                        (unsigned)slot, (unsigned)target, (unsigned)m_objects[target].spriteId);
        m_objects[target].active = false;
        s_isProjectile[target] = false;
      }
      else
      {
        if(s_signalSourceProjectile[slot])
          MASA_DBG_SLOT(slot, "[MASA] DESTROY_OTHER canceled slot=%u need=%u got=%u target=%u\n",
                        (unsigned)slot, (unsigned)s_slotSpawnNeed[slot], (unsigned)s_slotSpawnOk[slot], (unsigned)target);
      }
    }

    for(int i = 0; i < kMaxSignals; i++)
      s_signalPrev[i] = s_signalActive[i];

    for(int i = 0; i < kMaxObjects; i++)
    {
      if(!m_objects[i].active)
        continue;
      out.push(RENDER_DRAW_SPRITE_XFORM, m_objects[i].x, m_objects[i].y,
               s_renderSprite[i], s_renderAngle10[i], s_renderScale1000[i]);
    }
  }

  for(int i = 0; i < kMaxTextBoxes; i++)
  {
    if(!s_textBoxVisible[i] || s_textBoxLen[i] == 0)
      continue;
    int16_t x1 = s_textBoxX[i];
    int16_t y1 = s_textBoxY[i];
    int16_t x2 = (int16_t)(x1 + s_textBoxW[i]);
    int16_t y2 = (int16_t)(y1 + s_textBoxH[i]);
    out.push_shape(SHAPE_FILL_RECT, x1, y1, x2, y2, 0, 0, s_textBoxColor[i]);
    out.push_shape(SHAPE_RECT, x1, y1, x2, y2, 0, 0, 15);

    char line1[kMaxTextBoxLen + 1];
    char line2[kMaxTextBoxLen + 1];
    line1[0] = '\0';
    line2[0] = '\0';
    uint8_t l1 = 0;
    uint8_t l2 = 0;
    bool second = false;
    for(uint8_t j = 0; j < s_textBoxLen[i] && j < kMaxTextBoxLen; j++)
    {
      char c = s_textBoxStr[i][j];
      if(c == '|')
      {
        second = true;
        continue;
      }
      if(!second && l1 < kMaxTextBoxLen)
        line1[l1++] = c;
      else if(second && l2 < kMaxTextBoxLen)
        line2[l2++] = c;
    }
    line1[l1] = '\0';
    line2[l2] = '\0';
    if(l1 > 0)
      out.push_text((int16_t)(x1 + 6), (int16_t)(y1 + 8), 15, line1, l1);
    if(l2 > 0)
      out.push_text((int16_t)(x1 + 6), (int16_t)(y1 + 20), 15, line2, l2);
  }

  for(int i = 0; i < kMaxChoiceSlots; i++)
  {
    if(!s_choiceVisible[i] || s_choiceCount[i] == 0)
      continue;
    int16_t baseX = s_choiceX[i];
    int16_t baseY = s_choiceY[i];
    for(uint8_t c = 0; c < s_choiceCount[i]; c++)
    {
      char line[kMaxChoiceLen + 3];
      uint8_t len = s_choiceLen[i][c];
      if(len > kMaxChoiceLen)
        len = kMaxChoiceLen;
      uint8_t pos = 0;
      if(c == s_choiceSelected[i])
      {
        line[pos++] = '>';
        line[pos++] = ' ';
      }
      for(uint8_t j = 0; j < len && pos < sizeof(line) - 1; j++)
        line[pos++] = s_choiceText[i][c][j];
      line[pos] = '\0';
      uint8_t color = (c == s_choiceSelected[i]) ? 15 : s_choiceColor[i];
      out.push_text((int16_t)(baseX), (int16_t)(baseY + c * 12), color, line, pos);
    }
  }

  for(int i = 0; i < kMaxTextSlots; i++)
  {
    if(!s_textVisible[i] || s_textLen[i] == 0)
      continue;
    out.push_text(s_textX[i], s_textY[i], s_textColor[i], s_textStr[i], s_textLen[i]);
  }
  for(int i = 0; i < kMaxTextSlots; i++)
  {
    if(!s_varfTextVisible[i])
      continue;
    float val = 0.0f;
    if(s_varfTextScope[i] == 0)
    {
      if(s_varfTextIndex[i] < kMaxGlobalVars)
        val = s_varfGlobal[s_varfTextIndex[i]];
    }
    else
    {
      uint8_t obj = s_varfTextObj[i];
      if(obj < kMaxObjects && s_varfTextIndex[i] < kMaxVarsPerObj)
        val = s_varfObj[obj][s_varfTextIndex[i]];
    }
    char hud[kMaxTextLen + 1];
    const char *label = s_varfTextLabel[i];
    int n = 0;
    if(label && label[0] != '\0')
      n = snprintf(hud, sizeof(hud), "%s%.2f", label, (double)val);
    else
      n = snprintf(hud, sizeof(hud), "%.2f", (double)val);
    if(n < 0)
      n = 0;
    if(n > kMaxTextLen)
      n = kMaxTextLen;
    if(n > 0)
      out.push_text(s_varfTextX[i], s_varfTextY[i], s_varfTextColor[i], hud, (uint8_t)n);
  }
  for(int i = 0; i < kMaxTextSlots; i++)
  {
    if(!s_strTextVisible[i])
      continue;
    const char *val = "";
    if(s_strTextScope[i] == 0)
    {
      if(s_strTextIndex[i] < kMaxGlobalVars)
        val = s_strGlobal[s_strTextIndex[i]];
    }
    else
    {
      uint8_t obj = s_strTextObj[i];
      if(obj < kMaxObjects && s_strTextIndex[i] < kMaxVarsPerObj)
        val = s_strObj[obj][s_strTextIndex[i]];
    }
    char hud[kMaxTextLen + 1];
    const char *label = s_strTextLabel[i];
    int n = 0;
    if(label && label[0] != '\0')
      n = snprintf(hud, sizeof(hud), "%s%s", label, val);
    else
      n = snprintf(hud, sizeof(hud), "%s", val);
    if(n < 0)
      n = 0;
    if(n > kMaxTextLen)
      n = kMaxTextLen;
    if(n > 0)
      out.push_text(s_strTextX[i], s_strTextY[i], s_strTextColor[i], hud, (uint8_t)n);
  }
  for(int i = 0; i < kMaxTextSlots; i++)
  {
    if(!s_varTextVisible[i])
      continue;
    int32_t val = 0;
    if(s_varTextScope[i] == 0)
    {
      if(s_varTextIndex[i] < kMaxGlobalVars)
        val = s_varGlobal[s_varTextIndex[i]];
    }
    else
    {
      uint8_t obj = s_varTextObj[i];
      if(obj < kMaxObjects && s_varTextIndex[i] < kMaxVarsPerObj)
        val = s_varObj[obj][s_varTextIndex[i]];
    }
    char hud[kMaxTextLen + 1];
    const char *label = s_varTextLabel[i];
    int n = 0;
    if(label && label[0] != '\0')
      n = snprintf(hud, sizeof(hud), "%s%d", label, (int)val);
    else
      n = snprintf(hud, sizeof(hud), "%d", (int)val);
    if(n < 0)
      n = 0;
    if(n > kMaxTextLen)
      n = kMaxTextLen;
    if(n > 0)
      out.push_text(s_varTextX[i], s_varTextY[i], s_varTextColor[i], hud, (uint8_t)n);
  }
  if(s_hudEnabled)
  {
    char hud[kMaxHudTemplateLen + 1];
    if(s_hudFormat[0] != '\0')
    {
      strncpy(hud, s_hudFormat, kMaxHudTemplateLen);
      hud[kMaxHudTemplateLen] = '\0';
    }
    else
    {
      strncpy(hud, "L:{LIFE} S:{SCORE} C:{COINS}", kMaxHudTemplateLen);
      hud[kMaxHudTemplateLen] = '\0';
    }
    replace_token_i32(hud, sizeof(hud), "{LIFE}", s_hudLife);
    replace_token_i32(hud, sizeof(hud), "{SCORE}", s_hudScore);
    replace_token_i32(hud, sizeof(hud), "{COINS}", s_hudCoins);
    int n = (int)strlen(hud);
    if(n < 0)
      n = 0;
    if(n > 0)
    {
      int16_t drawX = s_hudX;
      int16_t drawY = s_hudY;
      int16_t textW = (int16_t)(n * 6);
      if(s_hudAlign == 1)
        drawX = (int16_t)(s_hudX - (textW / 2));
      else if(s_hudAlign == 2)
        drawX = (int16_t)(s_hudX - textW);
      if(s_hudBgColor != 0xFF)
      {
        int16_t x1 = (int16_t)(drawX - s_hudPadX);
        int16_t y1 = (int16_t)(drawY - s_hudPadY);
        int16_t x2 = (int16_t)(drawX + textW + s_hudPadX);
        int16_t y2 = (int16_t)(drawY + 8 + s_hudPadY);
        out.push_shape(SHAPE_FILL_RECT, x1, y1, x2, y2, 0, 0, s_hudBgColor);
      }
      int off = 0;
      while(off < n)
      {
        int rem = (n - off);
        int chunk = (rem > kMaxTextLen) ? kMaxTextLen : rem;
        if(rem > kMaxTextLen)
        {
          int brk = -1;
          for(int j = off + chunk - 1; j > off; j--)
          {
            if(hud[j] == ' ')
            {
              brk = j;
              break;
            }
          }
          if(brk > off)
            chunk = brk - off;
        }
        if(chunk <= 0)
          break;
        out.push_text((int16_t)(drawX + off * 6), drawY, s_hudColor, hud + off, chunk);
        off += chunk;
      }
    }
  }
  if(s_hudEnabled && s_hudLife <= 0)
  {
    // Restart only on rising-edge of real buttons (ignore analog movement bits).
    const uint16_t restartMask = (INPUT_A | INPUT_B | INPUT_X | INPUT_Y |
                                  INPUT_START | INPUT_SELECT | INPUT_L | INPUT_R);
    if(!s_gameOverArmed)
    {
      uint16_t nowRestart = (uint16_t)(s_inputMask & restartMask);
      // Arm when restart buttons are released; don't block on stick/axis drift.
      if(nowRestart == 0)
      {
        s_gameOverArmed = true;
        s_gameOverPrevMask = 0;
      }
    }
    else
    {
      uint16_t nowRestart = (uint16_t)(s_inputMask & restartMask);
      if(nowRestart != 0 && s_gameOverPrevMask == 0)
      {
        reset();
        return;
      }
      s_gameOverPrevMask = nowRestart;
    }
  }
  for(int i = 0; i < kMaxShapeSlots; i++)
  {
    if(!s_shapeVisible[i])
      continue;
    out.push_shape(s_shapeType[i], s_shapeX1[i], s_shapeY1[i],
                   s_shapeX2[i], s_shapeY2[i], s_shapeX3[i], s_shapeY3[i],
                   s_shapeColor[i]);
  }
}
}
