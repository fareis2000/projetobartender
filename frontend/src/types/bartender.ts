/**
 * @file src/types/bartender.ts
 * @description Contratos de dados e tipagem estrita TypeScript de ponta a ponta do Bartender.OS v3.0.
 *
 * Papel na Engenharia Frontend & Modelo de Negócios SaaS:
 * - Espelha com fidelidade 1:1 os schemas Pydantic do backend FastAPI, garantindo segurança em tempo
 *   de compilação (`tsc -b` com `strict: true`) em toda a jornada: do clique no cardápio até o IoT.
 * - Modela a precificação fracionada ao mililitro (`Bottle`, `PumpSlot`, `DrinkRecipe`), a máquina de
 *   estados completa do autosserviço via Pix com trava anti-desperdício de copo (`OrderStatus`),
 *   a telemetria híbrida de hardware ESP8266/ESP32 (`HardwareHealth`, `MachineRealtimeSnapshot`)
 *   e a governança financeira multi-tenant com Split da plataforma (`BarAnalytics`, `PlatformOverview`).
 */

/** Identificadores canônicos das 4 linhas/bombas peristálticas de cada máquina Bartender.OS. */
export type PumpId = 'amarelo' | 'vermelho' | 'verde' | 'azul';

/** Modos de transporte suportados entre o servidor Bartender.OS e a controladora física ESP8266/ESP32. */
export type ConnectionMode = 'cloud_iot' | 'auto' | 'wifi' | 'serial' | 'simulator';

/** Estados operacionais imediatos do subsistema físico de preparo/dosagem da máquina. */
export type PrepState = 'idle' | 'dispensing' | 'completed' | 'stopped' | 'error';

/** Provedor de liquidação Pix configurado para o bar (`simulated` p/ demos comerciais ou `mercadopago` oficial). */
export type PaymentProvider = 'simulated' | 'mercadopago';

/** Estratégia comercial de precificação de uma receita no cardápio: soma dinâmica dos ml ou valor fixo. */
export type DrinkPricingMode = 'auto_ml' | 'fixed';

/**
 * Ciclo de vida transacional completo de um pedido no autoatendimento:
 * - `PENDING_PAYMENT`: Cobrança Pix gerada aguardando liquidação no banco.
 * - `PAID_QUEUED`: Pix confirmado, aguardando pedidos anteriores terminarem na máquina.
 * - `READY_FOR_CUP`: Vez do cliente liberada na máquina; exige confirmação explícita do copo na base.
 * - `PAUSED_TURN`: Cliente demorou a posicionar o copo; fila avança sem perder o crédito já pago.
 * - `DISPENSING`: Bombas acionadas despejando os mililitros em tempo real.
 * - `COMPLETED`: Drink 100% entregue com baixa automática de estoque.
 * - `FAILED_DISPENSE`: Interrupção física/emergência; elegível para reenvio à fila ou estorno Pix.
 * - `EXPIRED` | `CANCELED` | `REFUNDED`: Estados terminais administrativos/financeiros.
 */
export type OrderStatus =
  | 'PENDING_PAYMENT'
  | 'PAID_QUEUED'
  | 'READY_FOR_CUP'
  | 'PAUSED_TURN'
  | 'DISPENSING'
  | 'COMPLETED'
  | 'FAILED_DISPENSE'
  | 'EXPIRED'
  | 'CANCELED'
  | 'REFUNDED';

/**
 * Usuário autenticado nos painéis de gestão (`bar_owner` para Dono do Bar ou `superadmin` para Plataforma).
 */
export interface PrincipalUser {
  /** ID único (subject) do usuário no banco de dados. */
  sub: string;
  /** E-mail corporativo utilizado no login. */
  email: string;
  /** Papel de controle de acesso baseado em função (RBAC). */
  role: 'superadmin' | 'bar_owner';
  /** ID do bar vinculado (`null` para contas globais Super-Admin). */
  bar_id: string | null;
  /** Nome fantasia do bar vinculado, quando aplicável. */
  bar_name: string | null;
}

