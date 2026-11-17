/*
 * ============================================================================
 * PROJETO BARTENDER AUTOMÁTICO — FIRMWARE UNIFICADO v2.0 + v3.0 (MULTI-REDE)
 * Compatível com: ESP8266 (NodeMCU / Wemos D1 Mini) e ESP32 (DOIT DevKit V1)
 * ============================================================================
 *
 * RODA EM QUALQUER REDE (v2 na porta 8000 E v3 na porta 8010 sem regravar!):
 *   1. Multi-WiFi Automático: Escaneia o ambiente e conecta sozinho em qualquer
 *      rede conhecida (roteador de casa, hotspot do celular ou Wi-Fi de evento).
 *   2. Auto-Descoberta UDP (Porta 4210): O servidor Python localiza o IP do ESP
 *      automaticamente em qualquer rede (mesmo quando bartender.local falha!) e
 *      sincroniza sozinho o IP do servidor v3 sem precisar editar código.
 *   3. Portal Web Integrado (http://192.168.4.1): Mantém o Wi-Fi próprio do ESP
 *      ("Bartender-ESP32", senha "12345678") ativo para configurar qualquer Wi-Fi
 *      novo pelo navegador do celular em 5 segundos.
 *   4. Triplo Canal Simultâneo:
 *      - API HTTP LAN (v2 e v3): GET /status, POST /dispense, POST /stop
 *      - Cloud Sync IoT (v3):    POST /api/iot/maq-01/sync
 *      - Cabo USB Serial (115200): PLAN:..., STOP, STATUS, WIFI:..., NETINFO
 * ============================================================================
 */

#include <Arduino.h>
#include <EEPROM.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>

#if defined(ESP8266)
  #include <ESP8266WiFi.h>
  #include <ESP8266WebServer.h>
  #include <ESP8266mDNS.h>
  #include <ESP8266HTTPClient.h>
  #include <WiFiClientSecureBearSSL.h>
  using WebServerType = ESP8266WebServer;
  #define DEVICE_MODEL "ESP8266"
#elif defined(ESP32)
  #include <WiFi.h>
  #include <WebServer.h>
  #include <ESPmDNS.h>
  #include <HTTPClient.h>
  #include <WiFiClientSecure.h>
  #include <Preferences.h>
  using WebServerType = WebServer;
  #define DEVICE_MODEL "ESP32"
#else
  #error "Selecione uma placa ESP8266 (NodeMCU 1.0) ou ESP32 (ESP32 Dev Module) na Arduino IDE!"
#endif

#if defined(__has_include)
  #if __has_include("secrets.h")
    #include "secrets.h"
  #endif
#endif

/* ================= CREDENCIAIS MULTI-REDE EMBUTIDAS ========================= */
#ifndef SECRET_WIFI_SSID
  #define SECRET_WIFI_SSID      "DR.PC"
#endif
#ifndef SECRET_WIFI_PASSWORD
  #define SECRET_WIFI_PASSWORD  "fabio1234"
#endif
#ifndef SECRET_AP_SSID
  #define SECRET_AP_SSID        "Bartender-ESP32"
#endif
#ifndef SECRET_AP_PASSWORD
  #define SECRET_AP_PASSWORD    "12345678"
#endif
#ifndef SECRET_API_TOKEN
  #define SECRET_API_TOKEN      "iot_1CGRzJLaTkhqUIl9ITZcR3iC"
#endif
#ifndef SECRET_CLOUD_SYNC_URL
  #define SECRET_CLOUD_SYNC_URL "http://192.168.0.210:8010/api/iot/maq-01/sync"
#endif

struct WifiCred {
  const char* ssid;
  const char* pass;
};

#ifndef SECRET_KNOWN_WIFI_LIST
  #define SECRET_KNOWN_WIFI_LIST \
    { "DR.PC-2G", "F@bio1234" }, \
    { "DR.PC-2G", "fabio1234" }, \
    { "DR.PC", "fabio1234" }, \
    { "Xiaomi 13T", "91186240" }, \
    { "MM phone", "123456789" }, \
    { "iPhone", "fabinhoinho" }, \
    { "Mynds Tech", "Mynds2024#" }, \
    { "Jersom", "08010512" }, \
    { "ALFA_ACADEMICO", "ProfeAlfa#2026!" }, \
    { "MyndsCorp", "Mynds2024#" }, \
    { "AP00008299", "SN2008@+" }, \
    { "REGINA 2", "reta247724" }, \
    { "ACADEMICA", "WIFI@Academico" }
#endif

const WifiCred KNOWN_NETWORKS[] = {
  { SECRET_WIFI_SSID, SECRET_WIFI_PASSWORD },
  SECRET_KNOWN_WIFI_LIST
};
const int KNOWN_NETWORKS_COUNT = sizeof(KNOWN_NETWORKS) / sizeof(KNOWN_NETWORKS[0]);

