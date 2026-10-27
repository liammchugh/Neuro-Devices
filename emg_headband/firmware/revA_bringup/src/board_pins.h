// Rev A pin map, read from emg_headband/hardware/emg_afe/kicad/emg_wearable_revA.kicad_pcb
// (U2 ESP32-S3-MINI-1 module pin -> net). Module pin N is GPIO(N-4) for pins 4..22.
#pragma once

constexpr int PIN_SPI_SCK   = 12;  // U2.16 SPI_SCK   -> U1.40 SCLK
constexpr int PIN_SPI_MISO  = 13;  // U2.17 SPI_MISO  -> U1.43 DOUT
constexpr int PIN_SPI_MOSI  = 14;  // U2.18 SPI_MOSI  -> U1.34 DIN
constexpr int PIN_ADS_CS    = 15;  // U2.19 ADS_CS    -> U1.39 CS     (R103 10k pull-up)
constexpr int PIN_ADS_DRDY  = 16;  // U2.20 ADS_DRDY  -> U1.47 DRDY
constexpr int PIN_ADS_START = 17;  // U2.21 ADS_START -> U1.38 START
constexpr int PIN_ADS_RESET = 18;  // U2.22 ADS_RESET -> U1.36 RESET  (R105 10k pull-up)
constexpr int PIN_VBAT_SENSE = 10; // U2.14 VBAT_SENSE, VBAT_SYS / 2 (R705/R706 1M/1M, C709)
// ADS1298 PWDN is held high by R106 (no GPIO). IO0 = TP10 (BOOT), EN = TP9.
// USB D-/D+ on IO19/IO20 (native USB).

constexpr float VBAT_DIVIDER = 2.0f;