/**
 * Resposta do endpoint `/api/auth/login` contendo o token JWT e metadados do operador logado.
 */
export interface AuthTokenResponse {
  /** Token JWT assinado para envio no header `Authorization: Bearer ...`. */
  access_token: string;
  /** Esquema do token (ex.: `"bearer"`). */
  token_type: string;
  /** Dados de perfil e permissão do usuário autenticado. */
  user: PrincipalUser;
}

/**
 * Entidade de Garrafa/Insumo cadastrada no estoque do bar com engenharia financeira por mililitro.
 */
export interface Bottle {
  /** Identificador único da garrafa no tenant do bar. */
  id: string;
  /** Identificador do bar proprietário deste insumo. */
  bar_id: string;
  /** Nome comercial exibido ao cliente e ao operador (ex.: `"Gin Tanqueray 750ml"`). */
  name: string;
  /** Descrição sensorial curta exibida no cardápio/construtor. */
  description: string;
  /** Cor hexadecimal usada para renderizar a camada líquida realista no copo SVG. */
  color_hex: string;
  /** Indica teor alcoólico para exibição automática do selo legal `+18`. */
  is_alcoholic: boolean;
  /** Indica se é um insumo não-alcoólico/base (tônica, refrigerante, suco) para sugestão inteligente de doses. */
  is_mixer: boolean;
  /** Volume nominal da garrafa lacrada em mililitros (ex.: `750`, `1000`, `2000`). */
  bottle_volume_ml: number;
  /** Volume útil comercializável em ml após descontar `loss_pct` (purga/mangueira). */
  usable_volume_ml: number;
  /** Custo de aquisição pago pelo bar na garrafa fechada, em centavos. */
  cost_cents: number;
  /** Percentual técnico estimado de perda operacional/mangueira (`0` a `30%`). */
  loss_pct: number;
  /** Preço de venda padronizado de 1 litro (1000 ml) em centavos, base para todo cálculo fracionado. */
  price_per_liter_cents: number;
  /** Valor informativo em centavos por 1 ml em ponto flutuante. */
  price_per_ml_cents_float: number;
  /** Valor de venda calculado para uma dose padrão de 50 ml, em centavos. */
  dose_50ml_cents: number;
  /** Faturamento bruto projetado ao esgotar o volume útil da garrafa, em centavos. */
  estimated_bottle_revenue_cents: number;
  /** Lucro bruto projetado por garrafa (`receita estimada - custo`), em centavos. */
  estimated_bottle_profit_cents: number;
  /** Quantidade de bombas físicas que estão utilizando esta garrafa neste exato momento. */
  installed_in_pumps: number;
  /** Data/hora ISO 8601 de criação do registro. */
  created_at: string;
}

/**
 * Payload enviado pelo Dono do Bar para cadastrar ou atualizar uma garrafa no CRUD de estoque.
 */
export interface BottlePayload {
  /** Nome comercial da garrafa ou ingrediente. */
  name: string;
  /** Descrição complementar visível para o consumidor. */
  description: string;
  /** Cor hexadecimal da camada líquida no preview visual. */
  color_hex: string;
  /** Flag de bebida alcoólica (+18). */
  is_alcoholic: boolean;
  /** Flag de base/mixer para preenchimento rápido no construtor por ml. */
  is_mixer: boolean;
  /** Volume total da embalagem fechada em ml. */
  bottle_volume_ml: number;
  /** Custo de compra da garrafa em centavos. */
  cost_cents: number;
  /** Percentual de perda técnica em mangueira/escorva. */
  loss_pct: number;
  /** Preço de venda configurado por litro (1000 ml) em centavos. */
  price_per_liter_cents: number;
}

/**
 * Estado consolidado de uma das 4 bombas físicas da máquina, unindo calibração de hardware
 * (GPIO, vazão ml/s, volume restante) aos dados comerciais da garrafa nela conectada.
 */