const char* WIFI_SSID          = SECRET_WIFI_SSID;
const char* WIFI_PASSWORD      = SECRET_WIFI_PASSWORD;
const char* AP_SSID            = SECRET_AP_SSID;
const char* AP_PASSWORD        = SECRET_AP_PASSWORD;
const char* MDNS_HOSTNAME      = "bartender";
const uint16_t UDP_DISCOVERY_PORT = 4210;

String runtimeWifiSsid     = "";
String runtimeWifiPass     = "";
String runtimeCloudSyncUrl = SECRET_CLOUD_SYNC_URL;
String runtimeApiToken     = SECRET_API_TOKEN;

/* ================= LÓGICA DOS RELÉS E PINAGEM POR PLACA ===================== */
const bool RELAY_ACTIVE_LOW = true;

#if defined(ESP8266)
  // NodeMCU ESP8266: D1(5), D2(4), D5(14), D6(12), Buzzer D7(13), LED D0(16)
  const uint8_t PIN_BOMBA_AMARELO  = 5;   // D1
  const uint8_t PIN_BOMBA_VERMELHO = 4;   // D2
  const uint8_t PIN_BOMBA_VERDE    = 14;  // D5
  const uint8_t PIN_BOMBA_AZUL     = 12;  // D6
  const uint8_t PIN_BUZZER         = 13;  // D7
  const uint8_t PIN_LED            = 16;  // D0
#else
  // ESP32 DevKit V1: GPIO 16, 17, 18, 19, Buzzer 25, LED 2
  const uint8_t PIN_BOMBA_AMARELO  = 16;
  const uint8_t PIN_BOMBA_VERMELHO = 17;
  const uint8_t PIN_BOMBA_VERDE    = 18;
  const uint8_t PIN_BOMBA_AZUL     = 19;
  const uint8_t PIN_BUZZER         = 25;
  const uint8_t PIN_LED            = 2;
#endif

/* ================= ESTRUTURAS E ESTADO GLOBAL =============================== */
struct PumpChannel {
  const char* key;
  uint8_t pin;
  float flowMlPerSec;
};

PumpChannel pumps[4] = {
  { "amarelo",  PIN_BOMBA_AMARELO,  28.0f },
  { "vermelho", PIN_BOMBA_VERMELHO, 28.0f },
  { "verde",    PIN_BOMBA_VERDE,    28.0f },
  { "azul",     PIN_BOMBA_AZUL,     32.0f }
};

struct PlanStep {
  int pumpIdx;
  float ml;
  unsigned long pourMs;
  unsigned long pauseMs;
};

const int MAX_STEPS = 8;
PlanStep plan[MAX_STEPS];
int planCount = 0;
int currentStep = 0;

enum MachineState {
  STATE_IDLE,
  STATE_DOSING,
  STATE_PAUSING,
  STATE_MELODY,
  STATE_DONE,
  STATE_STOPPED
};

MachineState state = STATE_IDLE;
unsigned long stateStartMs = 0;
unsigned long jobStartMs = 0;
unsigned long totalExpectedMs = 1;
String currentDrinkName = "";
bool startedByCloud = false;

unsigned long lastSerialProgressMs = 0;
unsigned long lastCloudSyncMs = 0;
bool cloudServerReachable = true;

#define NOTE_C4  262
#define NOTE_G3  196
#define NOTE_A3  220
#define NOTE_B3  247
#define NOTE_REST 0

const int MELODY_NOTES[] = { NOTE_C4, NOTE_G3, NOTE_G3, NOTE_A3, NOTE_G3, NOTE_REST, NOTE_B3, NOTE_C4 };
const int MELODY_DIVS[]  = { 4, 8, 8, 4, 4, 4, 4, 4 };
const int MELODY_LEN     = 8;
int melodyIdx = 0;
unsigned long melodyPhaseStart = 0;
unsigned long melodyPhaseMs = 0;
bool melodyGapPhase = false;

WebServerType server(80);
WiFiUDP udpDiscovery;
#if defined(ESP32)
Preferences prefs;
#endif

struct EepromData {
  uint32_t magic;
  float rates[4];
  char savedSsid[48];
  char savedPass[64];
  char savedCloudUrl[128];
};
const uint32_t EEPROM_MAGIC = 0xB473ADE5;

/* ================= CONTROLE DE HARDWARE E PERSISTÊNCIA ====================== */
inline uint8_t nivelLigado()    { return RELAY_ACTIVE_LOW ? LOW  : HIGH; }
inline uint8_t nivelDesligado() { return RELAY_ACTIVE_LOW ? HIGH : LOW;  }

void setPumpState(int idx, bool ligada) {
  if (idx < 0 || idx >= 4) return;
  digitalWrite(pumps[idx].pin, ligada ? nivelLigado() : nivelDesligado());
  digitalWrite(PIN_LED, ligada ? HIGH : LOW);
}

void desligarTodasBombas() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(pumps[i].pin, nivelDesligado());
  }
  digitalWrite(PIN_LED, LOW);
  noTone(PIN_BUZZER);
}

int findPumpIndex(const String& key) {
  for (int i = 0; i < 4; i++) {
    if (key.equalsIgnoreCase(pumps[i].key)) return i;
  }
  return -1;
}

