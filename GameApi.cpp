#include "GameApi.h"
#include <math.h>

// Dibujo/animacion de sprites para el camino legacy y para utilidades de gameplay
// Mantiene transformaciones simples sin meter dependencias pesadas
static int s_transform_step = 1;

void set_transform_step(int step)
{
  if(step < 1)
    step = 1;
  if(step > 4)
    step = 4;
  s_transform_step = step;
}

// Draw using sprite pivot point as logical position
void draw_sprite(Graphics &g, Sprites &atlas, int x, int y, int spriteId)
{
  const short *origin = atlas.point(spriteId, 0);
  atlas.draw(g, spriteId, x + origin[0], y + origin[1]);
}

// Draw centered on (cx, cy), preserving sprite pivot offset
void draw_sprite_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId)
{
  const short *origin = atlas.point(spriteId, 0);
  int x = cx - (atlas.xres(spriteId) / 2);
  int y = cy - (atlas.yres(spriteId) / 2);
  atlas.draw(g, spriteId, x + origin[0], y + origin[1]);
}

// Per-pixel rotation around sprite pivot and destination center
void draw_sprite_rotated_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float angleDeg)
{
  if(spriteId < 0 || spriteId >= atlas.count)
    return;

  Sprite &sp = atlas.sprites[spriteId];
  const short *origin = atlas.point(spriteId, 0);
  const float rad = angleDeg * (3.14159265f / 180.0f);
  const float c = cosf(rad);
  const float s = sinf(rad);

  int step = s_transform_step;
  int i = 0;
  for(int sy = 0; sy < sp.yres; sy++)
  {
    for(int sx = 0; sx < sp.xres; sx++, i++)
    {
      if(step > 1 && ((sx % step) != 0 || (sy % step) != 0))
        continue;
      unsigned char col = sp.pixels[i];
      if(col == sp.transparency)
        continue;

      const float lx = (float)(sx - origin[0]);
      const float ly = (float)(sy - origin[1]);
      const int dx = cx + (int)roundf(lx * c - ly * s);
      const int dy = cy + (int)roundf(lx * s + ly * c);
      g.dot(dx, dy, col);
    }
  }
}

// Nearest-neighbor scale around sprite pivot and destination center
void draw_sprite_scaled_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float scale)
{
  if(spriteId < 0 || spriteId >= atlas.count)
    return;
  if(scale <= 0.01f)
    return;

  Sprite &sp = atlas.sprites[spriteId];
  const short *origin = atlas.point(spriteId, 0);
  const float invScale = 1.0f / scale;
  const int halfW = (int)ceilf((sp.xres * scale) * 0.5f);
  const int halfH = (int)ceilf((sp.yres * scale) * 0.5f);

  for(int dy = -halfH; dy <= halfH; dy++)
  {
    for(int dx = -halfW; dx <= halfW; dx++)
    {
      float lx = dx * invScale + origin[0];
      float ly = dy * invScale + origin[1];
      int sx = (int)floorf(lx + 0.5f);
      int sy = (int)floorf(ly + 0.5f);
      if((unsigned int)sx >= (unsigned int)sp.xres || (unsigned int)sy >= (unsigned int)sp.yres)
        continue;

      unsigned char col = sp.pixels[sy * sp.xres + sx];
      if(col == sp.transparency)
        continue;

      g.dot(cx + dx, cy + dy, col);
    }
  }
}

// Combined rotation + scale around sprite pivot and destination center
void draw_sprite_rotated_scaled_center(Graphics &g, Sprites &atlas, int cx, int cy, int spriteId, float angleDeg, float scale)
{
  if(spriteId < 0 || spriteId >= atlas.count)
    return;
  if(scale <= 0.01f)
    return;

  Sprite &sp = atlas.sprites[spriteId];
  const short *origin = atlas.point(spriteId, 0);
  const float rad = angleDeg * (3.14159265f / 180.0f);
  const float c = cosf(rad);
  const float s = sinf(rad);

  int step = s_transform_step;
  int i = 0;
  for(int sy = 0; sy < sp.yres; sy++)
  {
    for(int sx = 0; sx < sp.xres; sx++, i++)
    {
      if(step > 1 && ((sx % step) != 0 || (sy % step) != 0))
        continue;
      unsigned char col = sp.pixels[i];
      if(col == sp.transparency)
        continue;

      const float lx = (float)(sx - origin[0]);
      const float ly = (float)(sy - origin[1]);
      const float rx = (lx * c - ly * s) * scale;
      const float ry = (lx * s + ly * c) * scale;
      const int dx = cx + (int)roundf(rx);
      const int dy = cy + (int)roundf(ry);
      g.dot(dx, dy, col);
    }
  }
}

