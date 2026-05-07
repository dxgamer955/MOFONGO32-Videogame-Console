#include "AudioApi.h"
#include <Arduino.h>
#include <string.h>
#include <math.h>
#include "esp32-hal-ledc.h"
#include "driver/dac.h"
#include "driver/timer.h"
#include "soc/timer_group_struct.h"

namespace AudioApi
{
// Audio simple por PWM/timer. MASA solo pide "song" o "beep";
#ifdef SONGS_HAS_4CH
static const int kAudioVoices = 4;
#else
static const int kAudioVoices = 1;
#endif

// Internal runtime state
static int s_pin = 26;
static int s_channel = 0;
static int s_pwmFreq = 156250;
static const int s_sampleRate = 12000;
static bool s_audioTimerInit = false;
static const timer_group_t s_audioTimerGroup = TIMER_GROUP_1;
static const timer_idx_t s_audioTimerIdx = TIMER_0;

static volatile uint32_t s_voicePhase[kAudioVoices] = {0};
static volatile uint32_t s_voiceStep[kAudioVoices] = {0};
static volatile uint8_t s_voiceWave[kAudioVoices] = {0};
static volatile uint8_t s_voiceVol[kAudioVoices] = {64};
static volatile uint8_t s_voiceOn[kAudioVoices] = {0};
static volatile uint16_t s_noiseLfsr[kAudioVoices] = {0x1ACE, 0x2B5D, 0x35E7, 0x3F2D};
static volatile uint32_t s_sfxPhase = 0;
static volatile uint32_t s_sfxStep = 0;
static volatile uint8_t s_sfxWave = 0;
static volatile uint8_t s_sfxVol = 220;
static volatile uint8_t s_sfxOn = 0;

#ifdef SONGS_HAS_4CH
struct VoiceTrack
{
  const float *notes;
  const unsigned short *durMs;
  int len;
  int index;
  unsigned long nextChangeMs;
  uint8_t wave;
  bool active;
};
static VoiceTrack s_tracks[4];
static int s_trackCount = 0;
#else
static const float *s_trackNotes = NULL;
static const unsigned short *s_trackDurMs = NULL;
static int s_trackLen = 0;
static int s_trackIndex = 0;
static unsigned long s_trackNextChangeMs = 0;
#endif

static const SongDef *s_current = NULL;
static bool s_loop = false;
static bool s_paused = false;
static bool s_beepActive = false;
static uint32_t s_beepUntilMs = 0;

// Force output to silence
static void output_silence()
{
  ledcWriteTone(s_channel, 0);
  ledcWrite(s_channel, 0);
}

static inline uint32_t hz_to_step(float hz)
{
  if(hz <= 1.0f)
    return 0;
  const double k = 4294967296.0 / (double)s_sampleRate;
  double v = (double)hz * k;
  if(v < 0.0)
    v = 0.0;
  if(v > 4294967295.0)
    v = 4294967295.0;
  return (uint32_t)(v + 0.5);
}

static void set_voice(int idx, float hz, uint8_t wave, uint8_t vol)
{
  if(idx < 0 || idx >= kAudioVoices)
    return;
  // Raise noise channel by 1.5 octaves for clearer percussion presence
  if(wave == 3)
    hz *= 2.8284271f;
  if(hz <= 1.0f)
  {
    s_voiceOn[idx] = 0;
    s_voiceStep[idx] = 0;
    return;
  }
  s_voiceWave[idx] = wave;
  s_voiceVol[idx] = vol;
  s_voiceStep[idx] = hz_to_step(hz);
  s_voiceOn[idx] = (s_voiceStep[idx] > 0) ? 1 : 0;
}

static void silence_all_voices()
{
  for(int i = 0; i < kAudioVoices; i++)
  {
    s_voiceOn[i] = 0;
    s_voiceStep[i] = 0;
  }
}

static int song_index_from_name(const char *name)
{
  if(name == NULL || name[0] == 0)
    return -1;
  for(int i = 0; i < songsCount; i++)
  {
    if(songs[i].name && strcmp(songs[i].name, name) == 0)
      return i;
  }
  return -1;
}

static void clear_tracks()
{
#ifdef SONGS_HAS_4CH
  for(int i = 0; i < kAudioVoices; i++)
  {
    s_tracks[i].notes = NULL;
    s_tracks[i].durMs = NULL;
    s_tracks[i].len = 0;
    s_tracks[i].index = 0;
    s_tracks[i].nextChangeMs = 0;
    s_tracks[i].wave = 0;
    s_tracks[i].active = false;
  }
  s_trackCount = 0;
#else
  s_trackNotes = NULL;
  s_trackDurMs = NULL;
  s_trackLen = 0;
  s_trackIndex = 0;
  s_trackNextChangeMs = 0;
#endif
}

static void start_tracks_from_song(const SongDef *song)
{
  clear_tracks();
  if(song == NULL)
    return;

#ifdef SONGS_HAS_4CH
  int si = song_index_from_name(song->name);
  if(si >= 0)
  {
    const SongChannelsDef &sc = songsCh[si];
    for(int i = 0; i < kAudioVoices && i < (int)sc.channelCount; i++)
    {
      if(sc.notes[i] == nullptr || sc.durMs[i] == nullptr || sc.len[i] <= 0)
        continue;
      s_tracks[s_trackCount].notes = sc.notes[i];
      s_tracks[s_trackCount].durMs = sc.durMs[i];
      s_tracks[s_trackCount].len = sc.len[i];
      s_tracks[s_trackCount].index = 0;
      s_tracks[s_trackCount].nextChangeMs = 0;
      // Force sound style NES-like mapping by channel index:
      // 0=pulse1, 1=pulse2, 2=triangle, 3=noise.
      s_tracks[s_trackCount].wave = (uint8_t)i;
      s_tracks[s_trackCount].active = true;
      s_trackCount++;
    }
  }
#endif

#ifdef SONGS_HAS_4CH
  if(s_trackCount <= 0)
  {
    if(song->notes != NULL && song->durMs != NULL && song->len > 0)
    {
      s_tracks[0].notes = song->notes;
      s_tracks[0].durMs = song->durMs;
      s_tracks[0].len = song->len;
      s_tracks[0].index = 0;
      s_tracks[0].nextChangeMs = 0;
      s_tracks[0].wave = 0;
      s_tracks[0].active = true;
      s_trackCount = 1;
    }
  }
#else
  if(song->notes != NULL && song->durMs != NULL && song->len > 0)
  {
    s_trackNotes = song->notes;
    s_trackDurMs = song->durMs;
    s_trackLen = song->len;
    s_trackIndex = 0;
    s_trackNextChangeMs = 0;
  }
#endif
}

static int16_t wave_sample(int voice, uint8_t wave, uint32_t phase, bool wrapped)
{
  switch(wave)
  {
    // channel 0 pulse: 50%
    case 0:
      return (phase & 0x80000000UL) ? 110 : -110;
    // channel 1 pulse: 25%
    case 1:
      return ((phase >> 30) == 0) ? 96 : -96;
    // triangle
    case 2:
    {
      uint8_t p = (uint8_t)(phase >> 27); // 0..31
      int t = (p < 16) ? (p * 16 - 120) : (120 - (int)(p - 16) * 16);
      return (int16_t)t;
    }
    // noise
    case 3:
    default:
      if(wrapped)
      {
        uint16_t l = s_noiseLfsr[voice];
        uint16_t bit = (uint16_t)((l ^ (l >> 1)) & 1U);
        l = (uint16_t)((l >> 1) | (bit << 14));
        if(l == 0)
          l = 1;
        s_noiseLfsr[voice] = l;
      }
      return (s_noiseLfsr[voice] & 1U) ? 90 : -90;
  }
}

void IRAM_ATTR timerInterruptAudio(void *)
{
  uint32_t intStatus = TIMERG1.int_st_timers.val;
  if(intStatus & BIT(TIMER_0))
  {
    TIMERG1.hw_timer[TIMER_0].update = 1;
    TIMERG1.int_clr_timers.t0 = 1;
    TIMERG1.hw_timer[TIMER_0].config.alarm_en = 1;

    bool pulse1Active = false;
    for(int i = 0; i < kAudioVoices; i++)
    {
      if(s_voiceOn[i] && s_voiceStep[i] != 0 && s_voiceWave[i] == 0)
      {
        pulse1Active = true;
        break;
      }
    }

    int mix = 0;
    for(int i = 0; i < kAudioVoices; i++)
    {
      if(!s_voiceOn[i] || s_voiceStep[i] == 0)
        continue;
      uint32_t oldPhase = s_voicePhase[i];
      uint32_t newPhase = oldPhase + s_voiceStep[i];
      s_voicePhase[i] = newPhase;
      bool wrapped = (newPhase < oldPhase);
      int16_t ws = wave_sample(i, s_voiceWave[i], newPhase, wrapped);

      int sample = (int(ws) * int(s_voiceVol[i])) / 255;
      int weight = 256;
      switch(s_voiceWave[i])
      {
        case 0: weight = 256; break; // pulse1 lead
        case 1: weight = 192; break; // pulse2 support
        case 2: weight = 176; break; // triangle bass
        case 3: weight = pulse1Active ? 104 : 140; break; // duck noise under lead
        default: weight = 192; break;
      }
      mix += (sample * weight) / 256;
    }

    if(s_sfxOn && s_sfxStep != 0)
    {
      uint32_t oldPhase = s_sfxPhase;
      uint32_t newPhase = oldPhase + s_sfxStep;
      s_sfxPhase = newPhase;
      bool wrapped = (newPhase < oldPhase);
      int16_t ws = wave_sample(0, s_sfxWave, newPhase, wrapped);
      int s = (int(ws) * int(s_sfxVol)) / 255;
      mix += s;
    }

    // Soft clip for louder output without hard digital clipping.
    if(mix > 384)
      mix = 384;
    if(mix < -384)
      mix = -384;
    int a = (mix >= 0) ? mix : -mix;
    mix = (mix * (512 - a)) / 512;

    if(mix > 127)
      mix = 127;
    if(mix < -127)
      mix = -127;
    dac_output_voltage(DAC_CHANNEL_2, (uint8_t)(mix + 128));
  }
}

// Configure PWM channel used as simple tone generator.
void init(int pin, int channel, int pwmFreq)
{
  s_pin = pin;
  s_channel = channel;
  s_pwmFreq = pwmFreq;
  ledcSetup(s_channel, s_pwmFreq, 8);
  ledcAttachPin(s_pin, s_channel);
  output_silence();
  silence_all_voices();
#ifdef SONGS_HAS_4CH
  s_voiceVol[0] = 200;
  s_voiceVol[1] = 190;
  s_voiceVol[2] = 180;
  s_voiceVol[3] = 170;
#endif

  if(!s_audioTimerInit)
  {
    dac_output_enable(DAC_CHANNEL_2);
    dac_output_voltage(DAC_CHANNEL_2, 128);

    timer_config_t config;
    config.alarm_en = TIMER_ALARM_EN;
    config.auto_reload = TIMER_AUTORELOAD_EN;
    config.counter_dir = TIMER_COUNT_UP;
    config.divider = 16;
    config.intr_type = TIMER_INTR_LEVEL;
    config.counter_en = TIMER_PAUSE;
    timer_init(s_audioTimerGroup, s_audioTimerIdx, &config);
    timer_pause(s_audioTimerGroup, s_audioTimerIdx);
    timer_set_counter_value(s_audioTimerGroup, s_audioTimerIdx, 0ULL);
    timer_set_alarm_value(s_audioTimerGroup, s_audioTimerIdx, (uint64_t)((double)TIMER_BASE_CLK / (double)config.divider / (double)s_sampleRate));
    timer_enable_intr(s_audioTimerGroup, s_audioTimerIdx);
    timer_isr_register(s_audioTimerGroup, s_audioTimerIdx, timerInterruptAudio, NULL, 0, NULL);
    timer_start(s_audioTimerGroup, s_audioTimerIdx);
    s_audioTimerInit = true;
  }
}

static int note_index(char c)
{
  switch(c)
  {
    case 'C': return 0;
    case 'D': return 2;
    case 'E': return 4;
    case 'F': return 5;
    case 'G': return 7;
    case 'A': return 9;
    case 'B': return 11;
    default: return -1;
  }
}

static int note_to_hz(const char *note)
{
  if(note == NULL || note[0] == 0)
    return 0;
  char n = note[0];
  if(n >= 'a' && n <= 'z')
    n = (char)(n - 'a' + 'A');
  int base = note_index(n);
  if(base < 0)
    return 0;
  int i = 1;
  if(note[i] == '#')
  {
    base += 1;
    i++;
  }
  else if(note[i] == 'b' || note[i] == 'B')
  {
    base -= 1;
    i++;
  }
  int sign = 1;
  if(note[i] == '-')
  {
    sign = -1;
    i++;
  }
  if(note[i] < '0' || note[i] > '9')
    return 0;
  int octave = 0;
  while(note[i] >= '0' && note[i] <= '9')
  {
    octave = octave * 10 + (note[i] - '0');
    i++;
  }
  octave *= sign;
  int midi = (octave + 1) * 12 + base;
  float hz = 440.0f * powf(2.0f, ((float)midi - 69.0f) / 12.0f);
  if(hz < 1.0f)
    return 0;
  if(hz > 20000.0f)
    hz = 20000.0f;
  return (int)(hz + 0.5f);
}

// Find a song entry by exact name
const SongDef *get_sound(const char *name)
{
  if(name == NULL)
    return NULL;
  for(int i = 0; i < songsCount; i++)
  {
    if(strcmp(songs[i].name, name) == 0)
      return &songs[i];
  }
  return NULL;
}

// Start playback from beginning
void play_sound(const SongDef &sound, bool loop)
{
  s_current = &sound;
  s_loop = loop;
  s_paused = false;
  start_tracks_from_song(s_current);
}

// Stop only if the requested sound is currently active
void stop_sound(const SongDef &sound)
{
  if(s_current != &sound)
    return;
  s_current = NULL;
  s_paused = false;
  clear_tracks();
  silence_all_voices();
  output_silence();
}

// Pause current sound and mute output
void pause_sound(const SongDef &sound)
{
  if(s_current != &sound)
    return;
  s_paused = true;
  silence_all_voices();
  output_silence();
}

// Resume without resetting song index
void resume_sound(const SongDef &sound)
{
  if(s_current != &sound)
    return;
  if(!s_paused)
    return;
  s_paused = false;
#ifdef SONGS_HAS_4CH
  for(int i = 0; i < s_trackCount; i++)
  {
    s_tracks[i].nextChangeMs = 0;
  }
#else
  s_trackNextChangeMs = 0;
#endif
}

// Restart from first note (or start if different sound)
void restart_sound(const SongDef &sound)
{
  if(s_current != &sound)
  {
    play_sound(sound, false);
    return;
  }
  s_paused = false;
  start_tracks_from_song(s_current);
}

// emits tone/silence and advances timed sequence
void update()
{
  unsigned long now = millis();
  if(s_beepActive)
  {
    if(now >= s_beepUntilMs)
    {
      s_beepActive = false;
      s_sfxOn = 0;
      s_sfxStep = 0;
    }
  }

  if(s_current == NULL || s_paused)
    return;

#ifdef SONGS_HAS_4CH
  bool anyActive = false;
  for(int i = 0; i < s_trackCount; i++)
  {
    VoiceTrack &t = s_tracks[i];
    if(!t.active)
      continue;
    anyActive = true;
    if(now < t.nextChangeMs)
      continue;

    if(t.index >= t.len)
    {
      if(s_loop)
      {
        t.index = 0;
      }
      else
      {
        t.active = false;
        set_voice(i, 0.0f, t.wave, 0);
        continue;
      }
    }

    float note = t.notes[t.index];
    unsigned short dur = t.durMs[t.index];
    t.nextChangeMs = now + dur;
    t.index++;
    set_voice(i, note, t.wave, s_voiceVol[i]);
  }

  if(!anyActive)
  {
    const SongDef *cur = s_current;
    if(cur != NULL)
      stop_sound(*cur);
  }
#else
  if(s_trackNotes == NULL || s_trackDurMs == NULL || s_trackLen <= 0)
    return;
  if(now < s_trackNextChangeMs)
    return;
  if(s_trackIndex >= s_trackLen)
  {
    if(s_loop)
      s_trackIndex = 0;
    else
    {
      const SongDef *cur = s_current;
      if(cur != NULL)
        stop_sound(*cur);
      return;
    }
  }
  float note = s_trackNotes[s_trackIndex];
  unsigned short dur = s_trackDurMs[s_trackIndex];
  s_trackNextChangeMs = now + dur;
  s_trackIndex++;
  set_voice(0, note, 0, s_voiceVol[0]);
#endif
}

void beep_hz(int hz, int durationMs)
{
  beep_wave_hz(0, hz, durationMs);
}

void beep_square_hz(int hz, int durationMs)
{
  beep_wave_hz(0, hz, durationMs);
}

void beep_noise_hz(int hz, int durationMs)
{
  beep_wave_hz(3, hz, durationMs);
}

void beep_wave_hz(uint8_t wave, int hz, int durationMs)
{
  if(hz <= 0 || durationMs <= 0)
    return;
  if(hz > 20000)
    hz = 20000;
  s_beepUntilMs = millis() + (uint32_t)durationMs;
  s_beepActive = true;
  s_sfxWave = (uint8_t)(wave & 0x03);
  s_sfxPhase = 0;
  s_sfxStep = hz_to_step((float)hz);
  s_sfxOn = (s_sfxStep > 0) ? 1 : 0;
}

void beep_note(const char *note, int durationMs)
{
  beep_wave_note(0, note, durationMs);
}

void beep_wave_note(uint8_t wave, const char *note, int durationMs)
{
  int hz = note_to_hz(note);
  if(hz <= 0)
    return;
  beep_wave_hz(wave, hz, durationMs);
}

bool has_current_song()
{
  return s_current != NULL;
}

bool is_paused()
{
  return s_paused;
}

const char *current_song_name()
{
  return s_current ? s_current->name : "NONE";
}
}
