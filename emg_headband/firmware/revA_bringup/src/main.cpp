// Rev A EMG wearable bring-up firmware.
//
// ESP32-S3-MINI-1 + ADS1298, USB serial over the board's USB-C. Type `help` in a serial
// terminal (115200, any baud works on native USB). Line-based commands, newline-terminated.
//
// Acquisition: DRDY falling edge -> ISR -> acquisition task reads status + CH1..CH3 over SPI
// -> queue -> loop() filters and prints. Nothing is transmitted wirelessly yet.

#include <Arduino.h>
#include <SPI.h>
#include <math.h>

#include "ads1298.h"
#include "board_pins.h"
#include "filters.h"

static const char *FW_VERSION = "revA-bringup 0.1";

// ---------------------------------------------------------------- acquisition
static SPIClass adsSpi(FSPI);
static ads::Device adc;
static SemaphoreHandle_t spiMutex;
static QueueHandle_t frameQueue;
static TaskHandle_t acqTask;
static volatile bool streaming = false;
static volatile uint32_t drdyCount = 0, framesRead = 0, queueDrops = 0, badStatus = 0;

static void IRAM_ATTR onDrdy() {
  drdyCount++;
  BaseType_t woken = pdFALSE;
  vTaskNotifyGiveFromISR(acqTask, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static void acquisitionTask(void *) {
  ads::Frame f;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (!streaming) continue;
    bool got = false;
    xSemaphoreTake(spiMutex, portMAX_DELAY);
    if (streaming) {  // re-check: a config change may have stopped conversions meanwhile
      adc.readFrame(f);
      f.index = framesRead++;
      got = true;
    }
    xSemaphoreGive(spiMutex);
    if (!got) continue;
    if (!ads::statusValid(f.status)) badStatus++;
    if (xQueueSend(frameQueue, &f, 0) != pdTRUE) queueDrops++;
  }
}

static ads::Config cfg;
static float mains = 60.0f;
static ChannelChain chains[ads::MAX_CH];

static void designFilters() {
  for (auto &c : chains) c.design(cfg.rate, mains);
}

static bool applyConfig(const ads::Config &c) {
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  streaming = false;
  bool ok = adc.configure(c);
  xSemaphoreGive(spiMutex);
  if (!ok) return false;
  cfg = c;
  designFilters();
  return true;
}

static void startStream() {
  xQueueReset(frameQueue);
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  adc.startStreaming();
  streaming = true;
  xSemaphoreGive(spiMutex);
}

static void stopStream() {
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  streaming = false;
  adc.stopStreaming();
  xSemaphoreGive(spiMutex);
  xQueueReset(frameQueue);
}

static uint8_t readRegSafe(uint8_t addr) {
  // Registers can only be read in SDATAC mode.
  const bool was = streaming;
  if (was) stopStream();
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  uint8_t v = adc.readReg(addr);
  xSemaphoreGive(spiMutex);
  if (was) startStream();
  return v;
}

static bool nextFrame(ads::Frame &f, uint32_t timeoutMs = 100) {
  return xQueueReceive(frameQueue, &f, pdMS_TO_TICKS(timeoutMs)) == pdTRUE;
}

// ---------------------------------------------------------------- measurements
struct Stats {
  double sum[ads::MAX_CH] = {0}, sumSq[ads::MAX_CH] = {0};
  double band[ads::MAX_CH] = {0};  // sum of squares after the 20-450 Hz EMG chain
  float mn[ads::MAX_CH], mx[ads::MAX_CH];
  uint32_t n = 0;
  double mean(int c) const { return sum[c] / n; }
  double rms(int c) const { double m = mean(c); return sqrt(fmax(sumSq[c] / n - m * m, 0)); }
  double bandRms(int c) const { return sqrt(band[c] / n); }
  double pp(int c) const { return mx[c] - mn[c]; }
};

// Runs the ADC with config c, discards settleS seconds, then accumulates measureS seconds.
static bool measure(const ads::Config &c, float settleS, float measureS, Stats &st) {
  if (!applyConfig(c)) return false;
  for (int i = 0; i < ads::MAX_CH; i++) { st.mn[i] = 1e30f; st.mx[i] = -1e30f; }
  const uint32_t settle = uint32_t(settleS * c.rate), total = settle + uint32_t(measureS * c.rate);
  const float uvLsb = adc.microvoltsPerLsb();
  startStream();
  ads::Frame f;
  uint32_t got = 0;
  while (got < total) {
    if (!nextFrame(f, 500)) { stopStream(); return false; }
    for (int i = 0; i < c.nch; i++) {
      const float uv = f.ch[i] * uvLsb;
      chains[i].process(uv);
      if (got < settle) continue;
      st.sum[i] += uv; st.sumSq[i] += double(uv) * uv;
      st.band[i] += double(chains[i].emg) * chains[i].emg;
      st.mn[i] = fminf(st.mn[i], uv); st.mx[i] = fmaxf(st.mx[i], uv);
    }
    if (got >= settle) st.n++;
    got++;
  }
  stopStream();
  return true;
}

static float batteryVolts() {
  return analogReadMilliVolts(PIN_VBAT_SENSE) * VBAT_DIVIDER / 1000.0f;
}

// ---------------------------------------------------------------- output modes
enum class Mode { Idle, PlotWide, PlotEmg, PlotEnv, Binary };
static Mode mode = Mode::Idle;
static uint32_t decimCount = 0;
static constexpr int PLOT_HZ = 250;

static void emitBinary(const ads::Frame &f) {
  // 18 bytes: A5 5A | index u32 LE | loffP | loffN | CH1..CH3 int24 LE | xor of bytes 2..16
  uint8_t b[18];
  b[0] = 0xA5; b[1] = 0x5A;
  memcpy(&b[2], &f.index, 4);
  b[6] = ads::loffP(f.status);
  b[7] = ads::loffN(f.status);
  for (int i = 0; i < 3; i++) {
    const int32_t v = f.ch[i];
    b[8 + 3 * i] = v & 0xFF; b[9 + 3 * i] = (v >> 8) & 0xFF; b[10 + 3 * i] = (v >> 16) & 0xFF;
  }
  uint8_t x = 0;
  for (int i = 2; i < 17; i++) x ^= b[i];
  b[17] = x;
  Serial.write(b, sizeof(b));
}

static void handleFrame(const ads::Frame &f) {
  if (mode == Mode::Binary) { emitBinary(f); return; }
  const float uvLsb = adc.microvoltsPerLsb();
  for (int i = 0; i < cfg.nch; i++) chains[i].process(f.ch[i] * uvLsb);
  if (mode == Mode::Idle) return;
  if (++decimCount < uint32_t(cfg.rate / PLOT_HZ)) return;
  decimCount = 0;
  // Arduino Serial Plotter format: name:value pairs.
  char line[160];
  int n = 0;
  for (int i = 0; i < cfg.nch; i++) {
    const float v = mode == Mode::PlotWide ? chains[i].wide
                  : mode == Mode::PlotEmg  ? chains[i].emg : chains[i].env;
    n += snprintf(line + n, sizeof(line) - n, "ch%d_uV:%.2f ", i + 1, v);
  }
  if (cfg.leadoff) {
    n += snprintf(line + n, sizeof(line) - n, "loffP:%u loffN:%u",
                  ads::loffP(f.status), ads::loffN(f.status));
  }
  Serial.println(line);
}

// ---------------------------------------------------------------- commands
static void printConfig() {
  Serial.printf("config: nch=%d gain=%d rate=%d mains=%.0f rld=%s leadoff=%s uV/LSB=%.5f\n",
                cfg.nch, cfg.gain, cfg.rate, mains, cfg.rld ? "on" : "off",
                cfg.leadoff ? "on" : "off", adc.microvoltsPerLsb());
}

static void cmdInfo() {
  const bool was = streaming;
  if (was) stopStream();
  Serial.printf("firmware: %s, uptime %lu s\n", FW_VERSION, (unsigned long)(millis() / 1000));
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  uint8_t regs[ads::NUM_REGS];
  for (uint8_t a = 0; a < ads::NUM_REGS; a++) regs[a] = adc.readReg(a);
  xSemaphoreGive(spiMutex);
  Serial.printf("ADS1298 ID: 0x%02X (%s)\n", regs[0],
                regs[0] == ads::ID_ADS1298 ? "ADS1298 OK" :
                regs[0] == ads::ID_ADS1298R ? "ADS1298R" : "UNEXPECTED");
  Serial.print("regs:");
  for (uint8_t a = 0; a < ads::NUM_REGS; a++) Serial.printf(" %02X", regs[a]);
  Serial.println();
  printConfig();
  Serial.printf("battery (VBAT_SYS): %.2f V (0 V means SW1 off or no cell)\n", batteryVolts());
  Serial.printf("counters: drdy=%u frames=%u queue_drops=%u bad_status=%u\n",
                drdyCount, framesRead, queueDrops, badStatus);
  if (was) startStream();
}

static bool cmdSupply(bool verbose) {
  ads::Config c = cfg;
  c.nch = 3; c.gain = 1; c.mux = ads::MUX_MVDD; c.rld = false; c.leadoff = false;
  c.testSignal = false;
  Stats st;
  if (!measure(c, 0.2f, 0.5f, st)) { Serial.println("supply: no data (DRDY?)"); return false; }
  const double avdd = 2.0 * st.mean(0) / 1e6;  // CH1/CH2: (AVDD + AVSS) / 2
  const double dvdd = 4.0 * st.mean(2) / 1e6;  // CH3: DVDD / 4
  c.nch = 1; c.mux = ads::MUX_TEMP;
  Stats t;
  measure(c, 0.2f, 0.5f, t);
  const double tempC = (t.mean(0) - 145300.0) / 490.0 + 25.0;
  const bool okA = avdd > 2.90 && avdd < 3.10, okD = dvdd > 3.20 && dvdd < 3.40;
  const bool okT = tempC > 5 && tempC < 70;
  Serial.printf("supply: AVDD(+3V0_A)=%.3f V [%s, 2.90-3.10]  DVDD(+3V3)=%.3f V [%s, 3.20-3.40]"
                "  die temp=%.1f C [%s]\n", avdd, okA ? "PASS" : "FAIL", dvdd,
                okD ? "PASS" : "FAIL", tempC, okT ? "PASS" : "CHECK");
  (void)verbose;
  applyConfig(cfg);
  return okA && okD;
}

static bool cmdTestSignal() {
  ads::Config c = cfg;
  c.nch = 3; c.mux = ads::MUX_TEST; c.testSignal = true; c.rld = false; c.leadoff = false;
  Stats st;
  // ~1 Hz square wave: measure 3 s so several edges are seen.
  if (!measure(c, 0.3f, 3.0f, st)) { Serial.println("testsig: no data"); return false; }
  bool ok = true;
  for (int i = 0; i < 3; i++) {
    const double ppmV = st.pp(i) / 1000.0;
    const bool pass = ppmV > 1.8 && ppmV < 2.3;
    ok &= pass;
    Serial.printf("testsig CH%d: %.3f mVpp [%s, expect ~2.0 mVpp]\n", i + 1, ppmV,
                  pass ? "PASS" : "FAIL");
  }
  applyConfig(cfg);
  return ok;
}

// external=false: inputs shorted inside the ADS1298 (MUX=001), tests the ADC alone.
// external=true: normal inputs; short TRS tip+ring+sleeve (or the flex pads) yourself.
static bool cmdNoise(bool external) {
  ads::Config c = cfg;
  c.nch = 3; c.mux = external ? ads::MUX_NORMAL : ads::MUX_SHORT; c.testSignal = false;
  c.leadoff = false;
  Stats st;
  if (!measure(c, 1.0f, 5.0f, st)) { Serial.println("noise: no data"); return false; }
  bool ok = true;
  Serial.printf("noise (%s, gain %d, %d SPS, 5 s):\n",
                external ? "external short, normal inputs" : "internal short", c.gain, c.rate);
  for (int i = 0; i < 3; i++) {
    const double band = st.bandRms(i), wide = st.rms(i);
    // Guide limits, not datasheet limits: the ADS1298 should be well under these when healthy.
    const bool pass = band < (external ? 4.0 : 2.0) && wide < (external ? 10.0 : 5.0);
    ok &= pass;
    Serial.printf("  CH%d: offset %+.1f uV  broadband %.2f uVrms (%.1f uVpp)  "
                  "20-450 Hz %.2f uVrms [%s]\n", i + 1, st.mean(i), wide, st.pp(i), band,
                  pass ? "PASS" : "HIGH");
  }
  applyConfig(cfg);
  return ok;
}

static bool cmdRate() {
  const bool was = streaming;
  if (!was) startStream();
  const uint32_t d0 = drdyCount;
  ads::Frame f;
  const uint32_t t0 = millis();
  while (millis() - t0 < 1000) nextFrame(f, 10);  // keep the queue drained
  const uint32_t d = drdyCount - d0;
  if (!was) stopStream();
  const bool ok = fabs(double(d) - cfg.rate) < cfg.rate * 0.02;
  Serial.printf("DRDY rate: %u Hz [%s, expect %d]\n", d, ok ? "PASS" : "FAIL", cfg.rate);
  return ok;
}

static void cmdSelfTest() {
  const Mode saved = mode;
  mode = Mode::Idle;
  Serial.println("=== self-test (no electrodes needed) ===");
  stopStream();
  const uint8_t id = readRegSafe(ads::ID);
  const bool idOk = id == ads::ID_ADS1298 || id == ads::ID_ADS1298R;
  Serial.printf("ID: 0x%02X [%s, expect 0x92]\n", id, idOk ? "PASS" : "FAIL");
  if (!idOk) {
    Serial.println("SPI/power problem: 0x00 or 0xFF means no answer. Check +3V0_A, +3V3, U1"
                   " orientation and solder, then `info`.");
    mode = saved;
    return;
  }
  xSemaphoreTake(spiMutex, portMAX_DELAY);
  adc.writeReg(ads::CONFIG1, 0x85);
  const uint8_t rb = adc.readReg(ads::CONFIG1);
  xSemaphoreGive(spiMutex);
  Serial.printf("register write/readback: 0x%02X [%s]\n", rb, rb == 0x85 ? "PASS" : "FAIL");
  applyConfig(cfg);
  bool ok = idOk && rb == 0x85;
  ok &= cmdRate();
  ok &= cmdSupply(false);
  ok &= cmdTestSignal();
  ok &= cmdNoise(false);
  Serial.printf("battery (VBAT_SYS): %.2f V\n", batteryVolts());
  Serial.printf("=== self-test %s ===\n", ok ? "PASSED" : "had failures, see above");
  mode = saved;
  if (mode != Mode::Idle) startStream();
}

static void printHelp() {
  Serial.println(
      "commands:\n"
      "  help                 this list\n"
      "  info                 ADS1298 ID, registers, config, battery, counters\n"
      "  selftest             ID, SPI, DRDY rate, AVDD/DVDD/temp, test signal, noise\n"
      "  supply               AVDD, DVDD and die temperature via the ADS1298\n"
      "  testsig              internal 1 Hz 2 mVpp test signal on CH1-3\n"
      "  noise                input-short noise (inside the ADS1298)\n"
      "  noise ext            noise with real inputs; short the electrode leads yourself\n"
      "  bat                  battery voltage\n"
      "  plot wide|emg|env    stream filtered uV at 250 Hz (Arduino Serial Plotter format)\n"
      "  bin                  raw binary stream (use tools/revA_host.py)\n"
      "  stop                 stop streaming\n"
      "  ch 1|2|3             number of active channels\n"
      "  gain 1|2|3|4|6|8|12  PGA gain (6 default; +/-400 mV range)\n"
      "  rate 500..32000      sample rate (4000 default)\n"
      "  mains 50|60          notch frequency\n"
      "  rld on|off           right-leg drive from the active channels\n"
      "  leadoff on|off       DC lead-off detection (flags in plot/bin output)\n"
      "  rreg <hex>           read a register;  wreg <hex> <hex>  write one");
}

static void startMode(Mode m) {
  mode = m;
  decimCount = 0;
  for (int i = 0; i < ads::MAX_CH; i++) chains[i].design(cfg.rate, mains);
  if (m == Mode::Binary) {
    Serial.printf("#BIN fs=%d gain=%d nch=%d uv_per_lsb=%.7f frame=18\n", cfg.rate, cfg.gain,
                  cfg.nch, adc.microvoltsPerLsb());
    Serial.flush();
  }
  if (!streaming) startStream();
}

static void handleCommand(char *line) {
  char *cmd = strtok(line, " \t");
  if (!cmd) return;
  char *a1 = strtok(nullptr, " \t");
  char *a2 = strtok(nullptr, " \t");
  const bool wasStreaming = streaming;
  ads::Config c = cfg;
  bool reconfig = false;

  if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) printHelp();
  else if (!strcmp(cmd, "info")) cmdInfo();
  else if (!strcmp(cmd, "selftest") || !strcmp(cmd, "test")) cmdSelfTest();
  else if (!strcmp(cmd, "supply")) { stopStream(); cmdSupply(true); }
  else if (!strcmp(cmd, "testsig")) { stopStream(); cmdTestSignal(); }
  else if (!strcmp(cmd, "noise")) { stopStream(); cmdNoise(a1 && !strcmp(a1, "ext")); }
  else if (!strcmp(cmd, "bat")) Serial.printf("battery (VBAT_SYS): %.2f V\n", batteryVolts());
  else if (!strcmp(cmd, "stop")) { mode = Mode::Idle; stopStream(); Serial.println("stopped"); return; }
  else if (!strcmp(cmd, "bin")) { startMode(Mode::Binary); return; }
  else if (!strcmp(cmd, "plot")) {
    Mode m = Mode::PlotWide;
    if (a1 && !strcmp(a1, "emg")) m = Mode::PlotEmg;
    else if (a1 && !strcmp(a1, "env")) m = Mode::PlotEnv;
    startMode(m);
    return;
  }
  else if (!strcmp(cmd, "ch") && a1) { c.nch = atoi(a1); reconfig = true; }
  else if (!strcmp(cmd, "gain") && a1) { c.gain = atoi(a1); reconfig = true; }
  else if (!strcmp(cmd, "rate") && a1) { c.rate = atoi(a1); reconfig = true; }
  else if (!strcmp(cmd, "rld") && a1) { c.rld = !strcmp(a1, "on"); reconfig = true; }
  else if (!strcmp(cmd, "leadoff") && a1) { c.leadoff = !strcmp(a1, "on"); reconfig = true; }
  else if (!strcmp(cmd, "mains") && a1) {
    const int m = atoi(a1);
    if (m == 50 || m == 60) { mains = m; designFilters(); printConfig(); }
    else Serial.println("mains must be 50 or 60");
  }
  else if (!strcmp(cmd, "rreg") && a1) {
    const uint8_t a = strtoul(a1, nullptr, 16);
    Serial.printf("reg 0x%02X = 0x%02X\n", a, readRegSafe(a));
  }
  else if (!strcmp(cmd, "wreg") && a1 && a2) {
    stopStream();
    xSemaphoreTake(spiMutex, portMAX_DELAY);
    adc.writeReg(strtoul(a1, nullptr, 16), strtoul(a2, nullptr, 16));
    xSemaphoreGive(spiMutex);
    Serial.println("written (cleared by the next config change)");
  }
  else Serial.printf("unknown command '%s', try help\n", cmd);

  if (reconfig) {
    if (applyConfig(c)) printConfig();
    else Serial.println("invalid value; see help");
  }
  if (wasStreaming && !streaming && mode != Mode::Idle) startStream();
}

