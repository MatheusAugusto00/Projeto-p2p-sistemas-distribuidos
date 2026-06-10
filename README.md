# Arquitetura de Sistemas Distribuidos

Projeto da disciplina de Arquitetura de Sistemas Distribuidos do CEUB.

## Visao geral

Este repositorio implementa a base de comunicacao entre um no `Master` e um no `Worker` usando sockets TCP em Python, com mensagens JSON delimitadas por `\n`.

O fluxo atual cobre:

- Sprint 1: heartbeat entre Worker e Master para verificar disponibilidade.
- Sprint 2: apresentacao do Worker, distribuicao de tarefas, processamento simulado, envio de status final e confirmacao por `ACK`.
- Sprint 3: negociacao P2P entre Masters, redirecionamento temporario de Workers emprestados e devolucao ao Master de origem.
- Sprint 4: envio automatico de metricas do Master para o Supervisor de Metricas via TLS sobre TCP.

## Arquivos

- [server.py](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/server.py): implementa o Master.
- [client.py](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/client.py): implementa o Worker.
- [docs/superpowers/specs](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/docs/superpowers/specs): specs de design produzidas antes da implementacao.

## Funcionalidades implementadas

### Master

- Atua como servidor TCP concorrente com `threading`.
- Mantem fila de tarefas pendentes.
- Recebe a apresentacao do Worker com `WORKER` e `WORKER_UUID`.
- Aceita `SERVER_UUID` opcional para identificar Worker emprestado.
- Distribui uma tarefa com `TASK: QUERY` ou informa `TASK: NO_TASK`.
- Recebe o status final da tarefa (`OK` ou `NOK`).
- Retorna confirmacao final com `STATUS: ACK`.
- Atua tambem como cliente TCP para pedir ajuda a Masters vizinhos quando a fila ultrapassa `CAPACITY`.
- Monitora saturacao em uma thread propria, sem depender da chegada de Workers locais.
- Processa mensagens Master-to-Master com `type`, `request_id` e `payload`.
- Mantem as tarefas separadas em `Em fila`, `Em atividade` e `Feito`.
- Responde `response_accepted` ou `response_rejected` para pedidos `request_help`.
- Enfileira `command_redirect` para Workers locais ociosos ofertados a outro Master.
- Registra Workers emprestados com `register_temporary_worker`.
- Enfileira `command_release` e envia `notify_worker_returned` quando a carga cai abaixo de `RELEASE_THRESHOLD`.
- Se um Worker desconectar enquanto processa uma tarefa, devolve a tarefa para o inicio da fila.
- Faz validacao basica dos payloads e registra erros de protocolo.
- Envia relatorios `performance_report` para o supervisor externo da Sprint 4.
- Usa TLS sobre TCP para o supervisor, sem HTTP e sem aguardar resposta.

### Worker

- Atua como cliente TCP.
- Conecta ao Master, apresenta seu UUID e pode informar `SERVER_UUID` de origem.
- Aguarda resposta do Master com timeout de 5 segundos.
- Processa a tarefa recebida com simulacao de trabalho.
- Envia o status final da tarefa para o Master.
- Aguarda `ACK` e tenta reconectar automaticamente em caso de falha.
- Trata `command_redirect`, troca o Master atual e envia `register_temporary_worker`.
- Trata `command_release`, volta ao Master original e remove o campo `SERVER_UUID` da apresentacao.

## Protocolo JSON

Todas as mensagens devem terminar com `\n`.

### 1. Apresentacao do Worker para o Master

Campos obrigatorios:

- `WORKER`
- `WORKER_UUID`

Campo opcional:

- `SERVER_UUID`: usado quando o Worker esta emprestado por outro Master.

Exemplo:

```json
{
  "WORKER": "ALIVE",
  "WORKER_UUID": "W-123",
  "SERVER_UUID": "Master_B"
}
```

### 2. Resposta do Master com tarefa

Quando houver tarefa:

```json
{
  "TASK": "QUERY",
  "USER": "Task1"
}
```

Quando nao houver tarefa:

```json
{
  "TASK": "NO_TASK"
}
```

### 3. Status final enviado pelo Worker

```json
{
  "STATUS": "OK",
  "TASK": "QUERY",
  "WORKER_UUID": "W-123"
}
```

O campo `STATUS` pode ser `OK` ou `NOK`.

