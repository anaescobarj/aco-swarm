// =====================================================================
//  robot_esp32.ino – Firmware principal del robot móvil
//
//  Módulos: locomoción (TB6612FNG), brújula (QMC5883L), color (TCS34725),
//  obstáculos (HC-SR04 + servo), línea (3x TCRT5000), batería.
//  Comunicación: Wi-Fi SoftAP + API HTTP/JSON (app Streamlit, chatbot)
//                ESP-NOW (control remoto propio basado en ESP32).
//
//  Modos:
//   MANUAL  – comandos desde la app (botones o voz) o desde el control ESP-NOW.
//   AUTO    – sigue la pista (línea) o un rumbo polar deseado con la brújula,
//             detecta cambios de color y esquiva obstáculos volviendo al trayecto.
//   CALIB   – gira en el sitio 8 s para calibrar la brújula (hard/soft iron).
//
//  Placa: ESP32 DevKit V1 – arduino-esp32 core >= 3.0
// =====================================================================
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>
#include "config.h"
#include "motors.h"
#include "compass.h"
#include "color_sensor.h"
#include "sensors.h"

// ---------------------------------------------------------------------
//  Tipos y estado global
// ---------------------------------------------------------------------
enum Mode { MODE_MANUAL, MODE_AUTO, MODE_CALIB };
enum Nav  { NAV_LINEA, NAV_RUMBO };
enum AutoState {
  ST_SEGUIR, ST_FRENO, ST_ESC_IZQ, ST_ESC_DER, ST_GIRO1, ST_AVANCE1,
  ST_RODEO, ST_CRUZAR, ST_ALINEAR, ST_REORIENTAR, ST_PAUSA
};
static const char* MODE_NAMES[] = {"MANUAL", "AUTO", "CALIBRANDO"};
static const char* NAV_NAMES[]  = {"linea", "rumbo"};
static const char* ST_NAMES[]   = {"SEGUIR", "FRENO", "ESCANEO_IZQ", "ESCANEO_DER", "GIRO_EVASION",
                                   "AVANCE_LATERAL", "RODEO", "CRUZAR", "ALINEAR", "REORIENTAR", "PAUSA"};

struct __attribute__((packed)) RemotePacket {   // debe coincidir con control_remoto.ino
  uint16_t magic;
  uint8_t  seq;
  int8_t   x;        // -100..100 giro
  int8_t   y;        // -100..100 avance
  uint8_t  buttons;  // bit0 = cambiar modo, bit1 = parar, bit2 = turbo
};

static Mode mode = MODE_MANUAL;
static Nav nav = NAV_LINEA;
static AutoState ast = ST_SEGUIR;
static uint32_t stateSince = 0;

static float headingDes = 0;          // dirección polar deseada (°)
static float autoSpeed = AUTO_BASE_SPEED;
static float manualV = 0, manualW = 0;
static uint32_t manualUntil = 0;
static String cmdSource = "ninguno";
static String lastMove = "stop";

// Evasión de obstáculos
static float h0 = 0;                  // rumbo antes del obstáculo
static int side = 1;                  // +1 = esquiva por la derecha, -1 izquierda
static float distLeft = 0, distRight = 0;
static uint32_t obstaclesAvoided = 0;
static float lastLineErr = 0;
static uint32_t prevLineSeen = 0;
static uint32_t avoidEnd = 0;
static uint8_t tempLevel = 0;         // 0 normal, 1 aviso, 2 sobretemperatura         // instante en que terminó la última evasión    // última vez que se vio la línea (ciclo anterior)        // memoria del lado donde se vio la línea

// Eventos para la app / chatbot
static char lastEvent[96] = "Sistema iniciado";
static uint32_t eventId = 0;

// ESP-NOW
static volatile bool remotePending = false;
static RemotePacket remotePkt;
static uint8_t lastRemoteButtons = 0;
static uint32_t lastRemoteMs = 0;

WebServer server(HTTP_PORT);

// ---------------------------------------------------------------------
//  Utilidades
// ---------------------------------------------------------------------
static void logEvent(const char* fmt, ...) {
  va_list ap; va_start(ap, fmt);
  vsnprintf(lastEvent, sizeof(lastEvent), fmt, ap);
  va_end(ap);
  eventId++;
  Serial.printf("[EVENTO %lu] %s\n", (unsigned long)eventId, lastEvent);
}

