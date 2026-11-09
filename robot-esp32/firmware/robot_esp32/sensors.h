// =====================================================================
//  sensors.h – Ultrasonido HC-SR04 + servo SG90, sensores de línea
//  TCRT5000 y medición de batería.
// =====================================================================
#pragma once
#include "config.h"

namespace Sonar {

static float distCm = 400;
static float hist[3] = {400, 400, 400};
static uint8_t idx = 0;
static int servoAngle = SERVO_CENTER;

inline void servoWrite(int deg) {
  servoAngle = constrain(deg, 0, 180);
  // 50 Hz, 14 bits -> 20 ms = 16383 cuentas; pulso 500..2400 us
  uint32_t us = map(servoAngle, 0, 180, 500, 2400);
  ledcWrite(PIN_SERVO, (us * 16383UL) / 20000UL);
}

inline void begin() {
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);
  ledcAttach(PIN_SERVO, 50, 14);
  servoWrite(SERVO_CENTER);
}

// Una medición (bloquea máx. ~12 ms) -> 0..200 cm (400 = sin eco)
inline float measureOnce() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long t = pulseIn(PIN_ECHO, HIGH, 12000UL);
  if (t == 0) return 400;
  return t * 0.0343f / 2.0f;
}

// Filtro de mediana de 3 muestras para rechazar ecos espurios
inline float update() {
  hist[idx] = measureOnce(); idx = (idx + 1) % 3;
  float a = hist[0], b = hist[1], c = hist[2];
  distCm = max(min(a, b), min(max(a, b), c));
  return distCm;
}

}  // namespace Sonar

namespace LineSensors {
static bool l = false, c = false, r = false;
static uint32_t lastSeen = 0;
inline void begin() { pinMode(PIN_IR_L, INPUT); pinMode(PIN_IR_C, INPUT); pinMode(PIN_IR_R, INPUT); }
// invert = true en secciones negras (línea guía blanca sobre fondo negro)
inline void update(bool invert = false) {
  int act = invert ? !IR_ACTIVE_LEVEL : IR_ACTIVE_LEVEL;
  l = digitalRead(PIN_IR_L) == act;
  c = digitalRead(PIN_IR_C) == act;
  r = digitalRead(PIN_IR_R) == act;
  if (l || c || r) lastSeen = millis();
}
inline bool any() { return l || c || r; }
// error de posición: -1 (línea a la izquierda) .. +1 (línea a la derecha)
inline float error() {
  int n = l + c + r; if (n == 0) return 0;
  return ((r ? 1.0f : 0) - (l ? 1.0f : 0)) / n;
}
}  // namespace LineSensors

namespace Battery {
static float volts = 0;
inline void update() {
  float v = analogReadMilliVolts(PIN_VBAT) / 1000.0f * VBAT_RATIO;
  volts = (volts == 0) ? v : 0.9f * volts + 0.1f * v;
}
}  // namespace Battery

// Termistor NTC 10k B3950 pegado al portapilas 2S: protege las celdas 18650
// (y el TB6612, que está al lado) contra sobrecalentamiento.
namespace Thermistor {
static float tempC = 25.0f;
static bool ok = false;
inline void begin() { analogSetPinAttenuation(PIN_NTC, ADC_11db); }
inline void update() {
  uint32_t mv = 0;
  for (int i = 0; i < 4; i++) mv += analogReadMilliVolts(PIN_NTC);   // promedio de 4
  float v = mv / 4.0f;
  // circuito abierto (v ~ Vcc) o corto (v ~ 0) => sensor desconectado
  ok = (v > 50.0f && v < NTC_VCC_MV - 50.0f);
  if (!ok) return;
  float r = NTC_R_FIXED * v / (NTC_VCC_MV - v);                       // NTC en el lado bajo
  float invT = 1.0f / 298.15f + logf(r / NTC_R25) / NTC_BETA;         // ecuación Beta
  float t = 1.0f / invT - 273.15f;
  tempC = 0.8f * tempC + 0.2f * t;                                    // filtro paso-bajo
}
}  // namespace Thermistor