export interface PumpSlot {
  /** Identificador cromático da bomba (`amarelo`, `vermelho`, `verde` ou `azul`). */
  pump_id: PumpId;
  /** Rótulo amigável da bomba exibido no painel técnico. */
  label: string;
  /** Pino GPIO correspondente no microcontrolador ESP8266/ESP32. */
  gpio: number;
  /** Vazão calibrada em mililitros por segundo (`ml/s`) para conversão precisa de volume em tempo de relé. */
  flow_rate_ml_s: number;
  /** Volume físico estimado restante dentro da garrafa atual, em ml. */
  remaining_ml: number;
  /** Reserva mínima de segurança em ml abaixo da qual a bomba bloqueia novas vendas para não puxar ar. */
  min_reserve_ml: number;
  /** Volume efetivamente disponível para venda imediata (`remaining_ml - min_reserve_ml`). */
  available_ml: number;
  /** ID da garrafa atualmente espetada nesta mangueira (`null` se desvinculada). */
  bottle_id: string | null;
  /** Nome do ingrediente derivado da garrafa instalada. */
  ingredient: string;
  /** Descrição sensorial herdada da garrafa instalada. */
  description: string;
  /** Cor hexadecimal da bebida instalada para renderização em `GlassArtwork` e barras de progresso. */
  color_hex: string;
  /** Indica se o líquido instalado nesta bomba é alcoólico (+18). */
  is_alcoholic: boolean;
  /** Indica se o líquido instalado atua como mixer/diluente. */
  is_mixer: boolean;
  /** Capacidade nominal total da garrafa instalada, usada no cálculo percentual da barra de nível. */
  bottle_volume_ml: number;
  /** Preço de venda por litro (em centavos) do insumo atualmente instalado. */
  price_per_liter_cents: number;
  /** Preço de referência para cada fração de 10 ml em centavos. */
  price_per_10ml_cents: number;
}

/**
 * Etapa individual de dosagem na receita de um coquetel (qual bomba acionar, quantos ml e pausa pós-jato).
 */
export interface DoseStep {
  /** Bomba física que será acionada nesta etapa. */
  pump: PumpId;
  /** Volume exato em mililitros a ser despejado. */
  ml: number;
  /** Pausa em milissegundos após esta etapa (estabilização de espuma/camadas de densidade). */
  pause_ms: number;
}

/**
 * Receita completa de Drink enriquecida pelo backend com disponibilidade em tempo real,
 * custo de CMV, margem de lucro por copo e preço final ao consumidor.
 */
export interface DrinkRecipe {
  /** Identificador único da receita. */
  id: string;
  /** Bar proprietário desta receita. */
  bar_id: string;
  /** Título comercial de destaque no cardápio. */
  name: string;
  /** Subtítulo rápido com notas ou ingredientes-chave. */
  subtitle: string;
  /** Texto descritivo persuasivo exibido no card do drink. */
  description: string;
  /** Categoria de filtragem no cardápio (ex.: `"Clássicos da Casa"`, `"Sem Álcool"`). */
  category: string;
  /** Selo promocional no topo esquerdo do card (ex.: `"Mais Pedido"`, `"Especial"`). */
  badge: string;
  /** Cor inicial do gradiente temático do card e botão de compra. */
  accent_from: string;
  /** Cor final do gradiente temático do card e botão de compra. */
  accent_to: string;
  /** Cor de fallback para o líquido no copo caso uma bomba esteja sem garrafa vinculada. */
  glass_color: string;
  /** Modo de cálculo do preço (`auto_ml` soma os ml das bombas; `fixed` usa valor tabelado). */
  pricing_mode: DrinkPricingMode;
  /** Preço tabelado em centavos quando `pricing_mode === 'fixed'`. */
  fixed_price_cents: number;
  /** Percentual de desconto promocional sobre a soma avulsa dos ml quando `pricing_mode === 'auto_ml'`. */
  discount_pct: number;
  /** Define se o drink está visível/ativo no cardápio público dos clientes. */
  active: boolean;
  /** Sequência ordenada de acionamento das bombas para compor a bebida. */
  steps: DoseStep[];
  /** Soma total em mililitros de todas as etapas da receita. */
  total_ml: number;
  /** Tempo total estimado de preparo em segundos com base na vazão atual das bombas. */
  estimated_seconds: number;
  /** Preço bruto somando os ml avulsos + taxa de copo antes de descontos, em centavos. */
  raw_ml_price_cents: number;
  /** Preço final cobrado no Pix do cliente, em centavos. */
  final_price_cents: number;
  /** Custo de Mercadoria Vendida (CMV) estimado dos insumos consumidos em 1 copo, em centavos. */
  estimated_cost_cents: number;
  /** Lucro bruto estimado por copo vendido (`final_price_cents - estimated_cost_cents`), em centavos. */
  estimated_profit_cents: number;
  /** Indica automaticamente se qualquer etapa utiliza garrafa alcoólica (+18). */
  is_alcoholic: boolean;
  /** Indica se há estoque suficiente em todas as bombas exigidas para preparar o drink agora. */
  available: boolean;
  /** Motivo legível caso o drink esteja temporariamente indisponível (ex.: garrafa em fim de curso). */
  unavailable_reason: string | null;
}