static void setAutoState(AutoState s) { ast = s; stateSince = millis(); }

static void setMode(Mode m) {
  mode = m;
  Motors::stop();
  manualV = manualW = 0;
  if (m == MODE_AUTO) {
    headingDes = (nav == NAV_LINEA) ? Compass::heading : headingDes;
    setAutoState(ST_SEGUIR);
  }
  if (m == MODE_CALIB) { Compass::startCalibration(); stateSince = millis(); }
  logEvent("Modo %s", MODE_NAMES[m]);
}

// Gira en el sitio hacia 'target'. Devuelve true al alcanzarlo.
static bool turnTo(float target) {
  float err = Compass::wrap180(target - Compass::heading);
  if (fabsf(err) < HEADING_TOL_DEG) { Motors::stop(); return true; }
  float w = constrain(KP_HEADING * 2.0f * err, -TURN_SPEED, TURN_SPEED);
  if (fabsf(w) < 0.35f) w = (w > 0) ? 0.35f : -0.35f;   // vence la fricción estática
  Motors::arcade(0, w);
  return false;
}

// Avanza manteniendo el rumbo 'target' (control proporcional)
static void driveHeading(float target, float speed) {
  float err = Compass::wrap180(target - Compass::heading);
  float w = constrain(KP_HEADING * err, -0.5f, 0.5f);
  float v = (fabsf(err) > 45) ? speed * 0.3f : speed;
  Motors::arcade(v, w);
}

