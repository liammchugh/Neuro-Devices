// Minimal ADS1298 driver for the Rev A board (internal clock, internal 2.4 V reference,
// AVDD 3.0 V single supply). Register and command values are from the ADS129x datasheet
// (SBAS459).
#pragma once
#include <Arduino.h>
#include <SPI.h>

namespace ads {

enum Cmd : uint8_t {
  WAKEUP = 0x02, STANDBY = 0x04, RESET = 0x06, START = 0x08, STOP = 0x0A,
  RDATAC = 0x10, SDATAC = 0x11, RDATA = 0x12, RREG = 0x20, WREG = 0x40,
};

enum Reg : uint8_t {
  ID = 0x00, CONFIG1, CONFIG2, CONFIG3, LOFF,
  CH1SET, CH2SET, CH3SET, CH4SET, CH5SET, CH6SET, CH7SET, CH8SET,
  RLD_SENSP, RLD_SENSN, LOFF_SENSP, LOFF_SENSN, LOFF_FLIP,
  LOFF_STATP, LOFF_STATN, GPIO, PACE, RESP, CONFIG4, WCT1, WCT2,
  NUM_REGS
};

// CHnSET.MUX
enum Mux : uint8_t {
  MUX_NORMAL = 0, MUX_SHORT = 1, MUX_RLD_MEAS = 2, MUX_MVDD = 3,
  MUX_TEMP = 4, MUX_TEST = 5, MUX_RLD_DRP = 6, MUX_RLD_DRN = 7,
};

constexpr uint8_t ID_ADS1298 = 0x92;
constexpr uint8_t ID_ADS1298R = 0xD2;
constexpr float VREF = 2.4f;
constexpr int MAX_CH = 3;  // channels wired on Rev A (IN1..IN3)

struct Config {
  int nch = 3;            // 1..3 active channels (CH1 first)
  int gain = 6;           // 1, 2, 3, 4, 6, 8, 12
  int rate = 4000;        // 500..32000 SPS, high-resolution mode
  Mux mux = MUX_NORMAL;   // applied to the active channels
  bool rld = true;        // drive RLD from the active channels
  bool leadoff = false;   // DC lead-off comparators (6 nA)
  bool testSignal = false;// internal 1 Hz, +/-1 mV square wave (CONFIG2)
};

struct Frame {
  uint32_t index;
  uint32_t status;        // 24-bit status word: 1100 | LOFF_STATP | LOFF_STATN | GPIO
  int32_t ch[MAX_CH];     // raw 24-bit two's complement, sign-extended
};

inline uint8_t loffP(uint32_t status) { return (status >> 12) & 0xFF; }
inline uint8_t loffN(uint32_t status) { return (status >> 4) & 0xFF; }
inline bool statusValid(uint32_t status) { return (status >> 20) == 0xC; }

bool gainBits(int gain, uint8_t &bits);
bool rateBits(int rate, uint8_t &bits);

class Device {
 public:
  void begin(SPIClass &spi, int cs, int drdy, int start, int reset);
  void powerOnReset();
  void command(uint8_t c);
  uint8_t readReg(uint8_t addr);
  void writeReg(uint8_t addr, uint8_t value);
  // Stops conversions, writes every register for cfg, leaves the device in SDATAC.
  bool configure(const Config &cfg);
  void startStreaming();   // RDATAC + START pin high
  void stopStreaming();    // START pin low + SDATAC
  // Reads status + CH1..CH3 in RDATAC mode. Call after DRDY falls.
  void readFrame(Frame &f);
  const Config &config() const { return cfg_; }
  float microvoltsPerLsb() const { return VREF / (cfg_.gain * 8388608.0f) * 1e6f; }

 private:
  void select();
  void deselect();
  SPIClass *spi_ = nullptr;
  SPISettings settings_{4000000, MSBFIRST, SPI_MODE1};
  int cs_, drdy_, start_, reset_;
  Config cfg_;
};

}  // namespace ads