/**
 * Payload de criação ou edição de receita de Drink no painel do Dono do Bar.
 */
export interface DrinkPayload {
  /** Nome comercial do drink. */
  name: string;
  /** Subtítulo curto exibido acima do título. */
  subtitle: string;
  /** Descrição sensorial completa para o cardápio. */
  description: string;
  /** Nome da categoria de agrupamento. */
  category: string;
  /** Texto do selo de destaque. */
  badge: string;
  /** Cor primária hexadecimal do tema do card. */
  accent_from: string;
  /** Cor secundária hexadecimal do tema do card. */
  accent_to: string;
  /** Cor de referência do copo. */
  glass_color: string;
  /** Estratégia de preço (`auto_ml` ou `fixed`). */
  pricing_mode: DrinkPricingMode;
  /** Valor em centavos para modo de preço fixo. */
  fixed_price_cents: number;
  /** Desconto percentual para combos no modo automático por ml. */
  discount_pct: number;
  /** Visibilidade imediata no cardápio público. */
  active: boolean;
  /** Lista de etapas de dosagem das bombas. */
  steps: DoseStep[];
}

/**
 * Telemetria em tempo real do preparo físico em execução na máquina, transmitida via REST e WebSocket.
 */
export interface PreparationStatus {
  /** Estado atual da máquina (`idle`, `dispensing`, `completed`, `stopped`, `error`). */
  state: PrepState;
  /** ID do pedido atualmente sendo servido, se houver. */
  order_id: string | null;
  /** Senha numérica sequencial do pedido em preparo (ex.: `#14`). */
  order_number: number | null;
  /** ID da receita em preparo (`null` para drinks personalizados por ml). */
  drink_id: string | null;
  /** Nome do drink que está sendo despejado no copo. */
  drink_name: string | null;
  /** Percentual de conclusão da dosagem (`0` a `100`) para animação ao vivo do copo no celular. */
  progress: number;
  /** Bomba que está ativa despejando líquido neste instante, usada para colorir o jato animado. */
  current_pump: PumpId | null;
  /** Índice da etapa atual de dosagem. */
  current_step_index: number;
  /** Total de etapas programadas para o pedido atual. */
  total_steps: number;
  /** Mensagem amigável de status exibida na tela do cliente (ex.: `"Servindo Gin Tanqueray..."`). */
  message: string;
  /** Canal físico utilizado na execução deste preparo. */
  transport: 'cloud_iot' | 'wifi' | 'serial' | 'simulator' | null;
  /** Segundos decorridos desde o início do acionamento das bombas. */
  elapsed_seconds: number;
  /** Duração total prevista do preparo em segundos. */
  total_seconds: number;
}

/**
 * Diagnóstico detalhado de conectividade entre o backend em nuvem/local e o hardware ESP8266/ESP32.
 */