void carregarCalibracao() {
#if defined(ESP8266)
  EEPROM.begin(sizeof(EepromData));
  EepromData data;
  EEPROM.get(0, data);
  if (data.magic == EEPROM_MAGIC) {
    for (int i = 0; i < 4; i++) {
      if (data.rates[i] > 1.0f && data.rates[i] <= 200.0f) {
        pumps[i].flowMlPerSec = data.rates[i];
      }
    }
    data.savedSsid[sizeof(data.savedSsid) - 1] = '\0';
    data.savedPass[sizeof(data.savedPass) - 1] = '\0';
    data.savedCloudUrl[sizeof(data.savedCloudUrl) - 1] = '\0';
    if (strlen(data.savedSsid) > 0) {
      runtimeWifiSsid = String(data.savedSsid);
      runtimeWifiPass = String(data.savedPass);
    }
    if (strlen(data.savedCloudUrl) > 7) {
      runtimeCloudSyncUrl = String(data.savedCloudUrl);
    }
  }
#else
  prefs.begin("bartender", true);
  for (int i = 0; i < 4; i++) {
    pumps[i].flowMlPerSec = prefs.getFloat(pumps[i].key, pumps[i].flowMlPerSec);
  }
  String sSsid = prefs.getString("wifi_ssid", "");
  String sPass = prefs.getString("wifi_pass", "");
  String sCloud = prefs.getString("cloud_url", "");
  if (sSsid.length() > 0) {
    runtimeWifiSsid = sSsid;
    runtimeWifiPass = sPass;
  }
  if (sCloud.length() > 7) {
    runtimeCloudSyncUrl = sCloud;
  }
  prefs.end();
#endif
}

void salvarCalibracao() {
#if defined(ESP8266)
  EepromData data;
  memset(&data, 0, sizeof(EepromData));
  data.magic = EEPROM_MAGIC;
  for (int i = 0; i < 4; i++) {
    data.rates[i] = pumps[i].flowMlPerSec;
  }
  strncpy(data.savedSsid, runtimeWifiSsid.c_str(), sizeof(data.savedSsid) - 1);
  strncpy(data.savedPass, runtimeWifiPass.c_str(), sizeof(data.savedPass) - 1);
  strncpy(data.savedCloudUrl, runtimeCloudSyncUrl.c_str(), sizeof(data.savedCloudUrl) - 1);
  EEPROM.put(0, data);
  EEPROM.commit();
#else
  prefs.begin("bartender", false);
  for (int i = 0; i < 4; i++) {
    prefs.putFloat(pumps[i].key, pumps[i].flowMlPerSec);
  }
  if (runtimeWifiSsid.length() > 0) {
    prefs.putString("wifi_ssid", runtimeWifiSsid);
    prefs.putString("wifi_pass", runtimeWifiPass);
  }
  if (runtimeCloudSyncUrl.length() > 7) {
    prefs.putString("cloud_url", runtimeCloudSyncUrl);
  }
  prefs.end();
#endif
}

/* ================= PARSER DE RECEITAS E PRESETS ============================= */
bool parsePlanString(String planStr) {
  planStr.trim();
  if (planStr.length() == 0) return false;

  planCount = 0;
  totalExpectedMs = 0;

  int start = 0;
  while (start < (int)planStr.length() && planCount < MAX_STEPS) {
    int comma = planStr.indexOf(',', start);
    if (comma == -1) comma = planStr.length();
    String token = planStr.substring(start, comma);
    token.trim();

    int c1 = token.indexOf(':');
    int c2 = token.indexOf(':', c1 + 1);
    if (c1 > 0) {
      String pumpKey = token.substring(0, c1);
      float ml = (c2 > c1) ? token.substring(c1 + 1, c2).toFloat()
                           : token.substring(c1 + 1).toFloat();
      unsigned long pauseMs = (c2 > c1) ? (unsigned long)token.substring(c2 + 1).toInt() : 1000UL;

      int idx = findPumpIndex(pumpKey);
      if (idx >= 0 && ml > 0.0f && ml <= 500.0f) {
        unsigned long pourMs = (unsigned long)((ml / pumps[idx].flowMlPerSec) * 1000.0f);
        if (pourMs < 150) pourMs = 150;
        plan[planCount] = { idx, ml, pourMs, pauseMs };
        totalExpectedMs += (pourMs + pauseMs);
        planCount++;
      }
    }
    start = comma + 1;
  }

  if (totalExpectedMs == 0) totalExpectedMs = 1;
  return planCount > 0;
}

