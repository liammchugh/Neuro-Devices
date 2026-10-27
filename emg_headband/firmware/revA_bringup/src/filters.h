// Biquad filters (RBJ audio-EQ cookbook), transposed direct form II.
#pragma once
#include <math.h>

template <typename T>
struct Biquad {
  T b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0, z1 = 0, z2 = 0;

  T process(T x) {
    T y = b0 * x + z1;
    z1 = b1 * x - a1 * y + z2;
    z2 = b2 * x - a2 * y;
    return y;
  }
  void reset() { z1 = z2 = 0; }

  void lowpass(double fs, double f0, double q) {
    double w = 2 * M_PI * f0 / fs, c = cos(w), al = sin(w) / (2 * q);
    set((1 - c) / 2, 1 - c, (1 - c) / 2, 1 + al, -2 * c, 1 - al);
  }
  void highpass(double fs, double f0, double q) {
    double w = 2 * M_PI * f0 / fs, c = cos(w), al = sin(w) / (2 * q);
    set((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + al, -2 * c, 1 - al);
  }
  void notch(double fs, double f0, double q) {
    double w = 2 * M_PI * f0 / fs, c = cos(w), al = sin(w) / (2 * q);
    set(1, -2 * c, 1, 1 + al, -2 * c, 1 - al);
  }

 private:
  void set(double nb0, double nb1, double nb2, double na0, double na1, double na2) {
    b0 = T(nb0 / na0); b1 = T(nb1 / na0); b2 = T(nb2 / na0);
    a1 = T(na1 / na0); a2 = T(na2 / na0);
    reset();
  }
};

// Butterworth 4th order = two biquads with these Qs.
constexpr double BW4_Q1 = 0.5411961, BW4_Q2 = 1.3065630;
constexpr double BW2_Q = 0.7071068;

// Per-channel processing chain. All values in microvolts.
//   wide: 0.5 Hz HPF (double, DC offsets are ~1e5 uV) -> mains notch -> 4th-order 100 Hz LPF
//         (anti-alias for the 250 Hz plot stream). Keeps blinks/EOG and slow activity.
//   emg:  wide pre-stage -> 20 Hz HPF (4th) -> 450 Hz LPF (2nd) -> notches at 2x, 3x mains.
//   env:  |emg| -> 5 Hz LPF (2nd), a muscle-activation envelope.
struct ChannelChain {
  Biquad<double> hp05;
  Biquad<float> notch1, lpWide1, lpWide2, hp20a, hp20b, lp450, notch2, notch3, envLp;
  float wide = 0, emg = 0, env = 0;

  void design(double fs, double mains) {
    hp05.highpass(fs, 0.5, BW2_Q);
    notch1.notch(fs, mains, 30);
    lpWide1.lowpass(fs, 100, BW4_Q1);
    lpWide2.lowpass(fs, 100, BW4_Q2);
    hp20a.highpass(fs, 20, BW4_Q1);
    hp20b.highpass(fs, 20, BW4_Q2);
    lp450.lowpass(fs, fs > 1000 ? 450 : fs * 0.45, BW2_Q);
    notch2.notch(fs, 2 * mains, 30);
    notch3.notch(fs, 3 * mains < fs / 2 ? 3 * mains : 2 * mains, 30);
    envLp.lowpass(fs, 5, BW2_Q);
  }

  void process(double uv) {
    float x = float(hp05.process(uv));
    x = notch1.process(x);
    wide = lpWide2.process(lpWide1.process(x));
    float e = hp20b.process(hp20a.process(x));
    e = notch3.process(notch2.process(lp450.process(e)));
    emg = e;
    env = envLp.process(fabsf(e));
  }
};
