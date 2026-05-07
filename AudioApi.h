#pragma once

#include <stdint.h>
#include "gfx/songs.h"

namespace AudioApi
{
// API del audio para el sketch y MasaRuntime.
// Internamente usa el timer/PWM del ESP32
// Initialize PWM audio output.
void init(int pin, int channel, int pwmFreq);

// Song lookup by name from songs.h table.
const SongDef *get_sound(const char *name);

// Playback controls (Parte del API).
void play_sound(const SongDef &sound, bool loop);
void stop_sound(const SongDef &sound);
void pause_sound(const SongDef &sound);
void resume_sound(const SongDef &sound);
void restart_sound(const SongDef &sound);

// Call every frame to advance note timing.
void update();

// Play a one-shot square-wave tone on the buzzer pin.
void beep_hz(int hz, int durationMs);
void beep_wave_hz(uint8_t wave, int hz, int durationMs);
void beep_square_hz(int hz, int durationMs);
void beep_noise_hz(int hz, int durationMs);

// convert note names like "C4", "F#5", "Bb3" and beep.
void beep_note(const char *note, int durationMs);
void beep_wave_note(uint8_t wave, const char *note, int durationMs);

// Lightweight state accessors for UI/debug.
bool has_current_song();
bool is_paused();
const char *current_song_name();
}
