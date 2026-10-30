/*
 * ============================================================================
 * BARTENDER AUTOMÁTICO v2.0 — FIRMWARE HÍBRIDO (ESP8266 NodeMCU & ESP32)
 * ============================================================================
 * Compatível com:
 *   1. API HTTP JSON via Wi-Fi (porta 80) + mDNS (http://bartender.local)
 *   2. Comunicação USB Serial (115200 baud) como fallback direto
 *   3. Dosagem não-bloqueante (millis) com telemetria de progresso ao vivo
 *   4. Parada de Emergência instantânea (/stop ou comando Serial STOP)
 *   5. Persistência de calibração de vazão (ml/s) em Flash (EEPROM / NVS)
 *
 * PINOUT AUTOMÁTICO POR PLACA:
 *   [ESP8266 NodeMCU 1.0 / Wemos D1 Mini]
 *     - D1 (GPIO 5)  -> Bomba 1 (Amarela / Citrus)
 *     - D2 (GPIO 4)  -> Bomba 2 (Vermelha / Frutas Vermelhas)
 *     - D5 (GPIO 14) -> Bomba 3 (Verde / Maçã Verde)
 *     - D6 (GPIO 12) -> Bomba 4 (Azul / Base Água c/ Gás)
 *     - D0 (GPIO 16) -> LED Antena / Indicador
 *     - D7 (GPIO 13) -> Buzzer Passivo (melodia final)
 *
 *   [ESP32-WROOM-32 / DevKit V1]
 *     - GPIO 16, 17, 18, 19 -> Bombas 1 a 4 | GPIO 21 -> LED | GPIO 22 -> Buzzer
 * ============================================================================
 */

#if defined(ESP8266)
  #include <ESP8266WiFi.h>
  #include <ESP8266WebServer.h>
  #include <ESP8266mDNS.h>
  #include <EEPROM.h>
  using HttpServer = ESP8266WebServer;
  const char* DEVICE_MODEL = "ESP8266-NodeMCU";
#elif defined(ESP32)
  #include <WiFi.h>
  #include <WebServer.h>
  #include <ESPmDNS.h>
  #include <Preferences.h>
  using HttpServer = WebServer;
  const char* DEVICE_MODEL = "ESP32-WROOM-32";
#else
  #error "Selecione uma placa ESP8266 (NodeMCU 1.0 ESP-12E) ou ESP32 no Arduino IDE."
#endif

// Carrega senhas e chaves privadas de bombas/secrets.h (ignorado no Git)
#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "bombas/secrets.h nao encontrado! Copie secrets.example.h para secrets.h e preencha seu Wi-Fi."
#define SECRET_WIFI_SSID ""
#define SECRET_WIFI_PASSWORD ""
#define SECRET_AP_SSID "Bartender-ESP"
#define SECRET_AP_PASSWORD "12345678"
#define SECRET_API_TOKEN ""
#endif

/* ================= CONFIGURAÇÃO DE REDE WI-FI ================= */
const char* WIFI_SSID = SECRET_WIFI_SSID;
const char* WIFI_PASSWORD = SECRET_WIFI_PASSWORD;
const char* MDNS_HOSTNAME = "bartender";  // http://bartender.local

// Caso o Wi-Fi acima não conecte em 10s, cria ponto de acesso próprio:
const char* AP_SSID = SECRET_AP_SSID;
const char* AP_PASSWORD = SECRET_AP_PASSWORD;
const char* API_TOKEN = SECRET_API_TOKEN;

/* ================= PINOS SEGUROS (ESP8266 / ESP32) ============ */
#if defined(ESP8266)
const int PIN_AMARELO  = 5;   // Pino D1 (GPIO 5)  — Bomba 1 (Amarela)
const int PIN_VERMELHO = 4;   // Pino D2 (GPIO 4)  — Bomba 2 (Vermelha)
const int PIN_VERDE    = 14;  // Pino D5 (GPIO 14) — Bomba 3 (Verde)
const int PIN_AZUL     = 12;  // Pino D6 (GPIO 12) — Bomba 4 (Azul / Base)