### 4. Confirmacao final do Master

```json
{
  "STATUS": "ACK",
  "WORKER_UUID": "W-123"
}
```

### 5. Pedido de ajuda entre Masters

```json
{
  "type": "request_help",
  "request_id": "uuid-v4",
  "payload": {
    "master_id": "Master_A",
    "current_load": 150,
    "capacity": 100,
    "workers_needed": 2,
    "return_address": "127.0.0.1:8000"
  }
}
```

Resposta aceita:

```json
{
  "type": "response_accepted",
  "request_id": "uuid-v4",
  "payload": {
    "workers_offered": 1,
    "worker_details": [
      { "id": "B1", "address": "dynamic" }
    ]
  }
}
```

Resposta recusada:

```json
{
  "type": "response_rejected",
  "request_id": "uuid-v4",
  "payload": {
    "reason": "no_workers_available"
  }
}
```

### 6. Redirecionamento, registro e devolucao

```json
{
  "type": "command_redirect",
  "request_id": "uuid-v4",
  "payload": {
    "new_master_address": "127.0.0.1:8000",
    "original_master_address": "127.0.0.1:8001"
  }
}
```

```json
{
  "type": "register_temporary_worker",
  "request_id": "uuid-v4",
  "payload": {
    "worker_id": "B1",
    "original_master_address": "127.0.0.1:8001"
  }
}
```

```json
{
  "type": "command_release",
  "request_id": "uuid-v4",
  "payload": {
    "original_master_address": "127.0.0.1:8001"
  }
}
```

```json
{
  "type": "notify_worker_returned",
  "request_id": "uuid-v4",
  "payload": {
    "worker_id": "B1"
  }
}
```

### 7. Relatorio de metricas para o Supervisor

O Master envia automaticamente, a cada 10 segundos, um JSON terminado por `\n` para o supervisor da Sprint 4. A conexao padrao e TLS sobre TCP em `nuted-ia.dev:443`; o processo apenas conecta, envia e fecha, sem chamar `recv`.

Campos principais:

```json
{
  "server_uuid": "Master_A",
  "hostname": "Master_A.farm.local",
  "role": "master",
  "task": "performance_report",
  "timestamp": "2026-06-10T12:00:00Z",
  "message_id": "uuid-v4",
  "payload_version": "sprint4-monitor",
  "performance": {
    "system": {},
    "farm_state": {},
    "config_thresholds": {},
    "neighbors": []
  }
}
```

## Como executar

Em um terminal, inicie o Master:

```bash
python3 server.py
```

Em outro terminal, inicie o Worker:

```bash
python3 client.py
```

Se a porta `8000` ja estiver ocupada na sua maquina, voce pode executar em outra porta:

```bash
MASTER_PORT=8001 python3 server.py
MASTER_PORT=8001 python3 client.py
```

Tambem e possivel customizar:

- `MASTER_HOST`
- `MASTER_PORT`
- `MASTER_UUID`
- `PEER_MASTERS`: vizinhos no formato `Master_B@127.0.0.1:8001,Master_C@127.0.0.1:8002`.
- `INITIAL_TASK_COUNT`: quantidade inicial de tarefas criadas pelo Master.
- `CAPACITY`: quantidade de tarefas pendentes que dispara `request_help`.
- `RELEASE_THRESHOLD`: carga abaixo da qual Workers emprestados podem ser devolvidos.
- `HELP_CHECK_INTERVAL`: intervalo, em segundos, entre verificacoes de saturacao.
- `SUPERVISOR_ENABLED`: habilita envio de metricas da Sprint 4. Padrao `1`.
- `SUPERVISOR_HOST`: host do supervisor. Padrao `nuted-ia.dev`.
- `SUPERVISOR_PORT`: porta do supervisor. Padrao `443`.
- `SUPERVISOR_INTERVAL`: intervalo entre envios de metricas. Padrao `10`.
- `SUPERVISOR_TLS`: usa TLS quando `1`. Padrao `1`.
- `SUPERVISOR_SNI`: SNI usado na conexao TLS. Padrao igual a `SUPERVISOR_HOST`.
- `HOSTNAME`: hostname enviado no payload. Padrao `<MASTER_UUID>.farm.local`.
- `WORKER_ID`
- `SERVER_UUID`
- `MASTER_TIMEOUT`
- `RECONNECT_DELAY`