bool carregarPreset(String code) {
  code.trim();
  code.toUpperCase();
  if (code == "1" || code == "GIN_TROPICAL") {
    currentDrinkName = "Gin Tropical";
    return parsePlanString("vermelho:70:1500,amarelo:50:1500,azul:220:0");
  }
  if (code == "2" || code == "GIN_ T" || code == "GIN_TONICA") {
    currentDrinkName = "Gin Tonica";
    return parsePlanString("vermelho:90:2000,azul:220:0");
  }
  if (code == "3" || code == "GIN_M" || code == "SUNSET_CITRUS") {
    currentDrinkName = "Sunset Citrus";
    return parsePlanString("vermelho:60:1500,amarelo:50:1500,verde:40:1500,azul:190:0");
  }
  if (code == "4" || code == "EMERALD_SPRITZ") {
    currentDrinkName = "Emerald Spritz";
    return parsePlanString("vermelho:75:1500,verde:55:1500,azul:210:0");
  }
  if (code == "5" || code == "CITRUS_FIZZ") {
    currentDrinkName = "Citrus Zero Fizz";
    return parsePlanString("amarelo:80:1200,verde:45:1200,azul:225:0");
  }
  return false;
}

void iniciarPlano(bool fromCloud = false) {
  if (planCount <= 0) return;
  desligarTodasBombas();
  startedByCloud = fromCloud;
  currentStep = 0;
  state = STATE_DOSING;
  stateStartMs = millis();
  jobStartMs = stateStartMs;
  lastSerialProgressMs = 0;

  setPumpState(plan[0].pumpIdx, true);
  Serial.printf("START:%s:steps=%d\n", currentDrinkName.c_str(), planCount);
}

void paradaEmergencia() {
  desligarTodasBombas();
  state = STATE_STOPPED;
  startedByCloud = false;
  Serial.println("STOPPED");
}

int calcularProgresso() {
  if (state == STATE_IDLE) return 0;
  if (state == STATE_DONE) return 100;
  if (state == STATE_MELODY) return 98;
  unsigned long elapsed = millis() - jobStartMs;
  int pct = (int)((elapsed * 95UL) / totalExpectedMs);
  if (pct < 3) pct = 3;
  if (pct > 96) pct = 96;
  return pct;
}

const char* stateToString() {
  switch (state) {
    case STATE_IDLE:    return "idle";
    case STATE_DOSING:  return "dispensing";
    case STATE_PAUSING: return "dispensing";
    case STATE_MELODY:  return "dispensing";
    case STATE_DONE:    return "done";
    case STATE_STOPPED: return "stopped";
    default:            return "idle";
  }
}

/* ================= MÁQUINA DE ESTADOS NÃO-BLOQUEANTE ======================== */
void iniciarMelodia() {
  desligarTodasBombas();
  state = STATE_MELODY;
  melodyIdx = 0;
  melodyGapPhase = false;
  melodyPhaseStart = millis();
  melodyPhaseMs = 1000UL / MELODY_DIVS[0];
  if (MELODY_NOTES[0] != NOTE_REST) {
    digitalWrite(PIN_LED, HIGH);
    tone(PIN_BUZZER, MELODY_NOTES[0], melodyPhaseMs);
  }
}