const int PIN_LED      = 16;  // Pino D0 (GPIO 16) — LED Antena / Indicador
const int PIN_BUZZER   = 13;  // Pino D7 (GPIO 13) — Buzzer passivo (melodia)
#else
const int PIN_AMARELO  = 16;  // GPIO 16 — Bomba 1 (Citrus / Amarela)
const int PIN_VERMELHO = 17;  // GPIO 17 — Bomba 2 (Frutas Vermelhas)
const int PIN_VERDE    = 18;  // GPIO 18 — Bomba 3 (Maçã Verde)
const int PIN_AZUL     = 19;  // GPIO 19 — Bomba 4 (Base Água c/ Gás / Soda)

const int PIN_LED      = 21;  // GPIO 21 — LED Antena / Indicador
const int PIN_BUZZER   = 22;  // GPIO 22 — Buzzer passivo (melodia final)
#endif

const bool RELE_ATIVO_EM_LOW = true;

/* ================= CALIBRAÇÃO PADRÃO (ml/s) =================== */
struct PumpDef {
  const char* key;
  int pin;
  float flowMlPerSec;
};

PumpDef pumps[4] = {
  { "amarelo", PIN_AMARELO, 30.5f },
  { "vermelho", PIN_VERMELHO, 32.3f },
  { "verde", PIN_VERDE, 32.3f },
  { "azul", PIN_AZUL, 35.9f }
};

/* ================= NOTAS MUSICAIS ============================= */
#define NOTE_REST 0
#define NOTE_GS4 415
#define NOTE_AS4 466
#define NOTE_C5 523

const int MELODY_NOTES[] = {
  NOTE_C5, NOTE_C5, NOTE_C5, NOTE_C5,
  NOTE_GS4, NOTE_AS4, NOTE_C5, NOTE_REST, NOTE_AS4, NOTE_C5
};
const int MELODY_DIVS[] = { 8, 8, 8, 3, 3, 3, 8, 8, 8, 2 };
const int MELODY_LEN = sizeof(MELODY_NOTES) / sizeof(MELODY_NOTES[0]);

/* ================= MÁQUINA DE ESTADOS ========================= */
enum SystemState {
  STATE_IDLE,
  STATE_DOSING,
  STATE_PAUSING,
  STATE_MELODY,
  STATE_DONE,
  STATE_STOPPED
};

struct DoseStep {
  int pumpIdx;
  float ml;
  unsigned long pourMs;
  unsigned long pauseMs;
};

const int MAX_STEPS = 12;
DoseStep plan[MAX_STEPS];
int planCount = 0;
int currentStep = 0;

SystemState state = STATE_IDLE;
String currentDrinkName = "";
unsigned long stateStartMs = 0;
unsigned long planTotalMs = 0;
unsigned long completedMs = 0;
unsigned long lastSerialReportMs = 0;

// Controle não-bloqueante da melodia
int melodyIdx = 0;
bool melodyGapPhase = false;
unsigned long melodyPhaseMs = 0;
unsigned long melodyPhaseStart = 0;

HttpServer server(80);
#if defined(ESP32)
Preferences prefs;
#endif

/* ================= CONTROLE SEGURO DOS RELÉS ================== */
inline int nivelLigado() {
  return RELE_ATIVO_EM_LOW ? LOW : HIGH;
}
inline int nivelDesligado() {
  return RELE_ATIVO_EM_LOW ? HIGH : LOW;
}

void desligarTodasBombas() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(pumps[i].pin, nivelDesligado());
  }
}

void ligarBomba(int idx) {
  desligarTodasBombas();
  if (idx >= 0 && idx < 4) {
    digitalWrite(pumps[idx].pin, nivelLigado());
  }
}

int findPumpIndex(const String& name) {
  String lower = name;
  lower.trim();
  lower.toLowerCase();
  for (int i = 0; i < 4; i++) {
    if (lower == pumps[i].key) return i;
  }
  return -1;
}

/* ================= PERSISTÊNCIA FLASH (VAZÕES) ================ */
#if defined(ESP8266)
struct EepromCalib {
  uint32_t magic;
  float rates[4];
};
const uint32_t CALIB_MAGIC = 0xBA7E2026UL;