// ---------------------------------------------------------------------
//  Modo autónomo: máquina de estados
// ---------------------------------------------------------------------
static void autoControl(uint32_t now) {
  uint32_t dt = now - stateSince;
  switch (ast) {
    case ST_SEGUIR:
      if (Sonar::distCm < OBSTACLE_CM) {
        h0 = (nav == NAV_LINEA) ? Compass::heading : headingDes;
        Motors::brake();
        logEvent("Obstaculo a %.0f cm: iniciando evasion", Sonar::distCm);
        setAutoState(ST_FRENO);
        break;
      }
      if (nav == NAV_RUMBO) { driveHeading(headingDes, autoSpeed); break; }
      if (LineSensors::any() && now - prevLineSeen > 800 && avoidEnd != 0 && now - avoidEnd < 6000 &&
          fabsf(Compass::wrap180(Compass::heading - h0)) > 100) {
        // se retomó la línea en sentido contrario: reorientar con la brújula
        logEvent("Linea retomada en sentido contrario: reorientando");
        setAutoState(ST_REORIENTAR);
        break;
      }
      if (LineSensors::any()) {
        float e = LineSensors::error();
        Motors::arcade(autoSpeed, 0.45f * e);
        if (e != 0) lastLineErr = e;
        // la dirección deseada sigue la orientación de la pista
        headingDes = Compass::wrap360(headingDes + 0.2f * Compass::wrap180(Compass::heading - headingDes));
      } else if (now - LineSensors::lastSeen < 800) {
        driveHeading(headingDes, autoSpeed * 0.8f);   // la brújula mantiene el rumbo en huecos
      } else if (lastLineErr != 0) {
        // búsqueda: gira hacia el lado donde se vio la línea por última vez
        // espiral que se abre con el tiempo para no quedar girando en círculo
        float lost = (now - LineSensors::lastSeen) / 1000.0f;
        float w = 0.35f * max(0.2f, 1.0f - (lost - 0.8f) / 6.0f);
        Motors::arcade(autoSpeed * 0.5f, lastLineErr > 0 ? w : -w);
      } else {
        driveHeading(headingDes, autoSpeed * 0.5f);   // búsqueda lenta con la brújula
      }
      break;

    case ST_FRENO:
      if (dt > 250) { Motors::stop(); Sonar::servoWrite(SERVO_LEFT); setAutoState(ST_ESC_IZQ); }
      break;
    case ST_ESC_IZQ:
      if (dt > 350) { distLeft = Sonar::measureOnce(); Sonar::servoWrite(SERVO_RIGHT); setAutoState(ST_ESC_DER); }
      break;
    case ST_ESC_DER:
      if (dt > 450) {
        distRight = Sonar::measureOnce();
        Sonar::servoWrite(SERVO_CENTER);
        side = (distRight >= distLeft) ? 1 : -1;
        logEvent("Esquivando por la %s (izq %.0f cm, der %.0f cm)",
                 side > 0 ? "derecha" : "izquierda", distLeft, distRight);
        setAutoState(ST_GIRO1);
      }
      break;
    case ST_GIRO1:
      if (turnTo(h0 + side * 60) || dt > 2500) setAutoState(ST_AVANCE1);
      break;
    case ST_AVANCE1:
      driveHeading(h0 + side * 60, autoSpeed);
      if (dt > 700) setAutoState(ST_RODEO);
      break;
    case ST_RODEO: {
      // arco que rodea el obstáculo y regresa hacia el trayecto
      if (Sonar::distCm < OBSTACLE_CM * 0.6f) { Motors::brake(); setAutoState(ST_FRENO); break; }
      Motors::arcade(autoSpeed, -side * RODEO_W);
      bool found = (nav == NAV_LINEA) && LineSensors::any() && dt > 500;
      bool rumboOk = (nav == NAV_RUMBO) &&
                     fabsf(Compass::wrap180(Compass::heading - (h0 - side * 45))) < 10;
      if (found || rumboOk || dt > 5000) {
        obstaclesAvoided++;
        headingDes = h0;
        avoidEnd = now;
        logEvent("Obstaculo superado (#%lu), retomando trayecto", (unsigned long)obstaclesAvoided);
        setAutoState(found ? ST_CRUZAR : ST_SEGUIR);
      }
      break;
    }
    case ST_CRUZAR:
      // avanza hasta dejar el centro del robot sobre la línea
      Motors::arcade(autoSpeed * 0.6f, 0);
      if (dt > 300) setAutoState(ST_ALINEAR);
      break;
    case ST_ALINEAR:
      // pivotando sobre la línea, el primer cruce girando hacia el lado de la
      // evasión corresponde al sentido de avance original de la pista
      if (LineSensors::c && dt > 250) {
        headingDes = Compass::heading;
        lastLineErr = 0;
        setAutoState(ST_SEGUIR);
      } else if (dt > 4000) {
        setAutoState(ST_SEGUIR);
      } else {
        Motors::arcade(0, side * 0.38f);
      }
      break;
    case ST_REORIENTAR:
      if (turnTo(h0) || dt > 3000) {
        headingDes = Compass::heading;
        avoidEnd = 0;                      // solo una reorientación por evasión
        setAutoState(ST_SEGUIR);
      }
      break;
    case ST_PAUSA:
      Motors::stop();
      break;
  }
}

// ---------------------------------------------------------------------
//  Protección térmica (termistor NTC en el paquete de baterías)
// ---------------------------------------------------------------------
static void thermalProtection() {
  if (!Thermistor::ok) return;
  float t = Thermistor::tempC;
  if (tempLevel < 2 && t >= TEMP_CUTOFF_C) {
    tempLevel = 2;
    if (mode != MODE_MANUAL) setMode(MODE_MANUAL);
    Motors::brake();
    logEvent("SOBRETEMPERATURA %.1f C: motores detenidos", t);
  } else if (tempLevel == 0 && t >= TEMP_WARN_C) {
    tempLevel = 1;
    logEvent("Temperatura alta en baterias: %.1f C", t);
  } else if (tempLevel > 0 && t < TEMP_WARN_C - TEMP_HYST_C) {
    tempLevel = 0;
    logEvent("Temperatura normal: %.1f C", t);
  }
}

// ---------------------------------------------------------------------
//  Modo manual
// ---------------------------------------------------------------------
static void manualControl(uint32_t now) {
  if (now > manualUntil) { manualV = manualW = 0; lastMove = "stop"; }
  float v = manualV, w = manualW;
  if (v > 0 && Sonar::distCm < SAFETY_STOP_CM) v = 0;   // anticolisión
  if (tempLevel == 2) { v *= 0.4f; w *= 0.4f; }          // en sobretemperatura solo maniobras lentas
  Motors::arcade(v, w);
}