void atualizarMaquinaEstados() {
  unsigned long now = millis();

  if (state == STATE_DOSING) {
    PlanStep& st = plan[currentStep];
    if (now - lastSerialProgressMs >= 400) {
      lastSerialProgressMs = now;
      Serial.printf("PROGRESS:%d:%s\n", calcularProgresso(), pumps[st.pumpIdx].key);
    }
    if (now - stateStartMs >= st.pourMs) {
      setPumpState(st.pumpIdx, false);
      if (st.pauseMs > 0) {
        state = STATE_PAUSING;
        stateStartMs = now;
      } else {
        currentStep++;
        if (currentStep >= planCount) {
          iniciarMelodia();
        } else {
          stateStartMs = now;
          setPumpState(plan[currentStep].pumpIdx, true);
        }
      }
    }
  } else if (state == STATE_PAUSING) {
    PlanStep& st = plan[currentStep];
    if (now - stateStartMs >= st.pauseMs) {
      currentStep++;
      if (currentStep >= planCount) {
        iniciarMelodia();
      } else {
        state = STATE_DOSING;
        stateStartMs = now;
        setPumpState(plan[currentStep].pumpIdx, true);
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

/* ================= PARSER JSON LEVE ========================================= */
String extractJsonString(const String& body, const char* key) {
  String pattern = String("\"") + key + "\"";
  int kPos = body.indexOf(pattern);
  if (kPos < 0) return "";
  int colon = body.indexOf(':', kPos + pattern.length());
  if (colon < 0) return "";
  int q1 = body.indexOf('"', colon + 1);
  if (q1 < 0) return "";
  int q2 = body.indexOf('"', q1 + 1);
  if (q2 < 0) return "";
  return body.substring(q1 + 1, q2);
}

float extractJsonFloat(const String& body, const char* key, float fallback = 0.0f) {
  String pattern = String("\"") + key + "\"";
  int kPos = body.indexOf(pattern);
  if (kPos < 0) return fallback;
  int colon = body.indexOf(':', kPos + pattern.length());
  if (colon < 0) return fallback;
  int start = colon + 1;
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '"')) start++;
  int end = start;
  while (end < (int)body.length() &&
         ((body[end] >= '0' && body[end] <= '9') || body[end] == '.' || body[end] == '-')) {
    end++;
  }
  if (end <= start) return fallback;
  return body.substring(start, end).toFloat();
}

/* ================= SINCRONIZAÇÃO NUVEM IOT (v3) ============================= */
void sincronizarNuvemIoT() {
  if (runtimeCloudSyncUrl.length() == 0 || WiFi.status() != WL_CONNECTED) return;

  // Se estiver preparando um drink iniciado via LAN HTTP (v2/v3) ou USB Serial, não faz polling HTTP externo!
  if ((state == STATE_DOSING || state == STATE_PAUSING || state == STATE_MELODY) && !startedByCloud) {
    return;
  }

  unsigned long now = millis();
  unsigned long interval = (state == STATE_DOSING || state == STATE_PAUSING)
                             ? 450UL
                             : (cloudServerReachable ? 900UL : 8000UL);
  if (now - lastCloudSyncMs < interval) return;

  if (state == STATE_DOSING && currentStep < planCount) {
    unsigned long elapsedStep = now - stateStartMs;
    if (plan[currentStep].pourMs <= elapsedStep + 450UL) {
      return;
    }
  }
  if (state == STATE_MELODY) return;

  lastCloudSyncMs = now;

  String curPump = "";
  if (state == STATE_DOSING && currentStep < planCount) {
    curPump = pumps[plan[currentStep].pumpIdx].key;
  }

  String reqJson = "{";
  reqJson += "\"state\":\"" + String(stateToString()) + "\",";
  reqJson += "\"progress\":" + String(calcularProgresso()) + ",";
  reqJson += "\"current_pump\":\"" + curPump + "\",";
  reqJson += "\"step\":" + String(currentStep + 1) + ",";
  reqJson += "\"total_steps\":" + String(planCount) + ",";
  reqJson += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  reqJson += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  reqJson += "\"device\":\"" + String(DEVICE_MODEL) + "\"";
  reqJson += "}";

  String urlStr = runtimeCloudSyncUrl;
  HTTPClient http;
  http.setTimeout(cloudServerReachable ? 800 : 300);
  int httpCode = -1;
  String respBody = "";

  if (urlStr.startsWith("https://")) {
#if defined(ESP8266)
    BearSSL::WiFiClientSecure secureClient;
    secureClient.setInsecure();
    if (http.begin(secureClient, urlStr)) {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Machine-Token", runtimeApiToken);
      httpCode = http.POST(reqJson);
      if (httpCode == 200) respBody = http.getString();
      http.end();
    }
#else
    WiFiClientSecure secureClient;
    secureClient.setInsecure();
    if (http.begin(secureClient, urlStr)) {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Machine-Token", runtimeApiToken);
      httpCode = http.POST(reqJson);
      if (httpCode == 200) respBody = http.getString();
      http.end();
    }
#endif
  } else {
    WiFiClient plainClient;
    plainClient.setTimeout(cloudServerReachable ? 800 : 300);
    if (http.begin(plainClient, urlStr)) {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Machine-Token", runtimeApiToken);
      httpCode = http.POST(reqJson);
      if (httpCode == 200) respBody = http.getString();
      http.end();
    }
  }

  cloudServerReachable = (httpCode > 0);

  if (httpCode == 200 && state == STATE_DONE) {
    state = STATE_IDLE;
  }

  if (httpCode != 200 || respBody.length() == 0) return;

  String cmd = extractJsonString(respBody, "command");
  if (cmd == "stop") {
    paradaEmergencia();
  } else if (cmd == "dispense" && state != STATE_DOSING && state != STATE_PAUSING) {
    String dName = extractJsonString(respBody, "drink_name");
    String planStr = extractJsonString(respBody, "plan");
    if (planStr.length() > 0 && parsePlanString(planStr)) {
      currentDrinkName = (dName.length() > 0) ? dName : "Drink App";
      iniciarPlano(true);
    }
  } else if (cmd == "update_pumps") {
    bool changed = false;
    for (int i = 0; i < 4; i++) {
      float val = extractJsonFloat(respBody, pumps[i].key, -1.0f);
      if (val > 1.0f && val <= 200.0f) {
        pumps[i].flowMlPerSec = val;
        changed = true;
      }
    }
    if (changed) salvarCalibracao();
  }
}

/* ================= CONEXÃO MULTI-WIFI E AUTODESCOBERTA UDP ================== */
bool tentarConexaoWifi(const char* ssid, const char* pass, unsigned long timeoutMs = 10500) {
  if (!ssid || strlen(ssid) == 0 || String(ssid) == "SEU_WIFI_AQUI" || String(ssid) == "WIFI_DO_BAR_2.4G") {
    return false;
  }
  if (WiFi.status() == WL_CONNECTED && WiFi.SSID() == String(ssid)) {
    return true;
  }
  Serial.printf("Conectando ao Wi-Fi '%s'", ssid);
  WiFi.begin(ssid, pass ? pass : "");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < timeoutMs) {
    delay(200);
    Serial.print(".");
  }
  Serial.println();
  return WiFi.status() == WL_CONNECTED;
}

void conectarRede() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID, AP_PASSWORD);

  bool conectado = false;
  bool tentouAlgumaVisivel = false;

  int n = WiFi.scanNetworks();
  if (n > 0) {
    if (runtimeWifiSsid.length() > 0) {
      for (int i = 0; i < n; i++) {
        if (WiFi.SSID(i) == runtimeWifiSsid) {
          tentouAlgumaVisivel = true;
          conectado = tentarConexaoWifi(runtimeWifiSsid.c_str(), runtimeWifiPass.c_str(), 10500);
          break;
        }
      }
    }

    if (!conectado) {
      for (int i = 0; i < n && !conectado; i++) {
        String foundSsid = WiFi.SSID(i);
        for (int k = 0; k < KNOWN_NETWORKS_COUNT; k++) {
          if (strlen(KNOWN_NETWORKS[k].ssid) > 0 && foundSsid == String(KNOWN_NETWORKS[k].ssid)) {
            tentouAlgumaVisivel = true;
            conectado = tentarConexaoWifi(KNOWN_NETWORKS[k].ssid, KNOWN_NETWORKS[k].pass, 10500);
            if (conectado) break;
          }
        }
      }
    }
  }

  if (!conectado && !tentouAlgumaVisivel && runtimeWifiSsid.length() > 0) {
    conectado = tentarConexaoWifi(runtimeWifiSsid.c_str(), runtimeWifiPass.c_str(), 9000);
  }
  if (!conectado && !tentouAlgumaVisivel && strlen(WIFI_SSID) > 0) {
    conectado = tentarConexaoWifi(WIFI_SSID, WIFI_PASSWORD, 9000);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi conectado em '%s'! IP: %s\n",
                  WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
  } else {
    Serial.printf("Modo Access Point ativo: '%s' | IP: %s (Portal Web em http://192.168.4.1)\n",
                  AP_SSID, WiFi.softAPIP().toString().c_str());
  }

  if (MDNS.begin(MDNS_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    Serial.printf("mDNS ativo: http://%s.local\n", MDNS_HOSTNAME);
  }

  udpDiscovery.begin(UDP_DISCOVERY_PORT);
}

