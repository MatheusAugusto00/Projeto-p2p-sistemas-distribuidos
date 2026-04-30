# Arquitetura de Sistemas Distribuidos

Projeto da disciplina de Arquitetura de Sistemas Distribuidos do CEUB.

## Visao geral

Este repositorio implementa a base de comunicacao entre um no `Master` e um no `Worker` usando sockets TCP em Python, com mensagens JSON delimitadas por `\n`.

O fluxo atual cobre:

- Sprint 1: heartbeat entre Worker e Master para verificar disponibilidade.
- Sprint 2: apresentacao do Worker, distribuicao de tarefas, processamento simulado, envio de status final e confirmacao por `ACK`.

## Arquivos

- [server.py](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/server.py): implementa o Master.
- [client.py](/Users/level33/studies/arq/Projeto-p2p-sistemas-distribuidos/client.py): implementa o Worker.

## Funcionalidades implementadas

### Master

- Atua como servidor TCP concorrente com `threading`.
- Mantem fila de tarefas pendentes.
- Recebe a apresentacao do Worker com `WORKER` e `WORKER_UUID`.
- Aceita `SERVER_UUID` opcional para identificar Worker emprestado.
- Distribui uma tarefa com `TASK: QUERY` ou informa `TASK: NO_TASK`.
- Recebe o status final da tarefa (`OK` ou `NOK`).
- Retorna confirmacao final com `STATUS: ACK`.
- Faz validacao basica dos payloads e registra erros de protocolo.

### Worker

- Atua como cliente TCP.
- Conecta ao Master, apresenta seu UUID e pode informar `SERVER_UUID` de origem.
- Aguarda resposta do Master com timeout de 5 segundos.
- Processa a tarefa recebida com simulacao de trabalho.
- Envia o status final da tarefa para o Master.
- Aguarda `ACK` e tenta reconectar automaticamente em caso de falha.

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
- `WORKER_ID`
- `SERVER_UUID`
- `MASTER_TIMEOUT`
- `RECONNECT_DELAY`

## Comportamento esperado

1. O Worker abre uma conexao TCP com o Master.
2. O Worker envia sua mensagem de apresentacao.
3. O Master responde com `QUERY` ou `NO_TASK`.
4. Se houver tarefa, o Worker simula o processamento.
5. O Worker envia o resultado com `STATUS: OK` ou `STATUS: NOK`.
6. O Master registra o resultado e responde com `ACK`.
7. O Worker fecha o ciclo e tenta novamente apos o intervalo configurado.

## Observacoes de implementacao

- O Master usa `SO_REUSEADDR` para facilitar reinicios.
- O Worker usa timeout de 5 segundos para nao ficar bloqueado indefinidamente.
- O processamento da fila no Master esta protegido por `Lock` para evitar condicoes de corrida entre threads.
- O protocolo ignora extensoes nao usadas diretamente, mas exige a presenca dos campos obrigatorios nas mensagens conhecidas.
