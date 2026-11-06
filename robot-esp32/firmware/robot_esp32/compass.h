// =====================================================================
//  compass.h – Brújula digital QMC5883L (GY-271) por I2C
//  - Lectura continua a 50 Hz, rango ±8 G, sobremuestreo 512
//  - Calibración hard-iron (min/max) guardada en memoria no volátil
//  - Filtro circular (promedio de vectores) para suavizar el rumbo
// =====================================================================
#pragma once
#include <Wire.h>
#include <Preferences.h>
#include "config.h"

namespace Compass {

static const uint8_t ADDR = 0x0D;
static bool ok = false;
static float heading = 0;           // 0..360, 0 = Norte, sentido horario
static int16_t rawX = 0, rawY = 0, rawZ = 0;
static float offX = 0, offY = 0, scaleX = 1, scaleY = 1;
static float fx = 1, fy = 0;        // vector filtrado
static bool calibrating = false;
static int16_t minX, maxX, minY, maxY;

// lee LSB y luego MSB (orden garantizado, a diferencia de 'read() | read() << 8')
static inline int16_t read16() { uint8_t lo = Wire.read(); uint8_t hi = Wire.read(); return (int16_t)(lo | (hi << 8)); }

static void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ADDR); Wire.write(reg); Wire.write(val); Wire.endTransmission();
}

inline void loadCalibration() {
  Preferences p; p.begin("compass", true);
  offX = p.getFloat("ox", 0); offY = p.getFloat("oy", 0);
  scaleX = p.getFloat("sx", 1); scaleY = p.getFloat("sy", 1);
  p.end();
}

inline bool begin() {
  Wire.beginTransmission(ADDR);
  ok = (Wire.endTransmission() == 0);
  if (!ok) return false;
  writeReg(0x0B, 0x01);   // periodo SET/RESET recomendado
  writeReg(0x09, 0x1D);   // OSR=512, RNG=8G, ODR=50Hz, modo continuo
  loadCalibration();
  return true;
}

inline float wrap360(float a) { while (a < 0) a += 360; while (a >= 360) a -= 360; return a; }
inline float wrap180(float a) { while (a > 180) a -= 360; while (a < -180) a += 360; return a; }

inline void update() {
  if (!ok) return;
  Wire.beginTransmission(ADDR); Wire.write(0x00);
  if (Wire.endTransmission(false) != 0) return;
  if (Wire.requestFrom(ADDR, (uint8_t)6) != 6) return;
  rawX = read16();
  rawY = read16();
  rawZ = read16();

  if (calibrating) {
    minX = min(minX, rawX); maxX = max(maxX, rawX);
    minY = min(minY, rawY); maxY = max(maxY, rawY);
  }
  float x = (rawX - offX) * scaleX;
  float y = (rawY - offY) * scaleY;
  float n = sqrtf(x * x + y * y);
  if (n < 1e-3f) return;
  // filtro paso-bajo sobre el vector unitario (evita el salto 359°->0°)
  const float a = 0.3f;
  fx = (1 - a) * fx + a * (x / n);
  fy = (1 - a) * fy + a * (y / n);
  // El eje X del módulo apunta hacia el frente del robot
  float h = atan2f(fy, fx) * 180.0f / PI + MAG_DECLINATION_DEG;
  heading = wrap360(h);
}

inline void startCalibration() {
  calibrating = true;
  minX = minY = 32767; maxX = maxY = -32768;
}

inline void finishCalibration() {
  calibrating = false;
  if (maxX - minX < 50 || maxY - minY < 50) return;   // giro insuficiente
  offX = (maxX + minX) / 2.0f; offY = (maxY + minY) / 2.0f;
  float rx = (maxX - minX) / 2.0f, ry = (maxY - minY) / 2.0f, r = (rx + ry) / 2.0f;
  scaleX = r / rx; scaleY = r / ry;                     // corrección soft-iron simple
  Preferences p; p.begin("compass", false);
  p.putFloat("ox", offX); p.putFloat("oy", offY);
  p.putFloat("sx", scaleX); p.putFloat("sy", scaleY);
  p.end();
}

}  // namespace Compass
