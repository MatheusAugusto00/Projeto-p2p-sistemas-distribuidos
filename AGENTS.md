# Project Agent Instructions

Este arquivo deve ser lido antes de qualquer acao em prompts futuros deste projeto.

## Regras obrigatorias

1. Use sempre as skills configuradas no projeto antes de executar qualquer tarefa.
   - As skills locais ficam em `.agents/skills/`.
   - Comece verificando quais skills se aplicam ao pedido.
   - Se a tarefa envolver nova funcionalidade, mudanca de comportamento ou refatoracao, siga o fluxo das skills de brainstorming, planejamento, TDD e verificacao.

2. Respeite a organizacao por sprint.
   - Cada sprint deve ter uma spec em `docs/superpowers/specs/`.
   - Cada sprint deve ter um plano em `docs/superpowers/plans/`.
   - Antes de implementar uma sprint nova ou alterar uma sprint existente, atualize ou crie a spec e o plano correspondentes.

3. Nao implemente direto sem escopo claro.
   - Primeiro entenda se o pedido pertence a uma sprint existente ou a uma nova sprint.
   - Se o pedido alterar requisitos, protocolo, arquitetura, fluxo de tasks, Workers ou Masters, registre isso na spec antes do codigo.

4. Use TDD para mudancas de comportamento.
   - Escreva ou atualize testes antes do codigo de producao.
   - Rode os testes e confirme a falha esperada.
   - Implemente o minimo necessario para passar.
   - Rode a verificacao completa antes de afirmar que terminou.

5. Preserve o escopo do projeto.
   - O foco atual do repositorio e o trabalho de Arquitetura de Sistemas Distribuidos.
   - Nao adicionar frameworks, APIs externas, banco de dados ou interface grafica sem pedido explicito.
   - Preferir Python standard library e o padrao atual de sockets TCP com JSON delimitado por `\n`.

6. Nao remover trabalho existente sem pedido explicito.
   - Nao reverter mudancas do usuario.
   - Nao apagar arquivos de docs, specs, planos ou testes sem confirmacao.

## Estrutura esperada

```text
.
├── AGENTS.md
├── README.md
├── server.py
├── client.py
├── tests/
│   └── test_sprint3.py
└── docs/
    └── superpowers/
        ├── specs/
        │   └── YYYY-MM-DD-<sprint-ou-topico>-design.md
        └── plans/
            └── YYYY-MM-DD-<sprint-ou-topico>.md
```

## Verificacao minima antes de concluir

Sempre que houver alteracao de codigo Python, rode:

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py
```

Se algum comando falhar, relate a falha e nao declare a tarefa como concluida.