// Rotate-draw wrapper for an animated sprite instance
void sprite_draw_rotated(Graphics &g, SpriteInstance &inst, float angleDeg)
{
  if(!inst.visible || inst.clip == NULL || inst.clip->frameCount <= 0 || inst.clip->atlasRef == NULL || inst.clip->atlasRef->atlas == NULL)
    return;
  int idx = inst.clip->frames[inst.frameIndex];
  Sprites &atlas = *inst.clip->atlasRef->atlas;
  if(inst.center)
    draw_sprite_rotated_center(g, atlas, inst.x, inst.y, idx, angleDeg);
  else
    draw_sprite(g, atlas, inst.x, inst.y, idx);
}

// Scale-draw wrapper for an animated sprite instance
void sprite_draw_scaled(Graphics &g, SpriteInstance &inst, float scale)
{
  if(!inst.visible || inst.clip == NULL || inst.clip->frameCount <= 0 || inst.clip->atlasRef == NULL || inst.clip->atlasRef->atlas == NULL)
    return;
  int idx = inst.clip->frames[inst.frameIndex];
  Sprites &atlas = *inst.clip->atlasRef->atlas;
  if(inst.center)
    draw_sprite_scaled_center(g, atlas, inst.x, inst.y, idx, scale);
  else
    draw_sprite(g, atlas, inst.x, inst.y, idx);
}

// Start or switch animation clip for one instance
void anim_play(SpriteInstance &inst, const AnimationClip &clip, bool restart)
{
  inst.clip = &clip;
  inst.visible = true;
  inst.paused = false;
  if(restart || inst.frameIndex >= clip.frameCount)
    inst.frameIndex = 0;
  inst.nextFrameMs = 0;
}

void anim_pause(SpriteInstance &inst)
{
  inst.paused = true;
}

void anim_resume(SpriteInstance &inst)
{
  inst.paused = false;
  inst.nextFrameMs = 0;
}

void anim_stop(SpriteInstance &inst)
{
  inst.visible = false;
  inst.paused = false;
  inst.frameIndex = 0;
  inst.nextFrameMs = 0;
}

// Advance animation frame based on clip FPS
void anim_update(SpriteInstance &inst, unsigned long nowMs)
{
  if(!inst.visible || inst.paused || inst.clip == NULL || inst.clip->frameCount <= 0)
    return;
  if(nowMs < inst.nextFrameMs)
    return;

  int frameMs = 1000 / (inst.clip->fps > 0 ? inst.clip->fps : 1);
  inst.nextFrameMs = nowMs + frameMs;
  inst.frameIndex++;
  if(inst.frameIndex >= inst.clip->frameCount)
  {
    if(inst.clip->loop)
      inst.frameIndex = 0;
    else
      inst.frameIndex = inst.clip->frameCount - 1;
  }
}

// Draw current frame from the instance clip
void anim_draw(Graphics &g, SpriteInstance &inst)
{
  if(!inst.visible || inst.clip == NULL || inst.clip->frameCount <= 0 || inst.clip->atlasRef == NULL || inst.clip->atlasRef->atlas == NULL)
    return;
  int idx = inst.clip->frames[inst.frameIndex];
  Sprites &atlas = *inst.clip->atlasRef->atlas;
  if(inst.center)
    draw_sprite_center(g, atlas, inst.x, inst.y, idx);
  else
    draw_sprite(g, atlas, inst.x, inst.y, idx);
}
