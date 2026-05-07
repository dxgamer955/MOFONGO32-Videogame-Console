#include "BackgroundApi.h"
#include "gfx/backgrounds.h"

namespace BackgroundApi
{
// Maneja fondos procedural y fondos convertidos desde PNG
// El runtime solo cambia indices/scroll, este modulo hace el dibujo real sobre Graphics
// Internal background state
static int s_xres = 320;
static int s_yres = 200;
static int s_procedural = BG_BANDS;
static int s_image = -1;
static int s_color = 0;
static bool s_useColor = false;
static int s_scrollX = 0;
static int s_scrollY = 0;

void init(int screenW, int screenH)
{
  s_xres = screenW;
  s_yres = screenH;
}

// Select active procedural background id
void set_procedural(int bgId)
{
  if(bgId < BG_BANDS || bgId > BG_STARS)
    return;
  s_procedural = bgId;
}

// Select active converted image background id
void set_image(int bgId)
{
  if(bgId < 0 || bgId >= backgroundsCount)
    return;
  s_image = bgId;
}

void clear_image()
{
  s_image = -1;
}

void set_color(int colorIndex)
{
  s_color = colorIndex;
  s_useColor = true;
}

void clear_color()
{
  s_useColor = false;
}

int current_color()
{
  return s_color;
}

// Absolute scroll offset
void set_scroll(int x, int y)
{
  s_scrollX = x;
  s_scrollY = y;
}

// Incremental scroll offset
void add_scroll(int dx, int dy)
{
  s_scrollX += dx;
  s_scrollY += dy;
}

int scroll_x()
{
  return s_scrollX;
}

int scroll_y()
{
  return s_scrollY;
}

int current_procedural()
{
  return s_procedural;
}

int current_image()
{
  return s_image;
}

int image_count()
{
  return backgroundsCount;
}

// Draw converted background with wrap-around scrolling
static void draw_image(Graphics &graphics, int bgId)
{
  if(bgId < 0 || bgId >= backgroundsCount)
    return;

  int w = backgroundsWidth;
  int h = backgroundsHeight;
  if(w <= 0 || h <= 0)
    return;

  int offX = s_scrollX % w;
  int offY = s_scrollY % h;
  if(offX < 0) offX += w;
  if(offY < 0) offY += h;

  int offset = backgroundsOffsets[bgId];
  for(int y = 0; y < s_yres; y++)
  {
    int sy = (y + offY) % h;
    int rowOff = offset + sy * w;
    for(int x = 0; x < s_xres; x++)
    {
      int sx = (x + offX) % w;
      graphics.dot(x, y, backgroundsPixels[rowOff + sx]);
    }
  }
}

// Draw one of the simple built-in procedural effects
static void draw_procedural(Graphics &graphics, int bgId, unsigned long nowMs)
{
  const int t = (int)(nowMs / 16);
  if(bgId == BG_BANDS)
  {
    for(int y = 0; y < s_yres; y += 20)
    {
      int c = ((y / 4) + (t / 6)) % 54;
      graphics.fillRect(0, y, s_xres, 12, c);
    }
    return;
  }

  if(bgId == BG_GRID)
  {
    graphics.fillRect(0, 0, s_xres, s_yres, 4);
    int sx = (t / 2) % 16;
    int sy = (t / 3) % 16;
    for(int x = -sx; x < s_xres; x += 16)
      graphics.fillRect(x, 0, 1, s_yres, 14);
    for(int y = -sy; y < s_yres; y += 16)
      graphics.fillRect(0, y, s_xres, 1, 14);
    return;
  }

  graphics.fillRect(0, 0, s_xres, s_yres, 0);
  for(int i = 0; i < 64; i++)
  {
    int x = (i * 37 + t / 3) % s_xres;
    int y = (i * 53 + t / 5) % s_yres;
    graphics.dot(x, y, 20 + (i % 30));
  }
  for(int i = 0; i < 24; i++)
  {
    int x = (i * 91 + t / 2) % s_xres;
    int y = (i * 47 + t / 4) % s_yres;
    graphics.dot(x, y, 54);
  }
}

// Draw whichever mode is currently selected
void draw(Graphics &graphics, unsigned long nowMs)
{
  if(s_image >= 0 && backgroundsCount > 0)
    draw_image(graphics, s_image);
  else if(s_useColor)
    graphics.fillRect(0, 0, s_xres, s_yres, s_color);
  else
    draw_procedural(graphics, s_procedural, nowMs);
}
}
