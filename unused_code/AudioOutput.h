#include "soc/timer_group_struct.h"
#include "driver/timer.h"
#include "driver/dac.h"

class AudioOutput;
void IRAM_ATTR timerInterrupt(AudioOutput *audioOutput);

class AudioOutput
{
  public:
  AudioSystem *audioSystem;
  static const dac_channel_t AUDIO_DAC_CHANNEL = DAC_CHANNEL_2; //GPIO26
  
  void init(AudioSystem &audioSystem)
  {
    this->audioSystem = &audioSystem;
    //Use dedicated DAC channel for audio, independent from composite I2S video.
    dac_output_enable(AUDIO_DAC_CHANNEL);
    dac_output_voltage(AUDIO_DAC_CHANNEL, 128);

    timer_config_t config;
    config.alarm_en = 1;
    config.auto_reload = 1;
    config.counter_dir = TIMER_COUNT_UP;
    config.divider = 16;
    config.intr_type = TIMER_INTR_LEVEL;
    config.counter_en = TIMER_PAUSE;
    timer_init((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0, &config);
    timer_pause((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0);
    timer_set_counter_value((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0, 0x00000000ULL);
    timer_set_alarm_value((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0, 1.0/audioSystem.samplingRate * TIMER_BASE_CLK / config.divider);
    timer_enable_intr((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0);
    timer_isr_register((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0, (void (*)(void*))timerInterrupt, (void*) this, 0, NULL);
    timer_start((timer_group_t)TIMER_GROUP_0, (timer_idx_t)TIMER_0);
  }
};

void IRAM_ATTR timerInterrupt(AudioOutput *audioOutput)
{
  uint32_t intStatus = TIMERG0.int_st_timers.val;
  if(intStatus & BIT(TIMER_0)) 
  {
      TIMERG0.hw_timer[TIMER_0].update = 1;
      TIMERG0.int_clr_timers.t0 = 1;
      TIMERG0.hw_timer[TIMER_0].config.alarm_en = 1;

      //Push audio sample to dedicated DAC pin (GPIO26).
      dac_output_voltage(AudioOutput::AUDIO_DAC_CHANNEL, audioOutput->audioSystem->nextSample());
  }
}  
