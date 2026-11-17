#pragma once

/*
 * ============================================================================
 * MODELO DE CREDENCIAIS DO ESP32 (VERSIONADO NO GIT)
 * ============================================================================
 * Papel na Arquitetura de Segurança:
 *   Isola as credenciais de rede Wi-Fi e o token de autenticação HTTP fora do
 *   código-fonte principal (`bombas.ino`), impedindo vazamento acidental de
 *   senhas de clientes ou roteadores corporativos em repositórios públicos.
 *
 * Como usar:
 *   1. Copie este arquivo para "bombas/secrets.h" (já ignorado pelo .gitignore)
 *   2. Preencha abaixo o nome e a senha do seu Wi-Fi 2.4 GHz
 *   3. Nunca coloque senhas reais neste arquivo .example!
 * ============================================================================
 */

// Credenciais da sua rede Wi-Fi 2.4 GHz
// Importante: Rádios ESP32-WROOM-32 e ESP8266 operam exclusivamente em 2.4 GHz (802.11 b/g/n).
#define SECRET_WIFI_SSID      "NOME_DO_SEU_WIFI_2.4G"
#define SECRET_WIFI_PASSWORD  "SENHA_DO_SEU_WIFI"

// Rede Wi-Fi própria criada pelo ESP32 caso não encontre o roteador (mín. 8 caracteres)
// No modo SoftAP o ESP32 assume o IP fixo `192.168.4.1` — ideal para eventos e feiras sem infraestrutura!
#define SECRET_AP_SSID        "Bartender-ESP32"
#define SECRET_AP_PASSWORD    "troque-esta-senha"

// Token opcional para proteger comandos HTTP no Wi-Fi (deixe "" para desativar,
// ou coloque o mesmo valor de ESP32_API_TOKEN no arquivo .env do servidor)
// Quando preenchido, exige o header `X-Bartender-Token` em `/dispense`, `/stop` e `/config/pumps`.
#define SECRET_API_TOKEN      ""
