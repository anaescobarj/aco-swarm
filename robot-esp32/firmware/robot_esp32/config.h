// =====================================================================
//  config.h  –  Configuración central del robot móvil ESP32
//  Proyecto Final – Robot autónomo con brújula, colores y obstáculos
// =====================================================================
#pragma once
#include <Arduino.h>

// ---------------- Red (Wi-Fi SoftAP + ESP-NOW) -----------------------
#define WIFI_AP_SSID      "ROBOT-ESP32"
#define WIFI_AP_PASS      "robot1234"      // mínimo 8 caracteres
#define WIFI_CHANNEL      1                // ESP-NOW y SoftAP comparten canal
#define HTTP_PORT         80
#define ESPNOW_MAGIC      0x52A7           // identifica paquetes del control propio

// ---------------- Puente H TB6612FNG ---------------------------------
#define PIN_PWMA   25   // canal A = lado izquierdo (2 motores en paralelo)
#define PIN_AIN1   26
#define PIN_AIN2   27
#define PIN_PWMB   14   // canal B = lado derecho
#define PIN_BIN1   33
#define PIN_BIN2   32
#define PIN_STBY   13
#define MOTOR_PWM_FREQ   20000   // 20 kHz: fuera del rango audible
#define MOTOR_PWM_BITS   10      // 0..1023
#define MOTOR_MAX_DUTY   0.80f   // batería 2S (7.4 V) sobre motores de 6 V
#define MOTOR_TRIM_L     1.00f   // compensación mecánica izquierda/derecha
#define MOTOR_TRIM_R     1.00f

// ---------------- Bus I2C: brújula QMC5883L + color TCS34725 ----------
#define PIN_SDA    21
#define PIN_SCL    22
#define I2C_FREQ   400000
#define PIN_COLOR_LED 4         // LED blanco del módulo TCS34725
#define MAG_DECLINATION_DEG  (-7.8f)  // declinación magnética aprox. Colombia (Antioquia) 2026

// ---------------- Ultrasonido HC-SR04 sobre servo SG90 ----------------
#define PIN_TRIG   18
#define PIN_ECHO   19           // con divisor 1k/2k (5 V -> 3.3 V)
#define PIN_SERVO  23
#define SERVO_CENTER   90
#define SERVO_LEFT     160
#define SERVO_RIGHT    20
#define OBSTACLE_CM        30.0f   // umbral de detección en modo autónomo
#define SAFETY_STOP_CM     12.0f   // bloqueo de avance en modo manual

// ---------------- Sensores de línea TCRT5000 (x3) ---------------------
#define PIN_IR_L   34           // pines solo-entrada (ADC1)
#define PIN_IR_C   35
#define PIN_IR_R   39
#define IR_ACTIVE_LEVEL  HIGH   // módulos con comparador: HIGH = superficie oscura

// ---------------- Monitoreo y estado ---------------------------------
#define PIN_VBAT   36           // divisor 100k / 33k
#define VBAT_RATIO ((100.0f + 33.0f) / 33.0f)
#define PIN_LED    2

// ---------------- Control ---------------------------------------------
#define LOOP_PERIOD_MS      50     // lazo de control a 20 Hz
#define MANUAL_TIMEOUT_MS   600    // si no llegan comandos, el robot se detiene
#define AUTO_BASE_SPEED     0.55f
#define TURN_SPEED          0.50f
#define KP_HEADING          0.012f // (fracción de PWM) / grado
#define HEADING_TOL_DEG     8.0f
#define RODEO_W             0.13f  // curvatura del arco de evasión