static void applyMove(const String& m, float speed, uint32_t ms, const char* src) {
  if (mode != MODE_MANUAL) setMode(MODE_MANUAL);
  speed = constrain(speed, 0.0f, 1.0f);
  manualV = manualW = 0;
  if (m == "forward" || m == "arriba")          manualV = speed;
  else if (m == "backward" || m == "abajo")     manualV = -speed;
  else if (m == "right" || m == "derecha")      manualW = speed * 0.8f;
  else if (m == "left" || m == "izquierda")     manualW = -speed * 0.8f;
  manualUntil = millis() + constrain(ms, 100UL, 5000UL);
  lastMove = m;
  cmdSource = src;
}

// ---------------------------------------------------------------------
//  ESP-NOW (control remoto propio)
// ---------------------------------------------------------------------
static void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (len != sizeof(RemotePacket)) return;
  RemotePacket p; memcpy(&p, data, sizeof(p));
  if (p.magic != ESPNOW_MAGIC) return;
  remotePkt = p;
  remotePending = true;
}

static void processRemote() {
  if (!remotePending) return;
  remotePending = false;
  RemotePacket p = remotePkt;
  lastRemoteMs = millis();
  uint8_t pressed = p.buttons & ~lastRemoteButtons;   // flancos de subida
  lastRemoteButtons = p.buttons;
  if ((pressed & 0x01) && !(mode != MODE_AUTO && tempLevel == 2)) setMode(mode == MODE_AUTO ? MODE_MANUAL : MODE_AUTO);
  if (pressed & 0x02) { setMode(MODE_MANUAL); return; }
  if (mode != MODE_MANUAL) return;
  float k = (p.buttons & 0x04) ? 1.0f : 0.6f;
  manualV = k * p.y / 100.0f;
  manualW = k * 0.7f * p.x / 100.0f;
  manualUntil = millis() + 300;                        // el control transmite a 20 Hz
  cmdSource = "control_espnow";
  lastMove = (fabsf(manualV) < 0.05f && fabsf(manualW) < 0.05f) ? "stop" : "joystick";
}

// ---------------------------------------------------------------------
//  API HTTP (app Streamlit / chatbot)
// ---------------------------------------------------------------------
static void sendJson(int code, const String& body) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(code, "application/json", body);
}
static void replyOk(const char* msg) { sendJson(200, String("{\"ok\":true,\"msg\":\"") + msg + "\"}"); }

static void handleState() {
  char buf[1000];
  float err = Compass::wrap180(headingDes - Compass::heading);
  snprintf(buf, sizeof(buf),
    "{\"t\":%lu,\"mode\":\"%s\",\"nav\":\"%s\",\"state\":\"%s\","
    "\"heading\":%.1f,\"heading_des\":%.1f,\"heading_err\":%.1f,"
    "\"mag_raw\":[%d,%d,%d],\"compass_ok\":%s,"
    "\"dist_cm\":%.1f,\"obstacle\":%s,\"servo\":%d,\"obstacles_avoided\":%lu,"
    "\"color\":\"%s\",\"rgbc\":[%u,%u,%u,%u],\"color_changes\":%lu,\"color_ok\":%s,"
    "\"line\":[%d,%d,%d],\"pwm_l\":%.2f,\"pwm_r\":%.2f,\"auto_speed\":%.2f,"
    "\"batt_v\":%.2f,\"temp_c\":%.1f,\"temp_ok\":%s,\"temp_alarm\":%d,\"rssi_clients\":%d,\"cmd_src\":\"%s\",\"last_move\":\"%s\","
    "\"event_id\":%lu,\"event\":\"%s\",\"uptime_s\":%lu}",
    (unsigned long)millis(), MODE_NAMES[mode], NAV_NAMES[nav], ST_NAMES[ast],
    Compass::heading, headingDes, err,
    Compass::rawX, Compass::rawY, Compass::rawZ, Compass::ok ? "true" : "false",
    Sonar::distCm, (Sonar::distCm < OBSTACLE_CM) ? "true" : "false", Sonar::servoAngle,
    (unsigned long)obstaclesAvoided,
    ColorSensor::name(), ColorSensor::R, ColorSensor::G, ColorSensor::B, ColorSensor::C,
    (unsigned long)ColorSensor::changes, ColorSensor::ok ? "true" : "false",
    LineSensors::l, LineSensors::c, LineSensors::r, Motors::lastL, Motors::lastR, autoSpeed,
    Battery::volts, Thermistor::tempC, Thermistor::ok ? "true" : "false", tempLevel,
    WiFi.softAPgetStationNum(), cmdSource.c_str(), lastMove.c_str(),
    (unsigned long)eventId, lastEvent, (unsigned long)(millis() / 1000));
  sendJson(200, buf);
}