export interface HardwareHealth {
  /** Modo de conexão configurado pelo operador para esta máquina. */
  mode: ConnectionMode;
  /** Transporte efetivamente ativo após resolução automática/fallback. */
  active_transport: 'cloud_iot' | 'wifi' | 'serial' | 'simulator' | 'disconnected';
  /** Indica se o ESP respondeu ao ping HTTP na rede local. */
  wifi_reachable: boolean;
  /** Endereço IP reportado pelo módulo Wi-Fi, quando disponível. */
  wifi_ip: string | null;
  /** Intensidade do sinal Wi-Fi em dBm (RSSI). */
  wifi_rssi: number | null;
  /** Indica se a porta USB Serial física está aberta e conectada. */
  serial_connected: boolean;
  /** Lista de portas COM/tty detectadas no host local. */
  available_serial_ports: string[];
  /** Hostname/IP configurado para comunicação LAN direta. */
  esp32_host: string;
  /** Porta TCP configurada para comunicação LAN direta. */
  esp32_port: number;
  /** Caminho/nome da porta serial configurada. */
  serial_port: string;
  /** Taxa de transmissão serial (baud rate). */
  serial_baud: number;
  /** Indica se o firmware em campo fez pull/heartbeat recente no endpoint Cloud IoT (`/api/iot/:slug/sync`). */
  iot_online: boolean;
  /** Segundos desde o último contato da placa IoT com a nuvem. */
  last_seen_seconds_ago: number | null;
  /** Resumo textual amigável do estado do hardware exibido ao dono do bar. */
  detail: string;
}

/**
 * Representação administrativa completa de uma unidade física de máquina Bartender.OS instalada no bar.
 */
export interface Machine {
  /** UUID/identificador interno da máquina. */
  id: string;
  /** Identificador do bar ao qual a máquina pertence. */
  bar_id: string;
  /** Código único amigável usado na URL do QR Code (`/m/:slug`). */
  slug: string;
  /** Nome de localização da máquina no salão (ex.: `"Máquina #01 · Balcão"`). */
  name: string;
  /** Token secreto exclusivo gravado no firmware (`secrets.h`) para autenticação IoT na nuvem. */
  api_token: string;
  /** URL pública completa codificada no adesivo QR Code da máquina. */
  qr_url: string;
  /** Taxa adicional opcional por copo descartável + gelo, em centavos. */
  cup_fee_cents: number;
  /** Consumação mínima exigida por pedido nesta máquina, em centavos. */
  min_order_cents: number;
  /** Trava máxima de segurança de volume por copo em ml (evita transbordamento na bandeja). */
  max_cup_ml: number;
  /** Habilita ou oculta a aba "Monte por ml" para os clientes desta máquina. */
  allow_custom_builder: boolean;
  /** Modo de comunicação selecionado com a eletrônica da máquina. */
  connection_mode: ConnectionMode;
  /** Host/IP local da placa ESP. */
  esp32_host: string;
  /** Porta HTTP local da placa ESP. */
  esp32_port: number;
  /** Porta USB Serial configurada. */
  serial_port: string;
  /** Velocidade serial em bps. */
  serial_baud: number;
  /** Estado detalhado das 4 bombas e respectivas garrafas instaladas. */
  pumps: PumpSlot[];
  /** Saúde e conectividade atual do hardware embarcado. */
  hardware: HardwareHealth;
  /** Progresso de dosagem em tempo real. */
  status: PreparationStatus;
  /** Quantidade atual de pedidos pagos aguardando ou na vez desta máquina. */
  queue_length: number;
}

/**
 * Detalhamento financeiro e volumétrico de cada ingrediente que compõe um pedido (`Order`).
 */
