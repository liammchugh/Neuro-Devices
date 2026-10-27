#include "ads1298.h"

namespace ads {

// One tCLK at the 2.048 MHz internal clock is 0.49 us; the datasheet asks for 4 tCLK
// between bytes of a multi-byte command and after the last byte before CS rises.
static inline void tDecode() { delayMicroseconds(3); }

static constexpr uint8_t CONFIG3_BASE = 0x80 /*PD_REFBUF*/ | 0x40 /*reserved, 1*/ |
                                        0x08 /*RLDREF_INT*/ | 0x04 /*PD_RLD*/;

bool gainBits(int gain, uint8_t &bits) {
  switch (gain) {
    case 6: bits = 0; return true;
    case 1: bits = 1; return true;
    case 2: bits = 2; return true;
    case 3: bits = 3; return true;
    case 4: bits = 4; return true;
    case 8: bits = 5; return true;
    case 12: bits = 6; return true;
  }
  return false;
}

bool rateBits(int rate, uint8_t &bits) {
  // High-resolution mode data rates.
  static const int rates[] = {32000, 16000, 8000, 4000, 2000, 1000, 500};
  for (uint8_t i = 0; i < 7; i++) {
    if (rates[i] == rate) { bits = i; return true; }
  }
  return false;
}

void Device::begin(SPIClass &spi, int cs, int drdy, int start, int reset) {
  spi_ = &spi;
  cs_ = cs; drdy_ = drdy; start_ = start; reset_ = reset;
  pinMode(cs_, OUTPUT);
  digitalWrite(cs_, HIGH);
  pinMode(start_, OUTPUT);
  digitalWrite(start_, LOW);
  pinMode(reset_, OUTPUT);
  digitalWrite(reset_, HIGH);
  pinMode(drdy_, INPUT_PULLUP);
}

void Device::select() {
  spi_->beginTransaction(settings_);
  digitalWrite(cs_, LOW);
}

void Device::deselect() {
  tDecode();
  digitalWrite(cs_, HIGH);
  spi_->endTransaction();
}

void Device::powerOnReset() {
  // tPOR is 2^18 tCLK (128 ms) after the supplies settle.
  delay(150);
  digitalWrite(reset_, LOW);
  delayMicroseconds(10);
  digitalWrite(reset_, HIGH);
  delayMicroseconds(50);   // 18 tCLK
  command(SDATAC);         // the device wakes up in RDATAC
  writeReg(CONFIG3, CONFIG3_BASE);
  delay(150);              // internal reference settling
}

void Device::command(uint8_t c) {
  select();
  spi_->transfer(c);
  deselect();
}

uint8_t Device::readReg(uint8_t addr) {
  select();
  spi_->transfer(RREG | addr);
  tDecode();
  spi_->transfer(0x00);
  tDecode();
  uint8_t v = spi_->transfer(0x00);
  deselect();
  return v;
}

void Device::writeReg(uint8_t addr, uint8_t value) {
  select();
  spi_->transfer(WREG | addr);
  tDecode();
  spi_->transfer(0x00);
  tDecode();
  spi_->transfer(value);
  deselect();
}

bool Device::configure(const Config &cfg) {
  uint8_t g, dr;
  if (cfg.nch < 1 || cfg.nch > MAX_CH || !gainBits(cfg.gain, g) || !rateBits(cfg.rate, dr)) {
    return false;
  }
  stopStreaming();
  cfg_ = cfg;

  const uint8_t mask = (1u << cfg.nch) - 1;
  writeReg(CONFIG1, 0x80 | dr);                       // HR mode, daisy-chain, no CLK out
  writeReg(CONFIG2, cfg.testSignal ? 0x10 : 0x00);    // internal test: 1x amp, fCLK/2^21
  writeReg(CONFIG3, CONFIG3_BASE | (cfg.leadoff ? 0x02 : 0x00));
  writeReg(LOFF, 0x00);                               // 95 % threshold, 6 nA DC current
  for (int i = 0; i < 8; i++) {
    const bool on = i < cfg.nch;
    writeReg(CH1SET + i, on ? uint8_t((g << 4) | cfg.mux) : uint8_t(0x80 | MUX_SHORT));
  }
  // Only drive RLD from channels that see the body.
  const uint8_t rldMask = (cfg.rld && cfg.mux == MUX_NORMAL) ? mask : 0;
  writeReg(RLD_SENSP, rldMask);
  writeReg(RLD_SENSN, rldMask);
  writeReg(LOFF_SENSP, cfg.leadoff ? mask : 0);
  writeReg(LOFF_SENSN, cfg.leadoff ? mask : 0);
  writeReg(LOFF_FLIP, 0x00);
  writeReg(GPIO, 0x00);                               // GPIO1-4 unconnected: outputs, low
  writeReg(PACE, 0x00);
  writeReg(RESP, 0x20);                               // bit 5 must be written as 1
  writeReg(CONFIG4, cfg.leadoff ? 0x02 : 0x00);       // continuous, LOFF comparators
  writeReg(WCT1, 0x00);
  writeReg(WCT2, 0x00);
  return true;
}

void Device::startStreaming() {
  command(RDATAC);
  digitalWrite(start_, HIGH);
}

void Device::stopStreaming() {
  digitalWrite(start_, LOW);
  delayMicroseconds(10);
  command(SDATAC);
}

void Device::readFrame(Frame &f) {
  uint8_t tx[3 + 3 * MAX_CH] = {0};  // DIN held low while reading in RDATAC
  uint8_t rx[sizeof(tx)];
  select();
  spi_->transferBytes(tx, rx, sizeof(tx));
  digitalWrite(cs_, HIGH);
  spi_->endTransaction();
  f.status = (uint32_t(rx[0]) << 16) | (uint32_t(rx[1]) << 8) | rx[2];
  for (int i = 0; i < MAX_CH; i++) {
    const uint8_t *p = &rx[3 + 3 * i];
    f.ch[i] = int32_t((uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8)) >> 8;
  }
}

}  // namespace ads