// ---------------------------------------------------------------- setup/loop
void setup() {
  Serial.setTxBufferSize(8192);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // never block acquisition when no host is reading

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_VBAT_SENSE, ADC_11db);

  spiMutex = xSemaphoreCreateMutex();
  frameQueue = xQueueCreate(1024, sizeof(ads::Frame));
  adsSpi.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI, -1);
  adc.begin(adsSpi, PIN_ADS_CS, PIN_ADS_DRDY, PIN_ADS_START, PIN_ADS_RESET);
  xTaskCreatePinnedToCore(acquisitionTask, "acq", 4096, nullptr, configMAX_PRIORITIES - 2,
                          &acqTask, 1);
  attachInterrupt(PIN_ADS_DRDY, onDrdy, FALLING);

  adc.powerOnReset();
  applyConfig(cfg);

  const uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  Serial.printf("\n%s. ADS1298 ID 0x%02X. Type `help`, or `selftest` to start.\n", FW_VERSION,
                readRegSafe(ads::ID));
  printConfig();
}

void loop() {
  static char line[96];
  static size_t len = 0;
  while (Serial.available()) {
    const char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (len) { line[len] = 0; handleCommand(line); len = 0; }
    } else if (len < sizeof(line) - 1) {
      line[len++] = ch;
    }
  }
  ads::Frame f;
  // Drain everything queued; never wait here so commands stay responsive.
  while (xQueueReceive(frameQueue, &f, 0) == pdTRUE) handleFrame(f);
  if (mode == Mode::Idle) delay(1);
}