void processarDescobertaUdp() {
  int packetSize = udpDiscovery.parsePacket();
  if (packetSize <= 0) return;

  char buf[384];
  int len = udpDiscovery.read(buf, sizeof(buf) - 1);
  if (len <= 0) return;
  buf[len] = '\0';

  String msg = String(buf);
  msg.trim();
  if (!msg.startsWith("BARTENDER_DISCOVER")) return;

  int p1 = msg.indexOf('|');
  if (p1 > 0) {
    int p2 = msg.indexOf('|', p1 + 1);
    String newSyncUrl = (p2 > p1) ? msg.substring(p1 + 1, p2) : msg.substring(p1 + 1);
    String newToken   = (p2 > p1) ? msg.substring(p2 + 1) : "";
    newSyncUrl.trim();
    newToken.trim();
    bool changed = false;
    if (newSyncUrl.startsWith("http") && newSyncUrl != runtimeCloudSyncUrl) {
      runtimeCloudSyncUrl = newSyncUrl;
      changed = true;
    }
    if (newToken.length() > 0 && newToken != runtimeApiToken) {
      runtimeApiToken = newToken;
      changed = true;
    }
    cloudServerReachable = true;
    if (changed) {
      salvarCalibracao();
      Serial.printf("Cloud Sync URL sincronizada via UDP: %s\n", runtimeCloudSyncUrl.c_str());
    }
  }

  String ipStr = (WiFi.status() == WL_CONNECTED)
                   ? WiFi.localIP().toString()
                   : WiFi.softAPIP().toString();
  int rssi = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;

  String reply = "{";
  reply += "\"ok\":true,";
  reply += "\"service\":\"bartender-esp\",";
  reply += "\"version\":\"3.0\",";
  reply += "\"device\":\"" + String(DEVICE_MODEL) + "\",";
  reply += "\"ip\":\"" + ipStr + "\",";
  reply += "\"port\":80,";
  reply += "\"ssid\":\"" + (WiFi.status() == WL_CONNECTED ? WiFi.SSID() : String(AP_SSID)) + "\",";
  reply += "\"rssi\":" + String(rssi);
  reply += "}";

  udpDiscovery.beginPacket(udpDiscovery.remoteIP(), udpDiscovery.remotePort());
  udpDiscovery.write((const uint8_t*)reply.c_str(), reply.length());
  udpDiscovery.endPacket();
}

/* ================= ROTAS HTTP (WI-FI JSON API LOCAL v2 & v3) ================ */
void sendCorsHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type, X-Bartender-Token");
}

bool verificarTokenHttp() {
  // Permite controle fluido na LAN tanto pela v2 (sem token) quanto pela v3 (com token)
  String sent = server.header("X-Bartender-Token");
  if (sent.length() == 0 || runtimeApiToken.length() == 0) return true;
  if (sent == runtimeApiToken) return true;
  server.send(401, "application/json", "{\"ok\":false,\"error\":\"Token invalido\"}");
  return false;
}

void handleOptions() {
  sendCorsHeaders();
  server.send(204);
}

