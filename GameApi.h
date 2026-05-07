#pragma once

#include <Arduino.h>
#include "Graphics.h"
#include "Sprites.h"

// Helpers de sprites/animacion escrito en estilo GML usados por demos y exporter viejo
// El runtime MASA nuevo tambien puede terminar usando estas primitivas para dibujar atlas
// Reference to a sprite atlas plus optional metadata
struct SpriteAtlasRef
{
  Sprites *atlas;
  int frameCount;
  const char *name;
};

// Animation description: frames, playback speed, and looping mode
struct AnimationClip
{
  const SpriteAtlasRef *atlasRef;
  const unsigned short *frames;
  int frameCount;
  int fps;
  bool loop;
};

// Runtime state for a drawable/animatable object
struct SpriteInstance
{
  int x;
  int y;
  bool center;
  bool visible;
  bool paused;
  int frameIndex;
  unsigned long nextFrameMs;
  const AnimationClip *clip;
};

// Basic sprite drawing helpers
void draw_sprite(Graphics &g, Sprites &atlas, int x, int y, int spriteId);
void draw_sprite_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId);

// Transform helpers for atlas sprites
void draw_sprite_rotated_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float angleDeg);
void draw_sprite_scaled_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float scale);
void draw_sprite_rotated_scaled_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float angleDeg, float scale);

// Performance knob: sample every N pixels for rotated/scale draws (1 = full quality)
void set_transform_step(int step);

// High-level transform draw for sprite instances
void sprite_draw_rotated(Graphics &g, SpriteInstance &inst, float angleDeg);
void sprite_draw_scaled(Graphics &g, SpriteInstance &inst, float scale);

// Animation control/update utilities
void anim_play(SpriteInstance &inst, const AnimationClip &clip, bool restart = true);
void anim_pause(SpriteInstance &inst);
void anim_resume(SpriteInstance &inst);
void anim_stop(SpriteInstance &inst);
void anim_update(SpriteInstance &inst, unsigned long nowMs);
void anim_draw(Graphics &g, SpriteInstance &inst);
