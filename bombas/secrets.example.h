#pragma once

/*
 * ============================================================================
 * MODELO DE CREDENCIAIS DO ESP32 (VERSIONADO NO GIT)
 * ============================================================================
 * Como usar:
 *   1. Copie este arquivo para "bombas/secrets.h" (já ignorado pelo .gitignore)
 *   2. Preencha abaixo o nome e a senha do seu Wi-Fi 2.4 GHz
 *   3. Nunca coloque senhas reais neste arquivo .example!
 * ============================================================================
 */

// Credenciais da sua rede Wi-Fi 2.4 GHz
#define SECRET_WIFI_SSID      "NOME_DO_SEU_WIFI_2.4G"
#define SECRET_WIFI_PASSWORD  "SENHA_DO_SEU_WIFI"

// Rede Wi-Fi própria criada pelo ESP32 caso não encontre o roteador (mín. 8 caracteres)
#define SECRET_AP_SSID        "Bartender-ESP32"
#define SECRET_AP_PASSWORD    "troque-esta-senha"

// Token opcional para proteger comandos HTTP no Wi-Fi (deixe "" para desativar,
// ou coloque o mesmo valor de ESP32_API_TOKEN no arquivo .env do servidor)
#define SECRET_API_TOKEN      ""

