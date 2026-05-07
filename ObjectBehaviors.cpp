#include "ObjectBehaviors.h"

// Frame layout from my current my_sprites.h:
// 0..7  = p_dance_1..8
// 8     = p_kirby
// 9     = p_popeyes
// 10    = p_ggball
static const int FRAME_DANCE_START = 0;
static const int FRAME_DANCE_END = 7;
static const int DANCE_FPS = 8;

static void behavior_p_dance(unsigned long nowMs, ObjectRenderState &s)
{
  int frameCount = FRAME_DANCE_END - FRAME_DANCE_START + 1;
  int step = (int)(nowMs / (1000 / DANCE_FPS)) % frameCount;
  s.frame = FRAME_DANCE_START + step;
}

static void behavior_p_kirby(unsigned long nowMs, ObjectRenderState &s)
{
  (void)nowMs;
  // Example: keep as-is (normal mode, static frame unless editor says otherwise)
  // To rotate Kirby globally, uncomment:
  // s.mode = 1;
  // s.angle = nowMs * 0.12f;
}

static void behavior_p_popeyes(unsigned long nowMs, ObjectRenderState &s)
{
  (void)nowMs;
  // Example: keep as-is
  // To pulse scale, uncomment:
  // s.mode = 2;
  // s.scale = 1.0f + 0.25f * sinf(nowMs * 0.006f);
}

void apply_object_behavior(int roomObjectIndex, unsigned long nowMs, ObjectRenderState &s)
{
  (void)roomObjectIndex; // Use this if you need per-instance logic

  // Dispatch by base frame family
  if(s.frame >= FRAME_DANCE_START && s.frame <= FRAME_DANCE_END)
  {
    behavior_p_dance(nowMs, s);
    return;
  }
  if(s.frame == 8)
  {
    behavior_p_kirby(nowMs, s);
    return;
  }
  if(s.frame == 9)
  {
    behavior_p_popeyes(nowMs, s);
    return;
  }
}
