// =====================================================================
//  control_remoto.ino – Control manual propio basado en ESP32
//  Joystick analógico KY-023 + 2 pulsadores, enlace ESP-NOW a 20 Hz.
//
//  Conexiones:
//    VRx -> GPIO34   VRy -> GPIO35   SW (joystick) -> GPIO32 (turbo)
//    BTN_MODO -> GPIO25 (a GND)   BTN_STOP -> GPIO26 (a GND)
//    LED estado -> GPIO2
//  Alimentación: batería 1S 18650 + módulo TP4056 + regulador 3.3 V.
//
//  Si se conoce la MAC del robot (se imprime por Serial al arrancar el
//  robot), escríbala en ROBOT_MAC; si no, se usa broadcast filtrado por
//  ESPNOW_MAGIC.
// =====================================================================
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#define PIN_VRX       34
#define PIN_VRY       35
#define PIN_SW        32
#define PIN_BTN_MODE  25
#define PIN_BTN_STOP  26
#define PIN_LED       2
#define WIFI_CHANNEL  1
#define ESPNOW_MAGIC  0x52A7
#define DEADZONE      8

uint8_t ROBOT_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};   // broadcast por defecto

struct __attribute__((packed)) RemotePacket {
  uint16_t magic;
  uint8_t  seq;
  int8_t   x;
  int8_t   y;
  uint8_t  buttons;
};

static int centerX = 2048, centerY = 2048;
static uint8_t seq = 0;

static int8_t axis(int raw, int center) {
  int v = (raw - center) * 100 / 2048;
  if (abs(v) < DEADZONE) v = 0;
  return (int8_t)constrain(v, -100, 100);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_SW, INPUT_PULLUP);
  pinMode(PIN_BTN_MODE, INPUT_PULLUP);
  pinMode(PIN_BTN_STOP, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  analogReadResolution(12);

  // auto-calibración del centro del joystick
  long sx = 0, sy = 0;
  for (int i = 0; i < 32; i++) { sx += analogRead(PIN_VRX); sy += analogRead(PIN_VRY); delay(5); }
  centerX = sx / 32; centerY = sy / 32;

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) { Serial.println("ESP-NOW error"); return; }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, ROBOT_MAC, 6);
  peer.channel = WIFI_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  Serial.println("Control remoto listo");
}

void loop() {
  RemotePacket p;
  p.magic = ESPNOW_MAGIC;
  p.seq = seq++;
  p.x = axis(analogRead(PIN_VRX), centerX);
  p.y = -axis(analogRead(PIN_VRY), centerY);   // empujar hacia adelante = avanzar
  p.buttons = (digitalRead(PIN_BTN_MODE) == LOW ? 0x01 : 0) |
              (digitalRead(PIN_BTN_STOP) == LOW ? 0x02 : 0) |
              (digitalRead(PIN_SW) == LOW ? 0x04 : 0);
  esp_err_t r = esp_now_send(ROBOT_MAC, (uint8_t*)&p, sizeof(p));
  digitalWrite(PIN_LED, r == ESP_OK ? (seq / 5) % 2 : HIGH);
  delay(50);   // 20 Hz
}