export interface OrderItemBreakdown {
  /** Bomba de origem deste ingrediente. */
  pump: PumpId;
  /** ID da garrafa consumida no momento da compra. */
  bottle_id: string | null;
  /** Nome do ingrediente congelado no recibo do pedido. */
  ingredient: string;
  /** Cor hexadecimal usada para desenhar a camada do pedido no modal de acompanhamento. */
  color_hex: string;
  /** Quantidade comprada deste ingrediente em mililitros. */
  ml: number;
  /** Preço de venda desta fração de ingrediente em centavos. */
  price_cents: number;
  /** Custo proporcional de aquisição (CMV) desta fração em centavos. */
  cost_cents: number;
}

/**
 * Entidade transacional central de Pedido (Pix + Fila Inteligente + Preparo Físico + Split Financeiro).
 */
export interface Order {
  /** Identificador único global do pedido. */
  id: string;
  /** Senha curta sequencial amigável chamada no salão (ex.: `#104`). */
  order_number: number;
  /** Identificador do bar vendedor. */
  bar_id: string;
  /** Identificador interno da máquina escolhida. */
  machine_id: string;
  /** Slug público da máquina onde o drink será retirado. */
  machine_slug: string;
  /** Nome amigável da máquina (ex.: `"Máquina #01 · Pista"`). */
  machine_name: string;
  /** Sessão anônima do celular do cliente proprietário deste pedido. */
  customer_session_id: string;
  /** Nome/apelido opcional informado pelo consumidor. */
  customer_name: string;
  /** ID da receita de cardápio (`null` quando criado pelo construtor personalizado por ml). */
  drink_id: string | null;
  /** Nome da bebida ou criação autoral escolhida pelo cliente. */
  drink_name: string;
  /** `true` se montado sob medida pelo cliente na aba "Monte por ml". */
  is_custom: boolean;
  /** `true` se contiver qualquer insumo alcoólico. */
  is_alcoholic: boolean;
  /** Roteiro físico de acionamento das bombas para este pedido. */
  steps: DoseStep[];
  /** Extrato itemizado por ingrediente (ml, preço de venda e custo). */
  items: OrderItemBreakdown[];
  /** Volume líquido total do pedido em mililitros. */
  total_ml: number;
  /** Subtotal referente aos líquidos/receita antes da taxa de copo, em centavos. */
  subtotal_cents: number;
  /** Valor cobrado pelo copo + gelo, em centavos. */
  cup_fee_cents: number;
  /** Valor final total da cobrança Pix paga pelo cliente, em centavos. */
  total_cents: number;
  /** Custo total dos insumos consumidos neste pedido (CMV), em centavos. */
  cost_total_cents: number;
  /** Comissão retida pela plataforma SaaS (Split), em centavos. */
  platform_fee_cents: number;
  /** Receita líquida repassada ao bar após taxa da plataforma (`total_cents - platform_fee_cents`). */
  bar_net_cents: number;
  /** Estado atual na máquina de estados de pagamento, fila e dispensação. */
  status: OrderStatus;
  /** Posição atual do cliente na fila de espera da máquina (`1` = próximo/na vez). */
  queue_position: number;
  /** Contagem regressiva em segundos até a expiração do código Pix pendente. */
  seconds_until_pix_expiry: number;
  /** Contagem regressiva em segundos para o cliente confirmar o copo na base antes de pausar sua vez. */
  seconds_until_turn_expiry: number;
  /** Motor de pagamento utilizado neste pedido (`simulated` ou `mercadopago`). */
  payment_provider: PaymentProvider;
  /** ID da transação externa no Mercado Pago, quando aplicável. */
  payment_external_id: string | null;
  /** String EMV "Pix Copia e Cola" pronta para área de transferência no smartphone. */
  pix_qr_code: string;
  /** Imagem Data URI / Base64 do QR Code Pix para leitura por segundo aparelho. */
  pix_qr_base64: string;
  /** Timestamp ISO 8601 de abertura do pedido. */
  created_at: string;
  /** Timestamp ISO 8601 de confirmação bancária do Pix. */
  paid_at: string | null;
  /** Timestamp ISO 8601 do término da entrega física da bebida. */
  completed_at: string | null;
}