void carregarCalibracao() {
  EEPROM.begin(sizeof(EepromCalib));
  EepromCalib c;
  EEPROM.get(0, c);
  if (c.magic == CALIB_MAGIC) {
    for (int i = 0; i < 4; i++) {
      if (c.rates[i] > 1.0f && c.rates[i] <= 200.0f) {
        pumps[i].flowMlPerSec = c.rates[i];
      }
    }
  }
  EEPROM.end();
}

void salvarCalibracao() {
  EEPROM.begin(sizeof(EepromCalib));
  EepromCalib c;
  c.magic = CALIB_MAGIC;
  for (int i = 0; i < 4; i++) {
    c.rates[i] = pumps[i].flowMlPerSec;
  }
  EEPROM.put(0, c);
  EEPROM.commit();
  EEPROM.end();
}
#else
void carregarCalibracao() {
  prefs.begin("bartender", true);
  for (int i = 0; i < 4; i++) {
    float saved = prefs.getFloat(pumps[i].key, pumps[i].flowMlPerSec);
    if (saved > 1.0f && saved <= 200.0f) {
      pumps[i].flowMlPerSec = saved;
    }
  }
  prefs.end();
}

void salvarCalibracao() {
  prefs.begin("bartender", false);
  for (int i = 0; i < 4; i++) {
    prefs.putFloat(pumps[i].key, pumps[i].flowMlPerSec);
  }
  prefs.end();
}
#endif

/* ================= AUXILIARES DE PARSING JSON SIMPLES ========= */
String extractJsonString(const String& body, const char* key) {
  String pattern = String("\"") + key + "\"";
  int pos = body.indexOf(pattern);
  if (pos < 0) return "";
  int colon = body.indexOf(':', pos + pattern.length());
  if (colon < 0) return "";
  int q1 = body.indexOf('"', colon + 1);
  if (q1 < 0) return "";
  int q2 = body.indexOf('"', q1 + 1);
  if (q2 < 0) return "";
  return body.substring(q1 + 1, q2);
}

float extractJsonFloat(const String& body, const char* key, float fallback = -1.0f) {
  String pattern = String("\"") + key + "\"";
  int pos = body.indexOf(pattern);
  if (pos < 0) return fallback;
  int colon = body.indexOf(':', pos + pattern.length());
  if (colon < 0) return fallback;
  int start = colon + 1;
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '\t')) start++;
  int end = start;
  while (end < (int)body.length() && (isDigit(body[end]) || body[end] == '.')) end++;
  if (end == start) return fallback;
  return body.substring(start, end).toFloat();
}

/* ================= MONTAGEM E EXECUÇÃO DE PLANOS ============== */
bool parsePlanString(const String& planStr) {
  planCount = 0;
  planTotalMs = 0;
  int start = 0;

  while (start < (int)planStr.length() && planCount < MAX_STEPS) {
    int comma = planStr.indexOf(',', start);
    String token = (comma < 0) ? planStr.substring(start) : planStr.substring(start, comma);
    token.trim();

    if (token.length() > 0) {
      int c1 = token.indexOf(':');
      int c2 = (c1 >= 0) ? token.indexOf(':', c1 + 1) : -1;
      if (c1 > 0) {
        String pName = token.substring(0, c1);
        float ml = (c2 > 0) ? token.substring(c1 + 1, c2).toFloat() : token.substring(c1 + 1).toFloat();
        unsigned long pauseMs = (c2 > 0) ? (unsigned long)token.substring(c2 + 1).toInt() : 1200UL;

        int pIdx = findPumpIndex(pName);
        if (pIdx >= 0 && ml > 0.0f && ml <= 500.0f) {
          unsigned long pourMs = (unsigned long)((ml / pumps[pIdx].flowMlPerSec) * 1000.0f);
          plan[planCount] = { pIdx, ml, pourMs, pauseMs };
          planTotalMs += pourMs + pauseMs;
          planCount++;
        }
      }
    }

    if (comma < 0) break;
    start = comma + 1;
  }

  return planCount > 0;
}

