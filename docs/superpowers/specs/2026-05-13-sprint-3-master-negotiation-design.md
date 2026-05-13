# Sprint 3 Master Negotiation Design

## Objetivo

Implementar somente a Sprint 3 do projeto: negociacao entre Masters via TCP, emprestimo temporario de Workers, registro no Master saturado e devolucao ao Master de origem quando a carga normalizar.

## Escopo

O sistema continua usando `server.py` como Master e `client.py` como Worker. A configuracao de multiplos Masters sera feita por variaveis de ambiente para evitar valores fixos no codigo:

- `MASTER_UUID`: identificador do Master atual.
- `MASTER_HOST` e `MASTER_PORT`: endereco de escuta do Master atual.
- `PEER_MASTERS`: lista de vizinhos no formato `Master_B@127.0.0.1:8001,Master_C@127.0.0.1:8002`.
- `CAPACITY`: limite de saturacao.
- `RELEASE_THRESHOLD`: limite abaixo do qual Workers emprestados podem ser devolvidos.

Essa configuracao atende ao requisito do PDF de que cada Master tenha `master_id` e endereco conhecidos pelos vizinhos. O PDF nao exige variaveis de ambiente especificamente; essa e apenas a forma mais simples para executar varios Masters localmente.

## Arquitetura

O Master passara a aceitar dois grupos de mensagens na mesma porta TCP:

1. Protocolo da Sprint 2, mantido para Workers locais e emprestados.
2. Protocolo da Sprint 3, identificado pelo campo `type`.

Mensagens Master-to-Master seguem a estrutura:

```json
{
  "type": "request_help",
  "request_id": "uuid-v4",
  "payload": {}
}
```

Campos desconhecidos serao ignorados. Campos obrigatorios ausentes geram log e resposta de erro controlada quando a conexao ainda permite resposta.

## Fluxo

Quando a fila pendente ultrapassar `CAPACITY`, o Master solicitante calcula `workers_needed` e envia `request_help` ao primeiro vizinho configurado. O vizinho responde com `response_accepted` quando possui Workers locais ociosos ou `response_rejected` quando nao pode ajudar. O `request_id` da resposta e sempre igual ao da requisicao.

Essa verificacao roda em uma thread propria de monitoramento. Assim, um Master saturado pede Workers emprestados mesmo que nenhum Worker local se apresente naquele momento. Quando um pedido e aceito, o Master marca que existe um pedido de ajuda pendente para evitar disparos repetidos antes do registro de um Worker emprestado.

Ao aceitar, o Master ofertante envia `command_redirect` aos Workers selecionados. Como o projeto atual usa Workers que abrem conexoes curtas em loop, o comando sera entregue como resposta a uma apresentacao normal do Worker quando ele estiver ocioso. O Worker reconecta ao novo Master e envia `register_temporary_worker`, depois continua usando o fluxo da Sprint 2 com `SERVER_UUID` preenchido com seu Master original.

Quando a carga do Master receptor cair abaixo de `RELEASE_THRESHOLD`, ele envia `command_release` para Workers emprestados ociosos e envia `notify_worker_returned` ao Master de origem. O Worker volta ao Master original.

## Componentes

- `server.py`
  - Parsing e validacao das mensagens `type`.
  - Diretorio de peers vindo de `PEER_MASTERS`.
  - Estado de Workers conhecidos, locais, emprestados e aguardando redirect/release.
  - Estado de tarefas em tres listas: pendentes, em atividade e feitas.
  - Refileiramento automatico de tarefa em atividade quando o Worker desconectar antes do `STATUS`.
  - Deteccao autonoma de saturacao e liberacao.
  - Cliente TCP para chamadas Master-to-Master.
  - Logs com timestamp, `type` e `request_id`.

- `client.py`
  - Estado do Master atual e Master original.
  - Tratamento de `command_redirect`.
  - Tratamento de `command_release`.
  - Envio de `register_temporary_worker`.
  - Continuidade do protocolo da Sprint 2 apos a reconexao.

## Testes

Serao adicionados testes com `unittest`, sem dependencias externas, cobrindo:

- Parsing de `PEER_MASTERS`.
- Validacao de envelopes Master-to-Master.
- `response_accepted` e `response_rejected` preservando `request_id`.
- Registro de Worker temporario.
- Preparacao de `command_redirect` e `command_release`.
- Atualizacao do estado do Worker no redirect/release.
- Movimentacao de tarefas entre `pending`, `in_progress` e `done`.
- Devolucao de tarefa para `pending` quando um Worker sair durante o processamento.
- Pedido de ajuda disparado pelo monitor de saturacao sem depender de apresentacao de Worker.

## Fora de Escopo

- Pool persistente de conexoes Master-to-Master.
- API REST ou gRPC.
- Persistencia em banco.
- Eleicao de lider ou descoberta automatica de peers.
- Interface grafica.