Para desabilitar o envio durante testes locais:

```bash
SUPERVISOR_ENABLED=0 python3 server.py
```

### Simulacao local da Sprint 3

Terminal 1, Master A saturado em `8000`:

```bash
MASTER_UUID=Master_A MASTER_HOST=127.0.0.1 MASTER_PORT=8000 INITIAL_TASK_COUNT=50 CAPACITY=5 RELEASE_THRESHOLD=2 PEER_MASTERS=Master_B@127.0.0.1:8001 python3 server.py
```

Terminal 2, Master B vizinho em `8001`:

```bash
MASTER_UUID=Master_B MASTER_HOST=127.0.0.1 MASTER_PORT=8001 INITIAL_TASK_COUNT=0 CAPACITY=100 RELEASE_THRESHOLD=60 PEER_MASTERS=Master_A@127.0.0.1:8000 python3 server.py
```

Terminal 3, Worker local do Master B:

```bash
WORKER_ID=B1 MASTER_HOST=127.0.0.1 MASTER_PORT=8001 python3 client.py
```

Quando o Master A detectar carga acima de `CAPACITY`, a thread de monitoramento envia `request_help` ao Master B. O Master B foi iniciado com `INITIAL_TASK_COUNT=0` para manter B1 e B2 ociosos e disponiveis para emprestimo. O Worker recebe `command_redirect` na proxima apresentacao. Depois de redirecionado, ele registra `register_temporary_worker` no Master A e passa a pedir tarefas com `SERVER_UUID` apontando para o Master de origem.

## Comportamento esperado

1. O Worker abre uma conexao TCP com o Master.
2. O Worker envia sua mensagem de apresentacao.
3. O Master responde com `QUERY` ou `NO_TASK`.
4. Se houver tarefa, o Master move a tarefa de `Em fila` para `Em atividade`.
5. O Worker simula o processamento.
6. O Worker envia o resultado com `STATUS: OK` ou `STATUS: NOK`.
7. O Master move a tarefa de `Em atividade` para `Feito` e responde com `ACK`.
8. Se a conexao cair antes do `STATUS`, o Master remove a tarefa de `Em atividade` e devolve para o inicio de `Em fila`.
9. O Worker fecha o ciclo e tenta novamente apos o intervalo configurado.
10. Na Sprint 3, quando ha saturacao, o Master negocia Workers com vizinhos e pode devolver Workers emprestados quando a carga normaliza.

## Observacoes de implementacao

- O Master usa `SO_REUSEADDR` para facilitar reinicios.
- O Worker usa timeout de 5 segundos para nao ficar bloqueado indefinidamente.
- O processamento das listas de tarefas no Master esta protegido por `Lock` para evitar condicoes de corrida entre threads.
- O protocolo ignora extensoes nao usadas diretamente, mas exige a presenca dos campos obrigatorios nas mensagens conhecidas.
- Mensagens Master-to-Master usam `type` em minusculas, `request_id` para correlacao e `payload` com os dados da operacao.
- Tipos Master-to-Master desconhecidos sao registrados em log e ignorados para manter compatibilidade com extensoes futuras.

## Integracao com Obra Superpowers

Este repositorio foi preparado para trabalhar com a skill `brainstorming` da Obra Superpowers:

- Specs aprovadas devem ser salvas em `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`.
- Nenhuma implementacao nova deve comecar sem uma spec curta ou detalhada, dependendo da complexidade.
- O fluxo recomendado e: `brainstorming -> revisao da spec -> plano de implementacao -> codigo`.

### Estrutura adicionada

```text
docs/
  superpowers/
    specs/
      TEMPLATE-design.md
```

### Como usar no projeto

1. Antes de codar, defina o escopo da mudanca em uma spec dentro de `docs/superpowers/specs/`.
2. Use [docs/superpowers/specs/TEMPLATE-design.md](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/docs/superpowers/specs/TEMPLATE-design.md) como base.
3. Registre arquitetura, componentes, fluxo de dados, erros e testes.
4. So depois da aprovacao da spec avance para implementacao no `server.py`, `client.py` ou arquivos futuros.

### Quando criar uma spec

- Nova mensagem no protocolo.
- Novo papel na rede P2P.
- Mudanca no fluxo de distribuicao de tarefas.
- Persistencia, retries, descoberta de peers, eleicao de lider, replicacao ou tolerancia a falhas.
