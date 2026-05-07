#pragma once
#include <Arduino.h>

#ifndef ENABLE_WEB_CONTROLLER
#define ENABLE_WEB_CONTROLLER 0
#endif

namespace WebInput
{
// Control web opcional para debug cuando no hay Bluepad32 conectado
// Se mantiene apagado por default en AudioVideoExample.ino
enum Button
{
  BTN_UP = 0,
  BTN_DOWN = 1,
  BTN_LEFT = 2,
  BTN_RIGHT = 3,
  BTN_A = 4,
  BTN_B = 5,
  BTN_X = 6,
  BTN_Y = 7,
  BTN_START = 8,
  BTN_SELECT = 9,
  BTN_L = 10,
  BTN_R = 11,
  BTN_MAX = 12
};

void begin();
void handle();
bool down(Button b);
bool pressed(Button b);
}