bool carregarPreset(const String& code) {
  String upper = code;
  upper.trim();
  upper.toUpperCase();

  if (upper == "RED") {
    currentDrinkName = "Red Robotics";
    return parsePlanString("vermelho:70:1500,azul:220:0");
  }
  if (upper == "YELLOW") {
    currentDrinkName = "Yellow Web";
    return parsePlanString("amarelo:100:1500,azul:250:0");
  }
  if (upper == "GREEN") {
    currentDrinkName = "Green Games";
    return parsePlanString("verde:101:1500,azul:250:0");
  }
  if (upper == "MIX") {
    currentDrinkName = "Mix Basics";
    return parsePlanString("amarelo:50:1500,vermelho:50:1500,azul:270:0");
  }
  return false;
}

void iniciarPlano() {
  if (planCount <= 0) return;
  completedMs = 0;
  currentStep = 0;
  state = STATE_DOSING;
  stateStartMs = millis();
  digitalWrite(PIN_LED, HIGH);
  ligarBomba(plan[0].pumpIdx);
  Serial.println("START:" + currentDrinkName);
}

void paradaEmergencia() {
  desligarTodasBombas();
  noTone(PIN_BUZZER);
  digitalWrite(PIN_LED, LOW);
  state = STATE_STOPPED;
  Serial.println("STOPPED");
}

int calcularProgresso() {
  if (state == STATE_DONE) return 100;
  if (state == STATE_MELODY) return 98;
  if (state != STATE_DOSING && state != STATE_PAUSING) return 0;
  if (planTotalMs == 0) return 50;

  unsigned long atual = completedMs + (millis() - stateStartMs);
  int pct = (int)((atual * 96UL) / planTotalMs);
  if (pct < 2) pct = 2;
  if (pct > 96) pct = 96;
  return pct;
}

const char* stateToString() {
  switch (state) {
    case STATE_DOSING:
    case STATE_PAUSING: return "dispensing";
    case STATE_MELODY: return "melody";
    case STATE_DONE: return "done";
    case STATE_STOPPED: return "stopped";
    default: return "idle";
  }
}

/* ================= ATUALIZAÇÃO DA MÁQUINA DE ESTADOS ========== */
void iniciarMelodia() {
  desligarTodasBombas();
  state = STATE_MELODY;
  melodyIdx = 0;
  melodyGapPhase = false;
  melodyPhaseMs = 1000UL / MELODY_DIVS[0];
  melodyPhaseStart = millis();

  if (MELODY_NOTES[0] != NOTE_REST) {
    digitalWrite(PIN_LED, HIGH);
    tone(PIN_BUZZER, MELODY_NOTES[0], melodyPhaseMs);
  }
}

void atualizarMaquinaEstados() {
  unsigned long now = millis();

  if (state == STATE_DOSING) {
    DoseStep& s = plan[currentStep];
    if (now - stateStartMs >= s.pourMs) {
      desligarTodasBombas();
      completedMs += s.pourMs;

      if (s.pauseMs > 0) {
        state = STATE_PAUSING;
        stateStartMs = now;
      } else {
        currentStep++;
        if (currentStep >= planCount) {
          iniciarMelodia();
        } else {
          stateStartMs = now;
          ligarBomba(plan[currentStep].pumpIdx);
        }
      }
    } else if (now - lastSerialReportMs >= 400) {
      lastSerialReportMs = now;
      Serial.printf("PROGRESS:%d:%s\n", calcularProgresso(), pumps[s.pumpIdx].key);
    }
  } else if (state == STATE_PAUSING) {
    DoseStep& s = plan[currentStep];
    if (now - stateStartMs >= s.pauseMs) {
      completedMs += s.pauseMs;
      currentStep++;
      if (currentStep >= planCount) {
        iniciarMelodia();
      } else {
        state = STATE_DOSING;
        stateStartMs = now;
        ligarBomba(plan[currentStep].pumpIdx);
      }
    }
  } else if (state == STATE_MELODY) {
    if (now - melodyPhaseStart >= melodyPhaseMs) {
      if (!melodyGapPhase) {
        digitalWrite(PIN_LED, LOW);
        noTone(PIN_BUZZER);
        melodyGapPhase = true;
        melodyPhaseMs = (unsigned long)(melodyPhaseMs * 0.35f);
        melodyPhaseStart = now;
      } else {
        melodyIdx++;
        if (melodyIdx >= MELODY_LEN) {
          noTone(PIN_BUZZER);
          digitalWrite(PIN_LED, LOW);
          state = STATE_DONE;
          Serial.println("DONE");
        } else {
          melodyGapPhase = false;
          melodyPhaseMs = 1000UL / MELODY_DIVS[melodyIdx];
          melodyPhaseStart = now;
          if (MELODY_NOTES[melodyIdx] != NOTE_REST) {
            digitalWrite(PIN_LED, HIGH);
            tone(PIN_BUZZER, MELODY_NOTES[melodyIdx], melodyPhaseMs);
          } else {
            digitalWrite(PIN_LED, LOW);
            noTone(PIN_BUZZER);
          }
        }
      }
    }
  }
}