/**
 * Contexto público completo carregado ao escanear o QR Code de uma máquina (`/api/public/m/:slug`).
 * Reúne marca do bar, regras de copo, estoque ao vivo das bombas, cardápio filtrado e eventual pedido ativo.
 */
export interface MachinePublicContext {
  /** Nome fantasia do bar exibido no cabeçalho mobile. */
  bar_name: string;
  /** Slug identificador do bar. */
  bar_slug: string;
  /** Provedor Pix ativo no estabelecimento. */
  payment_provider: PaymentProvider;
  /** ID interno da máquina conectada. */
  machine_id: string;
  /** Slug da máquina conectada. */
  machine_slug: string;
  /** Nome de exibição da máquina conectada. */
  machine_name: string;
  /** Taxa de copo/gelo desta máquina em centavos. */
  cup_fee_cents: number;
  /** Valor mínimo de pedido nesta máquina em centavos. */
  min_order_cents: number;
  /** Capacidade máxima permitida do copo em ml. */
  max_cup_ml: number;
  /** Indica se a aba de personalização por ml está habilitada nesta máquina. */
  allow_custom_builder: boolean;
  /** Estado atual das 4 bombas para precificação e limites de estoque ao vivo. */
  pumps: PumpSlot[];
  /** Receitas ativas do cardápio já calculadas para as garrafas desta máquina. */
  drinks: DrinkRecipe[];
  /** Estado imediato de preparo físico da máquina. */
  status: PreparationStatus;
  /** Diagnóstico resumido da controladora de hardware. */
  hardware: HardwareHealth;
  /** Tamanho atual da fila de espera desta máquina. */
  queue_length: number;
  /** Senha do pedido atualmente convocado para posicionar o copo, se houver. */
  ready_order_number: number | null;
  /** Pedido em aberto pertencente à sessão atual do celular do cliente, permitindo retomada imediata. */
  active_customer_order: Order | null;
}

/**
 * Pacote leve transmitido via WebSocket (`/api/ws/machines/:slug`) a cada mudança de bomba, fila ou dosagem.
 */
export interface MachineRealtimeSnapshot {
  /** Slug da máquina emissora do evento. */
  machine_slug: string;
  /** Progresso instantâneo de dosagem (`progress`, `current_pump`, `message`). */
  status: PreparationStatus;
  /** Saúde atualizada da conexão com o hardware. */
  hardware: HardwareHealth;
  /** Quantidade atualizada de pessoas na fila. */
  queue_length: number;
  /** ID do pedido atualmente autorizado a colocar o copo. */
  ready_order_id: string | null;
  /** Número da senha atualmente autorizada a colocar o copo. */
  ready_order_number: number | null;
  /** Volumes e estados atualizados das 4 bombas após baixas de estoque. */
  pumps: PumpSlot[];
}

/**
 * Configurações cadastrais e credenciais mascaradas de recebimento Pix do estabelecimento (`/api/bar/settings`).
 */
export interface BarSettings {
  /** ID único do bar (usado na URL de webhook dedicado do Mercado Pago). */
  id: string;
  /** Nome comercial do bar. */
  name: string;
  /** Slug único do bar. */
  slug: string;
  /** Nome do sócio/responsável. */
  owner_name: string;
  /** E-mail administrativo do responsável. */
  owner_email: string;
  /** Modo Pix atualmente habilitado (`simulated` ou `mercadopago`). */
  payment_provider: PaymentProvider;
  /** Indica se já existe um Access Token do Mercado Pago salvo com segurança no cofre do backend. */
  has_mp_token: boolean;
  /** Representação mascarada do token salvo (ex.: `"APP_USR-****1234"`) para conferência visual segura. */
  mp_token_masked: string;
  /** Indica se a validação criptográfica de assinatura de Webhook está configurada. */
  mp_webhook_secret_configured: boolean;
  /** Percentual de comissão SaaS acordado com a plataforma sobre cada venda Pix. */
  platform_fee_percent: number;
  /** URL base pública do servidor para composição automática do endpoint de Webhook e QR Codes. */
  public_base_url: string;
}