void handleRootPortal() {
  sendCorsHeaders();
  String ipStr = (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
  String ssidStr = (WiFi.status() == WL_CONNECTED) ? WiFi.SSID() : String("AP: ") + AP_SSID;
  String html = "<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>";
  html += "<title>Bartender.OS · Config Wi-Fi</title>";
  html += "<style>body{font-family:sans-serif;background:#fffaf3;color:#2d1810;padding:20px;max-width:460px;margin:auto}";
  html += ".card{background:#fff;border:1px solid #ead0b2;border-radius:16px;padding:18px;margin-bottom:16px}";
  html += "input,button{width:100%;padding:10px;margin-top:8px;border-radius:10px;border:1px solid #d6b48c;box-sizing:border-box}";
  html += "button{background:#ea580c;color:#fff;border:none;font-weight:bold;cursor:pointer}</style></head><body>";
  html += "<h2>🍹 Bartender.OS v2 + v3 (" + String(DEVICE_MODEL) + ")</h2>";
  html += "<div class='card'><b>Rede Atual:</b> " + ssidStr + "<br><b>IP:</b> " + ipStr + "<br><b>Cloud Sync:</b> " + runtimeCloudSyncUrl + "</div>";
  html += "<div class='card'><h3>Conectar a Novo Wi-Fi 2.4 GHz</h3>";
  html += "<input id='s' placeholder='Nome do Wi-Fi (SSID)' value='" + runtimeWifiSsid + "'>";
  html += "<input id='p' type='password' placeholder='Senha do Wi-Fi'>";
  html += "<input id='c' placeholder='URL Cloud Sync (opcional)' value='" + runtimeCloudSyncUrl + "'>";
  html += "<button onclick=\"fetch('/config/wifi',{method:'POST',body:JSON.stringify({ssid:document.getElementById('s').value,password:document.getElementById('p').value,cloud_sync_url:document.getElementById('c').value})}).then(r=>r.json()).then(d=>alert('IP: '+(d.ip||'Conectando...')))\">Salvar e Conectar</button></div>";
  html += "</body></html>";
  server.send(200, "text/html", html);
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
  String ssidStr = (WiFi.status() == WL_CONNECTED) ? WiFi.SSID() : String(AP_SSID);

  String json = "{";
  json += "\"ok\":true,";
  json += "\"service\":\"bartender-esp\",";
  json += "\"device\":\"" + String(DEVICE_MODEL) + "\",";
  json += "\"state\":\"" + String(stateToString()) + "\",";
  json += "\"drink_name\":\"" + currentDrinkName + "\",";
  json += "\"progress\":" + String(calcularProgresso()) + ",";
  json += "\"current_pump\":\"" + curPump + "\",";
  json += "\"step_index\":" + String(currentStep + 1) + ",";
  json += "\"total_steps\":" + String(planCount) + ",";
  json += "\"ip\":\"" + ipStr + "\",";
  json += "\"ssid\":\"" + ssidStr + "\",";
  json += "\"rssi\":" + String(rssi) + ",";
  json += "\"cloud_sync_url\":\"" + runtimeCloudSyncUrl + "\",";
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

  iniciarPlano(false);
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

void handleConfigCloud() {
  sendCorsHeaders();
  String body = server.arg("plain");
  String newUrl = extractJsonString(body, "cloud_sync_url");
  String newTok = extractJsonString(body, "api_token");
  newUrl.trim();
  newTok.trim();
  if (newUrl.startsWith("http")) {
    runtimeCloudSyncUrl = newUrl;
  }
  if (newTok.length() > 0) {
    runtimeApiToken = newTok;
  }
  cloudServerReachable = true;
  salvarCalibracao();
  handleStatus();
}

void handleConfigWifi() {
  sendCorsHeaders();
  String body = server.arg("plain");
  String newSsid = extractJsonString(body, "ssid");
  String newPass = extractJsonString(body, "password");
  String newCloud = extractJsonString(body, "cloud_sync_url");
  String newTok = extractJsonString(body, "api_token");
  newSsid.trim();
  newCloud.trim();
  newTok.trim();
  if (newCloud.startsWith("http")) runtimeCloudSyncUrl = newCloud;
  if (newTok.length() > 0) runtimeApiToken = newTok;
  if (newSsid.length() > 0) {
    runtimeWifiSsid = newSsid;
    runtimeWifiPass = newPass;
    salvarCalibracao();
    tentarConexaoWifi(runtimeWifiSsid.c_str(), runtimeWifiPass.c_str(), 10500);
  }
  handleStatus();
}

/* ================= COMANDOS VIA USB SERIAL ================================== */
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
  if (cmd.equalsIgnoreCase("NETINFO")) {
    String ipStr = (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
    String ssidStr = (WiFi.status() == WL_CONNECTED) ? WiFi.SSID() : String(AP_SSID);
    Serial.printf("NETINFO:{\"ok\":true,\"ip\":\"%s\",\"ssid\":\"%s\",\"connected\":%s}\n",
                  ipStr.c_str(), ssidStr.c_str(), (WiFi.status() == WL_CONNECTED ? "true" : "false"));
    return;
  }
  if (cmd.startsWith("CLOUD:")) {
    String newUrl = cmd.substring(6);
    newUrl.trim();
    if (newUrl.startsWith("http")) {
      runtimeCloudSyncUrl = newUrl;
      cloudServerReachable = true;
      salvarCalibracao();
      Serial.println("CLOUD_OK:" + runtimeCloudSyncUrl);
    }
    return;
  }
  if (cmd.startsWith("WIFI:")) {
    String rest = cmd.substring(5);
    int tab = rest.indexOf('\t');
    if (tab > 0) {
      runtimeWifiSsid = rest.substring(0, tab);
      runtimeWifiPass = rest.substring(tab + 1);
    } else {
      runtimeWifiSsid = rest;
      runtimeWifiPass = "";
    }
    runtimeWifiSsid.trim();
    if (runtimeWifiSsid.length() > 0) {
      salvarCalibracao();
      tentarConexaoWifi(runtimeWifiSsid.c_str(), runtimeWifiPass.c_str(), 7000);
      String ipStr = (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
      Serial.printf("WIFI_OK:%s\n", ipStr.c_str());
    }
    return;
  }

  if (state == STATE_DOSING || state == STATE_PAUSING || state == STATE_MELODY) {
    Serial.println("BUSY");
    return;
  }

  if (cmd.startsWith("PLAN:")) {
    currentDrinkName = "Drink Serial";
    if (parsePlanString(cmd.substring(5))) {
      iniciarPlano(false);
    } else {
      Serial.println("CMD_ERR");
    }
  } else if (carregarPreset(cmd)) {
    iniciarPlano(false);
  } else {
    Serial.println("CMD_ERR");
  }
}

/* ================= INICIALIZAÇÃO E LOOP PRINCIPAL =========================== */
void setup() {
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
  Serial.printf("\n=== Bartender.OS Unificado v2 + v3 (%s) ===\n", DEVICE_MODEL);

  carregarCalibracao();
  conectarRede();

  server.on("/", HTTP_GET, handleRootPortal);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/status", HTTP_OPTIONS, handleOptions);
  server.on("/dispense", HTTP_POST, handleDispense);
  server.on("/dispense", HTTP_OPTIONS, handleOptions);
  server.on("/stop", HTTP_POST, handleStop);
  server.on("/stop", HTTP_OPTIONS, handleOptions);
  server.on("/config/pumps", HTTP_POST, handleConfigPumps);
  server.on("/config/pumps", HTTP_OPTIONS, handleOptions);
  server.on("/config/cloud", HTTP_POST, handleConfigCloud);
  server.on("/config/cloud", HTTP_OPTIONS, handleOptions);
  server.on("/config/wifi", HTTP_POST, handleConfigWifi);
  server.on("/config/wifi", HTTP_OPTIONS, handleOptions);

#if defined(ESP8266)
  server.collectHeaders("X-Bartender-Token");
#else
  const char* headerKeys[] = { "X-Bartender-Token" };
  server.collectHeaders(headerKeys, 1);
#endif

  server.begin();
  ArduinoOTA.setHostname(MDNS_HOSTNAME);
  ArduinoOTA.onStart([]() { desligarTodasBombas(); });
  ArduinoOTA.begin();
  Serial.println("HTTP (80) + Descoberta UDP (4210) + ArduinoOTA (Wi-Fi Upload) prontos!");
}

void loop() {
#if defined(ESP8266)
  MDNS.update();
#endif
  ArduinoOTA.handle();
  processarDescobertaUdp();
  server.handleClient();
  processarSerial();
  atualizarMaquinaEstados();
  sincronizarNuvemIoT();

  // Reconexão automática caso o roteador/Hotspot seja ligado depois do ESP
  if (WiFi.status() != WL_CONNECTED && state != STATE_DOSING && state != STATE_PAUSING && state != STATE_MELODY) {
    static unsigned long lastWifiRetryMs = 0;
    if (millis() - lastWifiRetryMs >= 25000UL) {
      lastWifiRetryMs = millis();
      int n = WiFi.scanNetworks();
      bool ok = false;
      if (n > 0 && runtimeWifiSsid.length() > 0) {
        for (int i = 0; i < n && !ok; i++) {
          if (WiFi.SSID(i) == runtimeWifiSsid) {
            ok = tentarConexaoWifi(runtimeWifiSsid.c_str(), runtimeWifiPass.c_str(), 10500);
          }
        }
      }
      for (int i = 0; i < n && !ok; i++) {
        String foundSsid = WiFi.SSID(i);
        for (int k = 0; k < KNOWN_NETWORKS_COUNT && !ok; k++) {
          if (strlen(KNOWN_NETWORKS[k].ssid) > 0 && foundSsid == String(KNOWN_NETWORKS[k].ssid)) {
            ok = tentarConexaoWifi(KNOWN_NETWORKS[k].ssid, KNOWN_NETWORKS[k].pass, 10500);
          }
        }
      }
      if (ok) MDNS.begin(MDNS_HOSTNAME);
    }
  }
}
