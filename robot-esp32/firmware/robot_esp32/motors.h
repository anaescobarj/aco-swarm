// =====================================================================
//  motors.h – Módulo de locomoción (TB6612FNG, tracción diferencial 4WD)
//  Requiere arduino-esp32 core >= 3.0 (API ledcAttach / ledcWrite por pin)
// =====================================================================
#pragma once
#include "config.h"

namespace Motors {

static float lastL = 0, lastR = 0;

inline void begin() {
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  pinMode(PIN_STBY, OUTPUT);
  ledcAttach(PIN_PWMA, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  ledcAttach(PIN_PWMB, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  digitalWrite(PIN_STBY, HIGH);
}

// v en [-1, 1]; signo = sentido de giro
static void driveChannel(int pwmPin, int in1, int in2, float v, float trim) {
  v = constrain(v, -1.0f, 1.0f) * trim;
  const int maxDuty = (1 << MOTOR_PWM_BITS) - 1;
  int duty = (int)(fabsf(v) * MOTOR_MAX_DUTY * maxDuty);
  if (v > 0.01f)       { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
  else if (v < -0.01f) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); }
  else                 { digitalWrite(in1, LOW);  digitalWrite(in2, LOW); duty = 0; } // rueda libre
  ledcWrite(pwmPin, duty);
}

// Velocidades normalizadas de cada lado en [-1, 1]
inline void set(float left, float right) {
  lastL = constrain(left, -1.0f, 1.0f);
  lastR = constrain(right, -1.0f, 1.0f);
  driveChannel(PIN_PWMA, PIN_AIN1, PIN_AIN2, lastL, MOTOR_TRIM_L);
  driveChannel(PIN_PWMB, PIN_BIN1, PIN_BIN2, lastR, MOTOR_TRIM_R);
}

// Mezcla diferencial: avance v y giro w (w > 0 = derecha / horario)
inline void arcade(float v, float w) {
  float l = v + w, r = v - w;
  float m = max(fabsf(l), fabsf(r));
  if (m > 1.0f) { l /= m; r /= m; }
  set(l, r);
}

inline void stop()  { set(0, 0); }

// Freno activo (corto en el puente H)
inline void brake() {
  digitalWrite(PIN_AIN1, HIGH); digitalWrite(PIN_AIN2, HIGH);
  digitalWrite(PIN_BIN1, HIGH); digitalWrite(PIN_BIN2, HIGH);
  ledcWrite(PIN_PWMA, (1 << MOTOR_PWM_BITS) - 1);
  ledcWrite(PIN_PWMB, (1 << MOTOR_PWM_BITS) - 1);
  lastL = lastR = 0;
}

}  // namespace Motors
