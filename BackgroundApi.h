#pragma once

#include "Graphics.h"

namespace BackgroundApi
{
// API pequena para seleccionar y dibujar fondos del juego
// La data concreta viene de gfx/backgrounds.h, generado por las herramientas Python
// Built-in procedural backgrounds
enum ProceduralBg
{
  BG_BANDS = 0,
  BG_GRID = 1,
  BG_STARS = 2,
};

// Initialize module with target screen size
void init(int screenW, int screenH);

// Select built-in background or converted image background
void set_procedural(int bgId);
void set_image(int bgId);
void clear_image();
void set_color(int colorIndex);
void clear_color();
int current_color();

// Scroll offset controls for image backgrounds
void set_scroll(int x, int y);
void add_scroll(int dx, int dy);
int scroll_x();
int scroll_y();

// Current background selection
int current_procedural();
int current_image();
int image_count();

// Draw currently selected background
void draw(Graphics &graphics, unsigned long nowMs);
}
