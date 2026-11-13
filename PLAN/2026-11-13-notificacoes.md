# Plano — Central de Notificações Internas, fase 1 (2026-11-13)

Tarefas: [`TASKS/2026-11-13-notificacoes.md`](../TASKS/2026-11-13-notificacoes.md).
Spec: [`SPEC/2026-09-30-notificacoes.md`](../SPEC/2026-09-30-notificacoes.md).

## 1. Escopo da fase 1 (V1)

Primeira fatia da spec de notificações: o canal **dentro da aplicação**, priorizando o paciente.
A spec original **não é alterada**; os critérios não cobertos ficam listados como adiados.

Eventos que geram notificação na V1 (destinatário: o paciente):

| Evento | Notifica? |
|---|---|
| Consulta marcada (pelo paciente ou pela recepção/admin em nome dele) | Sim — `consulta_marcada` |
| Consulta remarcada (por qualquer lado autorizado) | Sim — `consulta_remarcada` |
| Consulta cancelada **pela clínica** (recepção/admin) | Sim — `consulta_cancelada` |
| Consulta cancelada pelo próprio paciente | Não (decisão aprovada) |

### Critérios da spec cobertos na V1

| Critério da spec | Situação na V1 |
|---|---|
| Eventos que geram notificação: marcada, remarcada, cancelada | Parcial: cancelada **pela clínica**; o aviso do cancelamento pelo paciente para a clínica fica para quando a equipe tiver central própria |
| Canal: notificação dentro da aplicação (sino com contador de não lidas) | Coberto |
| Textos das mensagens em modelos (templates) com variáveis; nenhum texto fixo na regra de negócio | Coberto (`app/notificacoes/textos.py`; texto renderizado na criação) |
| Marcar notificações como lidas, uma a uma ou todas | Coberto |

### Critérios adiados (nenhuma spec é alterada)

- Canal **e-mail** e caixa simulada visível ao admin em `/admin/emails`.
- Lembretes 24h e 2h antes por tarefa periódica, com idempotência (uma consulta nunca recebe
  o mesmo lembrete duas vezes).
- Regra "consulta cancelada não recebe lembretes pendentes" (fica junto dos lembretes).
- Preferência do paciente por e-mails de lembrete no perfil.
- Vaga da lista de espera, convite de profissional e recuperação de senha.
- SMS, WhatsApp e push continuam **fora do escopo** da spec (permanente).

## 2. Arquitetura

### Backend — módulo novo `app/notificacoes/`
```
app/notificacoes/
  models.py   # Notificacao
  schemas.py  # NotificacaoOut, ListaNotificacoes
  service.py  # criar, listar, marcar_lida, marcar_todas_lidas
  textos.py   # templates de título/texto por tipo, com variáveis
  router.py   # GET /notificacoes, PATCH /notificacoes/{id}/lida, POST /notificacoes/marcar-todas-lidas
```

**Geração (pontos de integração)** — em `app/agendamento/service.py`, **na mesma transação**
da operação, sem commit próprio (decisão aprovada):

- `marcar()`: após `_criar` retornar e antes de `_commit` → notifica o paciente (ele mesmo ou o
  alvo escolhido pela recepção).
- `remarcar()`: após a nova consulta ser criada e antes de `_commit` → notifica o paciente.
  Se a nova falhar, o rollback remove a notificação (atomicidade).
- `cancelar()`: após `_cancelar_sem_commit` e antes do commit, **somente** quando
  `autor.perfil in ("recepcao", "admin")`.

O `agendamento` decide o evento e o destinatário; o `notificacoes` decide o texto (templates).
Sem ciclo de import (`agendamento.service → notificacoes.service → agendamento.models`).

### Frontend — `src/frontend/src/features/notificacoes/`
```
tipos.ts                 # tipo Notificacao e resposta da API
Sino.tsx                 # sino no cabeçalho com contador de não lidas
CentralNotificacoes.tsx  # página /notificacoes
```
- `shared/Layout.tsx`: renderiza o `Sino` no nav **apenas quando `usuario.perfil === "paciente"`**.
- `App.tsx`: rota `/notificacoes` protegida para `["paciente"]`.
- Clique numa notificação: PATCH `/lida` + navega para `/minhas-consultas` (não existe página
  de detalhe de consulta; `consulta_id` fica guardado para deep link futuro).

