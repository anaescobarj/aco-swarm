// =====================================================================
//  color_sensor.h – Sensor de color TCS34725 (I2C, filtro IR, LED propio)
//  Clasifica la superficie en 6 colores: negro, blanco, rojo, amarillo,
//  verde y azul, usando cromaticidad normalizada + brillo (vecino más
//  cercano). Las referencias se pueden recalibrar en pista y se guardan
//  en memoria no volátil.
// =====================================================================
#pragma once
#include <Wire.h>
#include <Preferences.h>
#include "config.h"

namespace ColorSensor {

static const uint8_t ADDR = 0x29;
static const uint8_t CMD  = 0x80;
static const int N_COLORS = 6;
static const char* NAMES[N_COLORS] = {"negro", "blanco", "rojo", "amarillo", "verde", "azul"};

struct Ref { float r, g, b, lc; };   // cromaticidad (r,g,b suman 1) y log10(clear)
// Referencias por defecto (se ajustan con /api/calibrate?what=color&name=...)
static Ref refs[N_COLORS] = {
  {0.36f, 0.35f, 0.29f, 2.10f},   // negro
  {0.32f, 0.36f, 0.32f, 3.50f},   // blanco
  {0.58f, 0.22f, 0.20f, 2.90f},   // rojo
  {0.44f, 0.40f, 0.16f, 3.20f},   // amarillo
  {0.27f, 0.46f, 0.27f, 2.80f},   // verde
  {0.20f, 0.32f, 0.48f, 2.80f},   // azul
};

static bool ok = false;
static uint16_t C = 0, R = 0, G = 0, B = 0;
static int current = -1, candidate = -1, candidateCount = 0;
static uint32_t changes = 0;
static uint32_t lastRead = 0;

// lee LSB y luego MSB (orden garantizado, a diferencia de 'read() | read() << 8')
static inline int16_t read16() { uint8_t lo = Wire.read(); uint8_t hi = Wire.read(); return (int16_t)(lo | (hi << 8)); }

static void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ADDR); Wire.write(CMD | reg); Wire.write(val); Wire.endTransmission();
}

inline void loadCalibration() {
  Preferences p; p.begin("color", true);
  for (int i = 0; i < N_COLORS; i++) {
    if (p.isKey(NAMES[i])) p.getBytes(NAMES[i], &refs[i], sizeof(Ref));
  }
  p.end();
}

inline bool begin() {
  pinMode(PIN_COLOR_LED, OUTPUT);
  digitalWrite(PIN_COLOR_LED, HIGH);         // iluminación constante = lecturas estables
  Wire.beginTransmission(ADDR); Wire.write(CMD | 0x12);
  if (Wire.endTransmission(false) != 0) return ok = false;
  Wire.requestFrom(ADDR, (uint8_t)1);
  uint8_t id = Wire.read();
  ok = (id == 0x44 || id == 0x4D || id == 0x10);
  if (!ok) return false;
  writeReg(0x01, 0xEB);   // ATIME: (256-0xEB)*2.4 ms = 50.4 ms
  writeReg(0x0F, 0x01);   // ganancia 4x
  writeReg(0x00, 0x01);   // PON
  delay(3);
  writeReg(0x00, 0x03);   // PON + AEN
  loadCalibration();
  return true;
}

inline int classify(float r, float g, float b, float lc) {
  int best = 0; float bestD = 1e9f;
  for (int i = 0; i < N_COLORS; i++) {
    float dr = r - refs[i].r, dg = g - refs[i].g, db = b - refs[i].b;
    float dl = (lc - refs[i].lc) * 0.25f;    // el brillo pesa menos que el tono
    float d = dr * dr + dg * dg + db * db + dl * dl;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

// Devuelve true cuando se confirma un cambio de sección de color
inline bool update() {
  if (!ok || millis() - lastRead < 52) return false;   // respeta el tiempo de integración
  lastRead = millis();
  Wire.beginTransmission(ADDR); Wire.write(CMD | 0x20 | 0x14);  // auto-incremento desde CDATAL
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ADDR, (uint8_t)8) != 8) return false;
  C = (uint16_t)read16();
  R = (uint16_t)read16();
  G = (uint16_t)read16();
  B = (uint16_t)read16();
  float s = (float)R + G + B;
  if (s < 1) return false;
  int c = classify(R / s, G / s, B / s, log10f(C + 1.0f));
  // anti-rebote: 3 lecturas consecutivas iguales (~150 ms) para aceptar el cambio
  if (c == candidate) candidateCount++; else { candidate = c; candidateCount = 1; }
  if (candidateCount >= 3 && c != current) {
    bool firstRead = (current < 0);
    current = c;
    if (!firstRead) { changes++; return true; }
  }
  return false;
}

inline const char* name() { return current >= 0 ? NAMES[current] : "desconocido"; }

// Toma la lectura actual como referencia del color indicado
inline bool calibrate(const String& colorName) {
  for (int i = 0; i < N_COLORS; i++) {
    if (colorName == NAMES[i]) {
      float s = (float)R + G + B; if (s < 1) return false;
      refs[i] = {R / s, G / s, B / s, log10f(C + 1.0f)};
      Preferences p; p.begin("color", false);
      p.putBytes(NAMES[i], &refs[i], sizeof(Ref));
      p.end();
      return true;
    }
  }
  return false;
}

}  // namespace ColorSensor
