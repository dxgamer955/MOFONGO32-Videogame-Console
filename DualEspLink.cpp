#include "DualEspLink.h"

#include <SPI.h>
#include "driver/spi_slave.h"
#include "esp_heap_caps.h"
#include <string.h>

#if defined(SPI2_HOST)
#define DUAL_SPI_SLAVE_HOST SPI2_HOST
#elif defined(HSPI_HOST)
#define DUAL_SPI_SLAVE_HOST HSPI_HOST
#else
#define DUAL_SPI_SLAVE_HOST VSPI_HOST
#endif

#if defined(SPI_DMA_CH_AUTO)
#define DUAL_SPI_DMA_CH SPI_DMA_CH_AUTO
#else
#define DUAL_SPI_DMA_CH 1
#endif

namespace DualEspLink
{
// Link de compatibilidad para el demo dual-ESP antes de MASA
// Se deja activo porque el sketch todavia puede compilar rutas no-MASA
static SPIClass s_spi(VSPI);
static int s_csPin = 5;
static uint32_t s_hz = 2000000;
static bool s_masterInit = false;

static uint8_t *s_rxBuf = NULL;
static bool s_slaveInit = false;

static uint16_t checksum_crc16(const uint8_t *data, size_t n)
{
  uint16_t crc = 0xFFFF;
  for(size_t i = 0; i < n; i++)
  {
    crc ^= (uint16_t)data[i];
    for(int b = 0; b < 8; b++)
    {
      if(crc & 1)
        crc = (crc >> 1) ^ 0xA001;
      else
        crc >>= 1;
    }
  }
  return crc;
}

void begin_master(int sclkPin, int misoPin, int mosiPin, int csPin, uint32_t hz)
{
  s_csPin = csPin;
  s_hz = hz;
  s_spi.begin(sclkPin, misoPin, mosiPin, csPin);
  pinMode(s_csPin, OUTPUT);
  digitalWrite(s_csPin, HIGH);
  s_masterInit = true;
}

bool send_master(FrameState &state)
{
  if(!s_masterInit)
    return false;

  state.magic = kMagic;
  state.version = kVersion;
  state.checksum = 0;
  state.checksum = checksum_crc16((const uint8_t *)&state, sizeof(FrameState));

  s_spi.beginTransaction(SPISettings(s_hz, MSBFIRST, SPI_MODE0));
  digitalWrite(s_csPin, LOW);
  s_spi.transferBytes((uint8_t *)&state, NULL, sizeof(FrameState));
  digitalWrite(s_csPin, HIGH);
  s_spi.endTransaction();
  return true;
}

void begin_slave(int sclkPin, int misoPin, int mosiPin, int csPin)
{
  spi_bus_config_t buscfg = {};
  buscfg.mosi_io_num = mosiPin;
  buscfg.miso_io_num = misoPin;
  buscfg.sclk_io_num = sclkPin;
  buscfg.quadwp_io_num = -1;
  buscfg.quadhd_io_num = -1;
  buscfg.max_transfer_sz = sizeof(FrameState);

  spi_slave_interface_config_t slvcfg = {};
  slvcfg.spics_io_num = csPin;
  slvcfg.flags = 0;
  slvcfg.queue_size = 1;
  slvcfg.mode = 0;

  if(spi_slave_initialize(DUAL_SPI_SLAVE_HOST, &buscfg, &slvcfg, DUAL_SPI_DMA_CH) != ESP_OK)
    return;

  s_rxBuf = (uint8_t *)heap_caps_malloc(sizeof(FrameState), MALLOC_CAP_DMA | MALLOC_CAP_8BIT);
  if(s_rxBuf == NULL)
    return;

  memset(s_rxBuf, 0, sizeof(FrameState));
  s_slaveInit = true;
}

bool recv_slave(FrameState &state, uint32_t timeoutMs)
{
  if(!s_slaveInit || s_rxBuf == NULL)
    return false;

  spi_slave_transaction_t t = {};
  t.length = sizeof(FrameState) * 8;
  t.rx_buffer = s_rxBuf;
  t.tx_buffer = NULL;
  esp_err_t err = spi_slave_transmit(DUAL_SPI_SLAVE_HOST, &t, timeoutMs == 0 ? 0 : pdMS_TO_TICKS(timeoutMs));
  if(err != ESP_OK)
    return false;

  memcpy(&state, s_rxBuf, sizeof(FrameState));
  uint16_t got = state.checksum;
  state.checksum = 0;
  uint16_t calc = checksum_crc16((const uint8_t *)&state, sizeof(FrameState));
  state.checksum = got;
  if(got != calc)
    return false;
  if(state.magic != kMagic || state.version != kVersion)
    return false;
  if(state.objectCount > kMaxObjects)
    return false;
  return true;
}
}