static void handleCmd() {
  String m = server.arg("move");
  float speed = server.hasArg("speed") ? server.arg("speed").toFloat() / 100.0f : 0.6f;
  uint32_t ms = server.hasArg("ms") ? server.arg("ms").toInt() : 500;
  String src = server.hasArg("src") ? server.arg("src") : "app";
  if (m == "stop" || m == "parar") { applyMove("stop", 0, 100, src.c_str()); Motors::brake(); replyOk("stop"); return; }
  if (m != "forward" && m != "backward" && m != "left" && m != "right" &&
      m != "arriba" && m != "abajo" && m != "izquierda" && m != "derecha") {
    sendJson(400, "{\"ok\":false,\"msg\":\"move invalido\"}"); return;
  }
  applyMove(m, speed, ms, src.c_str());
  replyOk(m.c_str());
}

static void handleMode() {
  String m = server.arg("m");
  if (server.hasArg("nav")) nav = (server.arg("nav") == "rumbo") ? NAV_RUMBO : NAV_LINEA;
  if (m == "auto" && tempLevel == 2) { sendJson(409, "{\"ok\":false,\"msg\":\"sobretemperatura\"}"); return; }
  if (m == "auto") setMode(MODE_AUTO);
  else if (m == "manual") setMode(MODE_MANUAL);
  else if (m == "pausa" && mode == MODE_AUTO) setAutoState(ST_PAUSA);
  else if (m == "reanudar" && mode == MODE_AUTO) setAutoState(ST_SEGUIR);
  else if (!server.hasArg("nav")) { sendJson(400, "{\"ok\":false,\"msg\":\"modo invalido\"}"); return; }
  replyOk(MODE_NAMES[mode]);
}

static void handleHeading() {
  if (server.hasArg("deg")) headingDes = Compass::wrap360(server.arg("deg").toFloat());
  else if (server.hasArg("rel")) headingDes = Compass::wrap360(Compass::heading + server.arg("rel").toFloat());
  else { sendJson(400, "{\"ok\":false,\"msg\":\"use deg o rel\"}"); return; }
  logEvent("Direccion deseada %.0f grados", headingDes);
  replyOk("heading");
}

static void handleSpeed() {
  autoSpeed = constrain(server.arg("v").toFloat() / 100.0f, 0.2f, 1.0f);
  replyOk("speed");
}

static void handleCalibrate() {
  String what = server.arg("what");
  if (what == "compass") { setMode(MODE_CALIB); replyOk("girando 8 s"); return; }
  if (what == "color") {
    String n = server.arg("name");
    if (ColorSensor::calibrate(n)) { logEvent("Color %s calibrado", n.c_str()); replyOk("color calibrado"); }
    else sendJson(400, "{\"ok\":false,\"msg\":\"color invalido\"}");
    return;
  }
  sendJson(400, "{\"ok\":false,\"msg\":\"what=compass|color\"}");
}

static const char INDEX_HTML[] PROGMEM = R"HTML(<!doctype html><html><head>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Robot ESP32</title>
<style>body{font-family:sans-serif;text-align:center;background:#111;color:#eee}
button{width:90px;height:60px;margin:4px;font-size:18px}pre{text-align:left}</style></head><body>
<h2>Robot ESP32 – control de respaldo</h2>
<div><button onclick="c('forward')">Arriba</button></div>
<div><button onclick="c('left')">Izq</button><button onclick="c('stop')">Stop</button>
<button onclick="c('right')">Der</button></div><div><button onclick="c('backward')">Abajo</button></div>
<div><button onclick="fetch('/api/mode?m=auto')">AUTO</button><button onclick="fetch('/api/mode?m=manual')">MANUAL</button></div>
<pre id=s></pre><script>function c(m){fetch('/api/cmd?move='+m+'&ms=600')}
setInterval(()=>fetch('/api/state').then(r=>r.json()).then(j=>s.textContent=JSON.stringify(j,null,1)),300)</script>
<p>Dashboard completo: app Streamlit (ver repositorio)</p></body></html>)HTML";