## 3. Modelo de dados

**`notificacoes`** — criada por migração Alembic nova:

| Coluna | Tipo | Observações |
|---|---|---|
| `id` | int PK | |
| `usuario_id` | FK `usuarios.id` ON DELETE CASCADE, índice | destinatário |
| `tipo` | String(30) com CHECK `IN ('consulta_marcada', 'consulta_remarcada', 'consulta_cancelada')` | novos tipos (lembretes etc.) exigirão migração — aceito |
| `titulo` | String(120) | renderizado do template na criação |
| `texto` | String(500) | renderizado do template na criação |
| `consulta_id` | FK `consultas.id` ON DELETE SET NULL, nulo, índice | |
| `lida_em` | timestamptz nulo | NULL = não lida |
| `criado_em` | timestamptz `server_default now()` | UTC |

Índice `(usuario_id, criado_em)` para listagem/contagem. Datas em UTC no banco; exibição em
`America/Sao_Paulo` (frontend usa `shared/datas.ts`).

## 4. Rotas da API (prefixo `/api`, todas exigem login)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/notificacoes?pagina=&por_pagina=` | lista do usuário logado (mais recentes primeiro), paginada (`core.paginacao`, 20/página); resposta inclui `nao_lidas` |
| PATCH | `/notificacoes/{id}/lida` | marca a notificação como lida; de outro usuário → 404 |
| POST | `/notificacoes/marcar-todas-lidas` | marca todas como lidas; retorna `{"atualizadas": n}` |

## 5. Telas

| Rota | Tela | Perfil |
|---|---|---|
| — (cabeçalho) | Sino com contador de não lidas (badge, "9+" acima de 9) | paciente |
| `/notificacoes` | Central: lista paginada, não lidas destacadas, "Marcar todas como lidas", clique marca lida e vai para `/minhas-consultas` | paciente |

## 6. Testes

Cada critério incluído na V1 vira pelo menos um teste. A suíte existente não muda:

- **Backend** (`tests/backend/test_notificacoes.py`): geração nas três operações (paciente e
  recepção), atomicidade (remarcar para horário ocupado → 409 e zero notificações),
  cancelamento pelo paciente não notifica, autorização (404 para notificação alheia),
  privacidade (lista só as próprias), paginação, contagem de não lidas, templates em português
  com data exibida em `America/Sao_Paulo`.
- **Migração** (`tests/backend/test_migracoes.py`): banco temporário (pgserver) +
  `alembic upgrade head` cria `notificacoes` com o CHECK do `tipo`; `downgrade` remove a
  tabela.
- **Frontend** (`tests/frontend/notificacoes.test.tsx`): sino só para paciente, badge com
  contagem, central lista e destaca não lidas, clique marca lida e navega, marcar todas,
  erros em português.

## 7. Decisões da V1 (aprovadas em 2026-11-13)

1. V1 cobre notificações de consulta marcada, remarcada e cancelada pela clínica.
2. Cancelamento realizado pelo próprio paciente não gera notificação nesta fase.
3. `tipo` com CHECK no banco, aceitando inicialmente os 3 tipos da V1.
4. O sino é exibido somente para pacientes na V1.
5. Clique na notificação marca como lida e direciona para `/minhas-consultas`.
6. O seed não é alterado.
7. Textos renderizados na criação da notificação (histórico estável).
8. A criação das notificações participa da mesma transação da operação de agendamento, sem
   commit independente.

## 8. Riscos

- CHECK no `tipo` exige migração a cada tipo novo (lembretes, lista de espera...): custo aceito
  e previsto nas fases seguintes.
- Sino restrito a pacientes: quando a fase 2 notificar outros perfis, ajustar `Layout.tsx`
  (mudança pequena e localizada).
- Seed sem notificações: a demonstração só mostra notificações após ações reais do usuário.
- Migração é CREATE TABLE puro (sem alterar dados existentes): segura no deploy, que roda
  `alembic upgrade head` no `start.sh`.
