#pragma once

/*
 * ============================================================================
 * MODELO DE CREDENCIAIS DO ESP8266 / ESP32 — BARTENDER.OS v3.0 COMERCIAL
 * ============================================================================
 * Como usar:
 *   1. Copie este arquivo para "bombas/secrets.h" (já ignorado pelo .gitignore)
 *   2. Preencha o Wi-Fi 2.4 GHz do Bar
 *   3. Para operar sem PC no bar (Cliente pede no 4G -> Nuvem -> Wi-Fi do Bar),
 *      preencha SECRET_CLOUD_SYNC_URL e SECRET_API_TOKEN gerados no Painel do Bar!
 * ============================================================================
 */

// Wi-Fi 2.4 GHz local do Bar
#define SECRET_WIFI_SSID       "WIFI_DO_BAR_2.4G"
#define SECRET_WIFI_PASSWORD   "SENHA_WIFI_DO_BAR"

// Rede Wi-Fi de emergência caso não encontre o roteador
#define SECRET_AP_SSID         "Bartender-Config"
#define SECRET_AP_PASSWORD     "12345678"

// Token IoT da Máquina (copie do Painel do Dono do Bar -> Aba Máquinas)
#define SECRET_API_TOKEN       ""

// URL completa de Sincronização IoT na Nuvem (ex.: "https://seu-saas.com/api/iot/maq-01/sync"
// ou em testes na rede local: "http://192.168.1.10:8010/api/iot/maq-01/sync").
// Deixe "" para operar apenas em modo passivo LAN/USB.
#define SECRET_CLOUD_SYNC_URL  ""
