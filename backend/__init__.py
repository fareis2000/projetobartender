"""Pacote principal da API FastAPI do Bartender Automático.

Função Arquitetural (Bartender.OS v3.0 SaaS):
---------------------------------------------
Agrupa toda a infraestrutura de servidor da plataforma comercial Multi-Bares (`backend.app`
e `backend.tests`), fornecendo isolamento multi-tenant por `bar_id`, motor financeiro de
cobrança e split Pix (Mercado Pago Oficial + EMV BRCode Simulado), precificação dinâmica
em centavos por mililitro (`R$/ml`), fila virtual inteligente com confirmação obrigatória
de copo na plataforma e sincronização Cloud IoT para controladores ESP8266/ESP32.
"""