/* ================= ROTAS HTTP (WI-FI JSON API) ================ */
void sendCorsHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type, X-Bartender-Token");
}

bool verificarTokenHttp() {
  if (strlen(API_TOKEN) == 0) return true;
  if (server.header("X-Bartender-Token") == String(API_TOKEN)) return true;
  server.send(401, "application/json", "{\"ok\":false,\"error\":\"Token invalido ou ausente\"}");
  return false;
}

void handleOptions() {
  sendCorsHeaders();
  server.send(204);
}

void handleStatus() {
  sendCorsHeaders();
  String curPump = "";
  if (state == STATE_DOSING && currentStep < planCount) {
    curPump = pumps[plan[currentStep].pumpIdx].key;
  }
  String ipStr = (WiFi.status() == WL_CONNECTED)
                   ? WiFi.localIP().toString()
                   : WiFi.softAPIP().toString();
  int rssi = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;

  String json = "{";
  json += "\"ok\":true,";
  json += "\"device\":\"" + String(DEVICE_MODEL) + "\",";
  json += "\"state\":\"" + String(stateToString()) + "\",";
  json += "\"drink_name\":\"" + currentDrinkName + "\",";
  json += "\"progress\":" + String(calcularProgresso()) + ",";
  json += "\"current_pump\":\"" + curPump + "\",";
  json += "\"step_index\":" + String(currentStep + 1) + ",";
  json += "\"total_steps\":" + String(planCount) + ",";
  json += "\"ip\":\"" + ipStr + "\",";
  json += "\"rssi\":" + String(rssi) + ",";
  json += "\"pumps\":{";
  for (int i = 0; i < 4; i++) {
    json += "\"" + String(pumps[i].key) + "\":" + String(pumps[i].flowMlPerSec, 1);
    if (i < 3) json += ",";
  }
  json += "}}";

  server.send(200, "application/json", json);
}

void handleDispense() {
  sendCorsHeaders();
  if (!verificarTokenHttp()) return;
  if (state == STATE_DOSING || state == STATE_PAUSING || state == STATE_MELODY) {
    server.send(409, "application/json", "{\"ok\":false,\"error\":\"Drink ja em preparo\"}");
    return;
  }

  String body = server.arg("plain");
  String name = extractJsonString(body, "name");
  String planStr = extractJsonString(body, "plan");
  String preset = extractJsonString(body, "drink");

  bool ok = false;
  if (planStr.length() > 0) {
    currentDrinkName = (name.length() > 0) ? name : "Drink";
    ok = parsePlanString(planStr);
  } else if (preset.length() > 0) {
    ok = carregarPreset(preset);
  } else {
    // Suporte direto a JSON com volumes por bomba: {"amarelo":50,"azul":200}
    String built = "";
    for (int i = 0; i < 4; i++) {
      float v = extractJsonFloat(body, pumps[i].key, 0.0f);
      if (v > 0.0f) {
        if (built.length() > 0) built += ",";
        built += String(pumps[i].key) + ":" + String(v, 1) + ":" + String(i == 3 ? 0 : 1200);
      }
    }
    currentDrinkName = (name.length() > 0) ? name : "Custom";
    ok = parsePlanString(built);
  }

  if (!ok) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Plano de dosagem invalido\"}");
    return;
  }

  iniciarPlano();
  server.send(202, "application/json", "{\"ok\":true,\"state\":\"dispensing\"}");
}

