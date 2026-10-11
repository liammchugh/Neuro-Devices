#include <Arduino.h>
#include "esp_adc/adc_continuous.h"
#include "esp_err.h"

// XIAO ESP32-S3: D0/A0 = GPIO1 = ADC1 channel 0.
constexpr uint32_t ADC_RATE_HZ = 20000;
constexpr uint32_t OUTPUT_RATE_HZ = 1000;
constexpr uint32_t DECIMATION = ADC_RATE_HZ / OUTPUT_RATE_HZ;
constexpr uint32_t BAUD_RATE = 460800;
constexpr size_t DMA_FRAME_BYTES = 256;
constexpr uint8_t MEDIAN_WINDOW = 5;

static adc_continuous_handle_t adc_handle = nullptr;
static uint32_t raw_counter = 0;
static uint32_t output_counter = 0;
static uint16_t median_history[MEDIAN_WINDOW] = {};
static uint8_t median_count = 0;
static uint8_t median_pos = 0;

static uint16_t medianFiltered(uint16_t value) {
  median_history[median_pos] = value;
  median_pos = (median_pos + 1) % MEDIAN_WINDOW;
  if (median_count < MEDIAN_WINDOW) median_count++;

  uint16_t sorted[MEDIAN_WINDOW];
  for (uint8_t i = 0; i < median_count; ++i) sorted[i] = median_history[i];
  for (uint8_t i = 1; i < median_count; ++i) {
    uint16_t key = sorted[i];
    int j = i - 1;
    while (j >= 0 && sorted[j] > key) {
      sorted[j + 1] = sorted[j];
      --j;
    }
    sorted[j + 1] = key;
  }
  return sorted[median_count / 2];
}

static void initializeADC() {
  adc_continuous_handle_cfg_t handle_cfg = {};
  handle_cfg.max_store_buf_size = 8192;
  handle_cfg.conv_frame_size = DMA_FRAME_BYTES;
  ESP_ERROR_CHECK(adc_continuous_new_handle(&handle_cfg, &adc_handle));

  adc_digi_pattern_config_t pattern = {};
  pattern.atten = ADC_ATTEN_DB_12;
  pattern.channel = ADC_CHANNEL_0;
  pattern.unit = ADC_UNIT_1;
  pattern.bit_width = ADC_BITWIDTH_12;

  adc_continuous_config_t config = {};
  config.sample_freq_hz = ADC_RATE_HZ;
  config.conv_mode = ADC_CONV_SINGLE_UNIT_1;
  config.format = ADC_DIGI_OUTPUT_FORMAT_TYPE2;
  config.pattern_num = 1;
  config.adc_pattern = &pattern;
  ESP_ERROR_CHECK(adc_continuous_config(adc_handle, &config));
  ESP_ERROR_CHECK(adc_continuous_start(adc_handle));
}

void setup() {
  Serial.begin(BAUD_RATE);
  // USB CDC may take a moment to enumerate; do not wait indefinitely.
  delay(1500);
  initializeADC();
  Serial.println("# XIAO ESP32-S3 EMG: sample_index,raw_adc,median_adc");
  Serial.println("# rate_hz=1000, adc_rate_hz=20000, pin=GPIO1");
}

void loop() {
  uint8_t dma_data[DMA_FRAME_BYTES];
  uint32_t bytes_read = 0;
  esp_err_t err = adc_continuous_read(
      adc_handle, dma_data, sizeof(dma_data), &bytes_read, 100);

  if (err == ESP_ERR_TIMEOUT) return;
  if (err != ESP_OK) {
    Serial.printf("# ADC_ERROR=%s\n", esp_err_to_name(err));
    return;
  }

  for (uint32_t i = 0; i + sizeof(adc_digi_output_data_t) <= bytes_read;
       i += sizeof(adc_digi_output_data_t)) {
    adc_digi_output_data_t sample = {};
    memcpy(&sample, dma_data + i, sizeof(sample));
    if (sample.type2.unit != ADC_UNIT_1 ||
        sample.type2.channel != ADC_CHANNEL_0) continue;

    const uint16_t raw = sample.type2.data;
    // ADC hardware clocks 20 samples per 1 kHz output sample.
    if ((raw_counter++ % DECIMATION) != 0) continue;

    const uint16_t med = medianFiltered(raw);
    Serial.printf("%lu,%u,%u\n",
                  static_cast<unsigned long>(output_counter++), raw, med);
  }
}
