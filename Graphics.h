#pragma once
class TriangleTree;
class Font;

// Framebuffer 8-bit del proyecto. No conoce video compuesto directamente
// solo pinta en backbuffer y CompositeColorOutput lo consume despues
class Graphics
{ 
  public:
  int xres;
  int yres;
  char **frame;
  char **backbuffer;
  char **zbuffer;
  int cursorX, cursorY, cursorBaseX;
  int frontColor, backColor;
  Font *font;
  
  TriangleTree *triangleBuffer;
  TriangleTree *triangleRoot;
  int trinagleBufferSize;
  int triangleCount;

  Graphics(int w, int h, int initialTrinagleBufferSize = 0);
  static void setColorModeAtari(bool enabled);
  static void setLegacyGrayMapping(bool enabled);
  static void setDrawOffset(int x, int y);
  static int drawOffsetX();
  static int drawOffsetY();
  static void setGlobalHue(unsigned char hue);
  static unsigned char globalHue();
  void setTextColor(int front, int back = -1);
  void init();
  
  void setFont(Font &font);
  void setCursor(int x, int y);
  void print(const char *str);
  void print(int number, int base = 10, int minCharacters = 1);
  
  void begin(int clear = -1);
  void flush();
  void end();

  inline static char encodeColor(char color)
  {
    if(!s_atariColorMode)
      return color;
    if(!s_legacyGrayMapping)
      return color;

    unsigned char c = (unsigned char)color;
    // Keep transparency marker intact for code paths that may rely on it
    if(c == 255)
      return (char)255;

    // Legacy grayscale range (0..54) -> Atari color index with selected hue
    if(c <= 54)
    {
      unsigned char lum = (unsigned char)((c * 15 + 27) / 54);
      return (char)(((s_globalHue & 0x0F) << 4) | (lum & 0x0F));
    }

    // Values >54 are treated as direct Atari palette indices (0x00..0xFF)
    return color;
  }

  inline void dotFast(int x, int y, char color)
  {
    backbuffer[y + s_drawOffsetY][x + s_drawOffsetX] = encodeColor(color);
  }
  
  inline void dot(int x, int y, char color)
  {
    int tx = x + s_drawOffsetX;
    int ty = y + s_drawOffsetY;
    if((unsigned int)tx < xres && (unsigned int)ty < yres)
      backbuffer[ty][tx] = encodeColor(color);
  }
  
  inline void dotAdd(int x, int y, char color)
  {
    int tx = x + s_drawOffsetX;
    int ty = y + s_drawOffsetY;
    if((unsigned int)tx < xres && (unsigned int)ty < yres)
    {
      if(!s_atariColorMode)
      {
        backbuffer[ty][tx] = (color + backbuffer[ty][tx]) > 54 ? 54 : color + backbuffer[ty][tx];
      }
      else
      {
        unsigned char baseLum = ((unsigned char)backbuffer[ty][tx]) & 0x0F;
        unsigned char add = (unsigned char)color;
        unsigned char addLum = (add <= 54) ? (unsigned char)((add * 15 + 27) / 54) : (add & 0x0F);
        unsigned char outLum = (baseLum + addLum > 15) ? 15 : (baseLum + addLum);
        backbuffer[ty][tx] = (char)(((s_globalHue & 0x0F) << 4) | outLum);
      }
    }
  }
  
  inline char get(int x, int y)
  {
    int tx = x + s_drawOffsetX;
    int ty = y + s_drawOffsetY;
    if((unsigned int)tx < xres && (unsigned int)ty < yres)
      return backbuffer[ty][tx];
    return 0;
  }

  inline void xLine(int x0, int x1, int y, char color)
  {
    if(x0 > x1)
    {
      int xb = x0;
      x0 = x1;
      x1 = xb;
    }
    if(x0 < 0) x0 = 0;
    if(x1 > xres) x1 = xres;
    for(int x = x0; x < x1; x++)
      dotFast(x, y, color);
  }
    
  void enqueueTriangle(short *v0, short *v1, short *v2, char color);
  void triangle(short *v0, short *v1, short *v2, char color); 
  void line(int x1, int y1, int x2, int y2, char color);
  void fillRect(int x, int y, int w, int h, int color);
  void rect(int x, int y, int w, int h, int color);
  void circle(int cx, int cy, int r, int color);
  void fillCircle(int cx, int cy, int r, int color);

  private:
  static bool s_atariColorMode;
  static bool s_legacyGrayMapping;
  static int s_drawOffsetX;
  static int s_drawOffsetY;
  static unsigned char s_globalHue;
};