void handleStop() {
  sendCorsHeaders();
  if (!verificarTokenHttp()) return;
  paradaEmergencia();
  server.send(200, "application/json", "{\"ok\":true,\"state\":\"stopped\"}");
}

void handleConfigPumps() {
  sendCorsHeaders();
  if (!verificarTokenHttp()) return;
  String body = server.arg("plain");
  bool changed = false;

  for (int i = 0; i < 4; i++) {
    float val = extractJsonFloat(body, pumps[i].key, -1.0f);
    if (val > 1.0f && val <= 200.0f) {
      pumps[i].flowMlPerSec = val;
      changed = true;
    }
  }
  if (changed) salvarCalibracao();
  handleStatus();
}

/* ================= COMANDOS VIA USB SERIAL ==================== */
void processarSerial() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("STOP")) {
    paradaEmergencia();
    return;
  }
  if (cmd.equalsIgnoreCase("STATUS")) {
    Serial.printf("STATE:%s:%d\n", stateToString(), calcularProgresso());
    return;
  }

  if (state == STATE_DOSING || state == STATE_PAUSING || state == STATE_MELODY) {
    Serial.println("BUSY");
    return;
  }

  if (cmd.startsWith("PLAN:")) {
    currentDrinkName = "Drink Serial";
    if (parsePlanString(cmd.substring(5))) {
      iniciarPlano();
    } else {
      Serial.println("CMD_ERR");
    }
  } else if (carregarPreset(cmd)) {
    iniciarPlano();
  } else {
    Serial.println("CMD_ERR");
  }
}

/* ================= INICIALIZAÇÃO ============================== */
void conectarRede() {
  WiFi.mode(WIFI_STA);
  if (String(WIFI_SSID) != "SEU_WIFI_AQUI" && strlen(WIFI_SSID) > 0) {
    Serial.printf("Conectando ao Wi-Fi '%s'", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
      delay(250);
      Serial.print(".");
    }
    Serial.println();
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi conectado! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.printf("Modo Access Point ativo: '%s' | IP: %s\n",
                  AP_SSID, WiFi.softAPIP().toString().c_str());
  }

  if (MDNS.begin(MDNS_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    Serial.printf("mDNS ativo: http://%s.local\n", MDNS_HOSTNAME);
  }
}

void setup() {
  // Pré-carrega nível DESLIGADO antes do pinMode para evitar pulsos nos relés no boot
  for (int i = 0; i < 4; i++) {
    digitalWrite(pumps[i].pin, nivelDesligado());
    pinMode(pumps[i].pin, OUTPUT);
    digitalWrite(pumps[i].pin, nivelDesligado());
  }

  digitalWrite(PIN_LED, LOW);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  Serial.begin(115200);
  delay(200);
  Serial.printf("\n=== Bartender Automatico v2.0 (%s) ===\n", DEVICE_MODEL);

  carregarCalibracao();
  conectarRede();

  server.on("/status", HTTP_GET, handleStatus);
  server.on("/status", HTTP_OPTIONS, handleOptions);
  server.on("/dispense", HTTP_POST, handleDispense);
  server.on("/dispense", HTTP_OPTIONS, handleOptions);
  server.on("/stop", HTTP_POST, handleStop);
  server.on("/stop", HTTP_OPTIONS, handleOptions);
  server.on("/config/pumps", HTTP_POST, handleConfigPumps);
  server.on("/config/pumps", HTTP_OPTIONS, handleOptions);

#if defined(ESP8266)
  server.collectHeaders("X-Bartender-Token");
#else
  const char* headerKeys[] = { "X-Bartender-Token" };
  server.collectHeaders(headerKeys, 1);
#endif

  server.begin();
  Serial.println("Servidor HTTP pronto na porta 80!");
}

void loop() {
#if defined(ESP8266)
  MDNS.update();
#endif
  server.handleClient();
  processarSerial();
  atualizarMaquinaEstados();
}