/**
 * Resposta de verificação ao vivo da conta Mercado Pago (`/api/bar/settings/test-mercadopago`).
 */
export interface MpTokenTestResult {
  ok: boolean;
  account_id: string;
  nickname: string;
  email: string;
  first_name: string;
  is_test: boolean;
  message: string;
}

/**
 * Indicadores financeiros consolidados (DRE em tempo real) exibidos no topo do painel do Dono do Bar.
 */
export interface BarAnalytics {
  /** Total de pedidos com Pix confirmado. */
  paid_orders_count: number;
  /** Total de drinks fisicamente entregues com sucesso. */
  completed_orders_count: number;
  /** Pedidos aguardando pagamento ou execução na fila. */
  pending_orders_count: number;
  /** Total de pedidos estornados ao consumidor. */
  refunded_orders_count: number;
  /** Faturamento bruto total recebido via Pix, em centavos. */
  gross_revenue_cents: number;
  /** Custo total de insumos (garrafas) consumidos nos drinks pagos, em centavos. */
  total_cost_cents: number;
  /** Soma das taxas de split destinadas à plataforma SaaS, em centavos. */
  platform_fees_cents: number;
  /** Lucro líquido real do dono do bar (`gross - cost - platform_fees`), em centavos. */
  net_profit_cents: number;
  /** Volume total acumulado servido pelas máquinas do bar, em mililitros. */
  total_ml_dispensed: number;
}

/**
 * Resumo executivo de um bar cliente listado no console multi-tenant do Super-Admin.
 */
export interface BarSummary {
  /** Identificador único do tenant (bar). */
  id: string;
  /** Nome comercial do estabelecimento. */
  name: string;
  /** Slug único do estabelecimento. */
  slug: string;
  /** Nome do proprietário/gestor. */
  owner_name: string;
  /** E-mail de login do proprietário. */
  owner_email: string;
  /** Indica se a conta do bar está ativa para operar vendas. */
  active: boolean;
  /** Provedor Pix em uso pelo estabelecimento. */
  payment_provider: PaymentProvider;
  /** Indica se o estabelecimento já conectou sua conta Mercado Pago real. */
  has_mp_token: boolean;
  /** Taxa percentual de comissão SaaS (Split) aplicada a este bar. */
  platform_fee_percent: number;
  /** Quantidade de máquinas Bartender.OS vinculadas a este bar. */
  machines_count: number;
  /** Volume total de pedidos pagos neste estabelecimento. */
  paid_orders_count: number;
  /** Faturamento bruto transacionado pelo bar, em centavos. */
  gross_revenue_cents: number;
  /** Receita recorrente gerada para a plataforma SaaS por este bar, em centavos. */
  platform_fees_cents: number;
  /** Data de credenciamento do bar na plataforma. */
  created_at: string;
}

/**
 * Visão macro consolidada de toda a rede SaaS Bartender.OS para o Super-Admin.
 */
export interface PlatformOverview {
  /** Quantidade total de bares cadastrados na base. */
  total_bars: number;
  /** Quantidade de bares atualmente ativos em operação. */
  active_bars: number;
  /** Parque total de máquinas instaladas em todos os clientes. */
  total_machines: number;
  /** Quantidade global de pedidos pagos via Pix na plataforma. */
  total_paid_orders: number;
  /** GMV (Gross Merchandise Volume) total transacionado na rede, em centavos. */
  total_gross_cents: number;
  /** Receita bruta acumulada da plataforma SaaS via Split percentual, em centavos. */
  total_platform_fees_cents: number;
  /** Lista detalhada de todos os estabelecimentos clientes. */
  bars: BarSummary[];
}

/**
 * Resumo público enxuto de máquina disponível para listagem/descoberta rápida.
 */
export interface PublicMachineSummary {
  /** Código slug da máquina (`/m/:slug`). */
  slug: string;
  /** Nome amigável da máquina. */
  name: string;
  /** Nome do bar onde a máquina opera. */
  bar_name: string;
}
