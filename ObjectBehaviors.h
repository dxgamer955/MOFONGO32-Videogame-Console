#pragma once

#include <Arduino.h>

// Behaviors legacy usados cuando no existe generated/program_logic.h
// Sirven como fallback/demo para rooms exportadas viejas
struct ObjectRenderState
{
  int frame;
  int mode;      // 0=normal, 1=rotated, 2=scaled
  int x;
  int y;
  float angle;   // used when mode=rotated
  float scale;   // used when mode=scaled
  bool visible;
};

// Apply per-object behavior overrides
// Edit ObjectBehaviors.cpp to add custom logic for specific objects
void apply_object_behavior(int roomObjectIndex, unsigned long nowMs, ObjectRenderState &state);
