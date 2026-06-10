# Sprint 4 Supervisor Metrics Design

## Objetivo

Implementar a Sprint 4 do projeto: envio automatico de relatorios de performance do Master para o Supervisor de Metricas do Cluster definido no PDF. O envio deve usar socket TCP com TLS, payload JSON delimitado por `\n`, sem HTTP e sem aguardar resposta com `recv`.

## Escopo

O `server.py` continua sendo o unico processo Master. Ao iniciar, ele deve manter os comportamentos das Sprints 1 a 3 e tambem iniciar uma thread daemon que envia um payload `performance_report` a cada 10 segundos por padrao.

Configuracoes por variavel de ambiente:

- `SUPERVISOR_ENABLED`: habilita ou desabilita a thread de envio. Padrao `1`.
- `SUPERVISOR_HOST`: host do supervisor. Padrao `nuted-ia.dev`.
- `SUPERVISOR_PORT`: porta do supervisor. Padrao `443`.
- `SUPERVISOR_INTERVAL`: intervalo entre envios, em segundos. Padrao `10`.
- `SUPERVISOR_TLS`: usa TLS quando `1`. Padrao `1`.
- `SUPERVISOR_SNI`: SNI usado no TLS. Padrao igual a `SUPERVISOR_HOST`.
- `HOSTNAME`: hostname reportado no payload. Padrao `<MASTER_UUID>.farm.local`.

## Payload

O payload segue o modelo da Sprint 4:

- `server_uuid`: `MASTER_UUID`.
- `hostname`: `HOSTNAME` ou fallback local.
- `role`: `master`.
- `task`: `performance_report`.
- `timestamp`: UTC no formato ISO-8601 com `Z`.
- `message_id`: UUID v4.
- `payload_version`: `sprint4-monitor`.
- `performance.system`: metricas de uptime, load, CPU, memoria e disco coletadas com Python standard library e fallbacks seguros.
- `performance.farm_state`: resumo de Workers e tarefas a partir de `MasterState`.
- `performance.config_thresholds`: `CAPACITY`, `RELEASE_THRESHOLD` e alertas padrao de CPU/memoria.
- `performance.neighbors`: lista derivada de `PEER_MASTERS`, com status conhecido quando houver registro local.

## Comportamento

O sender abre uma conexao para o supervisor, envolve o socket com TLS quando configurado, envia `json.dumps(payload) + "\n"` e fecha a conexao. Ele nao deve chamar `recv`, pois o PDF instrui que os servers apenas enviem os dados e encerrem a conexao.

Falhas de rede devem ser registradas em log sem derrubar o Master. A thread deve continuar tentando no proximo intervalo.

## Testes

Os testes devem cobrir:

- Estrutura obrigatoria do payload.
- Contadores de Workers locais, ocupados, emprestados para fora e recebidos.
- Contadores de tarefas pendentes, em execucao, concluidas e falhas.
- Configuracao de thresholds e neighbors.
- Sender escrevendo JSON terminado por `\n` sem chamar `recv`.
- Startup respeitando `SUPERVISOR_ENABLED=0`.

## Fora de Escopo

- Uso de HTTP, REST ou bibliotecas externas.
- Dashboard proprio.
- Persistencia das metricas.
- Alteracao do protocolo Worker/Master ou da negociacao P2P.
