# 💾 Persistência Local de Dados (`backend/data/`)

Diretório de armazenamento persistente ultraleve em formato **JSON UTF-8 legível por humanos** para as configurações operacionais e calibrações hidráulicas do **Bartender.OS v2.0**.

---

## 💼 Por Que JSON Local em Vez de um Banco de Dados Tradicional? (Argumento Técnico-Comercial)

Para equipamentos embarcados de eventos e quiosques autônomos (*totens*), substituir um SGBD pesado (MySQL/PostgreSQL) por arquivos JSON validados com **Pydantic v2** entrega vantagens decisivas de engenharia e pós-venda:

1. **Zero Manutenção e Zero Corrupção de Serviço:**
   Quedas abruptas de energia em geradores de festas costumam corromper tabelas de bancos de dados relacionais ou impedir que serviços Windows inicializem. Aqui, a leitura é instantânea e **auto-regenerativa (*auto-healing*)**: se um arquivo for apagado ou editado incorretamente, o sistema restaura automaticamente os padrões seguros de fábrica (`DEFAULT_PUMPS` / `.env`) sem travar a máquina.
2. **Backup e Clonagem de Máquinas em 2 Segundos:**
   Para replicar exatamente a mesma carta de garrafas e calibração de uma máquina matriz para 5 novas máquinas alugadas para um festival, basta copiar os 2 arquivos JSON desta pasta (`< 2 KB` no total).
3. **Auditoria Transparente em Campo:**
   Qualquer técnico pode abrir `pumps.json` ou `connection.json` no Bloco de Notas para conferir qual porta `COM`, endereço IP ou vazão (`ml/s`) está gravada.

---

## 📄 Arquivos Armazenados Nesta Pasta

### 1. `connection.json`
Guarda a preferência de comunicação selecionada pelo operador na gaveta **⚙️ Conexão ESP32 & Bebidas** (`PUT /api/connection`):

```json
{
  "mode": "auto",
  "esp32_host": "bartender.local",
  "esp32_port": 80,
  "serial_port": "COM3",
  "serial_baud": 115200
}
```

- **`mode`**: `"auto"` (fallback triplo inteligente), `"wifi"`, `"serial"` ou `"simulator"`.
- **`esp32_host` / `esp32_port`**: Endereço mDNS ou IP estático do ESP32 na rede local.
- **`serial_port` / `serial_baud`**: Porta serial e velocidade para operação cabeada via USB.

> 🔒 **Segurança:** Repare que nenhum token ou senha de Wi-Fi é gravado em `connection.json`. Segredos permanecem estritamente isolados em `projetobartender/.env` e `bombas/secrets.h`.

---

### 2. `pumps.json`
Guarda o inventário líquido atual das 4 bombas e a vazão real calibrada (`flow_rate_ml_s`) de cada mangueira (`PUT /api/pumps/{pump_id}`):

```json
{
  "amarelo": {
    "id": "amarelo",
    "label": "Bomba 1 · Amarela",
    "ingredient": "Citrus / Maracujá",
    "description": "Xarope cítrico aromático de limão siciliano e maracujá",
    "gpio": 16,
    "flow_rate_ml_s": 30.5,
    "color_hex": "#f59e0b",
    "is_mixer": false
  }
}
```

- Sempre que `flow_rate_ml_s` é atualizado via interface web, o backend salva o novo valor neste arquivo **e também sincroniza automaticamente com a memória Flash NVS do ESP32** (`POST /config/pumps`), mantendo software e hardware 100% alinhados.
- Caso deseje **resetar todas as bombas para o padrão de fábrica**, basta parar o servidor, excluir `pumps.json` e iniciar novamente.