static void setupNetwork() {
  WiFi.mode(WIFI_AP_STA);   // AP para la app + STA para ESP-NOW
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASS, WIFI_CHANNEL);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  Serial.printf("AP %s listo en http://%s  MAC STA %s\n", WIFI_AP_SSID,
                WiFi.softAPIP().toString().c_str(), WiFi.macAddress().c_str());

  if (esp_now_init() == ESP_OK) esp_now_register_recv_cb(onEspNowRecv);
  else Serial.println("ERROR: ESP-NOW no inicio");

  server.on("/", []() { server.send_P(200, "text/html", INDEX_HTML); });
  server.on("/api/state", handleState);
  server.on("/api/cmd", handleCmd);
  server.on("/api/mode", handleMode);
  server.on("/api/heading", handleHeading);
  server.on("/api/speed", handleSpeed);
  server.on("/api/calibrate", handleCalibrate);
  server.onNotFound([]() { sendJson(404, "{\"ok\":false,\"msg\":\"no encontrado\"}"); });
  server.begin();
}

// ---------------------------------------------------------------------
//  setup / loop
// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  Motors::begin();
  Motors::stop();
  Wire.begin(PIN_SDA, PIN_SCL, I2C_FREQ);
  Serial.printf("Brujula QMC5883L: %s\n", Compass::begin() ? "OK" : "NO DETECTADA");
  Serial.printf("Color TCS34725: %s\n", ColorSensor::begin() ? "OK" : "NO DETECTADO");
  Sonar::begin();
  LineSensors::begin();
  analogSetPinAttenuation(PIN_VBAT, ADC_11db);
  Thermistor::begin();
  setupNetwork();
  Compass::update();
  headingDes = Compass::heading;
  logEvent("Robot listo. Conectese a la red %s", WIFI_AP_SSID);
}

void loop() {
  server.handleClient();
  processRemote();

  static uint32_t lastLoop = 0, lastTelemetry = 0;
  uint32_t now = millis();
  if (now - lastLoop < LOOP_PERIOD_MS) return;
  lastLoop = now;

  // 1) Percepción
  Compass::update();
  prevLineSeen = LineSensors::lastSeen;
  // En la sección negra la línea guía es blanca: se invierte la polaridad del TCRT5000
  LineSensors::update(ColorSensor::current == 0);
  Battery::update();
  Thermistor::update();
  if (ast != ST_ESC_IZQ && ast != ST_ESC_DER) Sonar::update();   // durante el escaneo se mide aparte
  const char* prevColor = ColorSensor::name();
  if (ColorSensor::update()) logEvent("Cambio de seccion: %s -> %s", prevColor, ColorSensor::name());

  // 2) Decisión y actuación
  thermalProtection();
  switch (mode) {
    case MODE_MANUAL: manualControl(now); break;
    case MODE_AUTO:   autoControl(now);   break;
    case MODE_CALIB:
      Motors::arcade(0, 0.45f);                       // giro lento en el sitio
      if (now - stateSince > 8000) { Compass::finishCalibration(); setMode(MODE_MANUAL);
                                     logEvent("Brujula calibrada"); }
      break;
  }

  // 3) Indicadores y telemetría serie (5 Hz)
  digitalWrite(PIN_LED, mode == MODE_AUTO ? ((now / 250) % 2) : HIGH);
  if (now - lastTelemetry > 200) {
    lastTelemetry = now;
    Serial.printf("H=%.1f Hd=%.1f d=%.0fcm col=%s L=%d%d%d m=%s st=%s\n", Compass::heading, headingDes,
                  Sonar::distCm, ColorSensor::name(), LineSensors::l, LineSensors::c, LineSensors::r,
                  MODE_NAMES[mode], ST_NAMES[ast]);
  }
}
