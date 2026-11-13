# Tarefas — Central de Notificações Internas, fase 1 (2026-11-13)

Plano: [`PLAN/2026-11-13-notificacoes.md`](../PLAN/2026-11-13-notificacoes.md).
Spec: [`SPEC/2026-09-30-notificacoes.md`](../SPEC/2026-09-30-notificacoes.md).

Como usar:
- Executar **na ordem**, uma por vez. Marcar `[x]` ao terminar.
- "Pronto" = testes da tarefa passando + `pytest` e `npm test` verdes + commit.
- Commit: `<parte>: <o que mudou>` com os trailers `Agent: ...` e
  `Spec: SPEC/2026-09-30-notificacoes.md`.
- Abreviação de spec: **NT** notificacoes (`SPEC/2026-09-30-notificacoes.md`).

Critérios adiados (não implementar nesta fase; nenhuma spec é alterada): canal e-mail e caixa
simulada `/admin/emails`, lembretes 24h/2h (tarefa periódica, idempotência, canceladas sem
lembrete pendente), preferência de e-mail no perfil, lista de espera, convite de profissional,
recuperação de senha, aviso de cancelamento pelo paciente para a clínica. SMS, WhatsApp e push
são fora do escopo da spec (permanente).

---

- [x] **01. Documentação da fase** — NT
  `PLAN/2026-11-13-notificacoes.md` e `TASKS/2026-11-13-notificacoes.md`: escopo da V1,
  critérios cobertos e adiados, decisões aprovadas. Sem código.
  Teste: nenhum (documentação); `git diff --check` limpo.

- [x] **02. Modelo `Notificacao` e migração** — NT
  `app/notificacoes/models.py` (CHECK `ck_notificacoes_tipo` com os 3 tipos, FKs `usuarios`
  ON DELETE CASCADE e `consultas` ON DELETE SET NULL, índice `(usuario_id, criado_em)`),
  migração Alembic nova e registro em `app/modelos.py`.
  Testes (`tests/backend/test_migracoes.py`): `alembic upgrade head` num banco temporário cria
  `notificacoes` com o CHECK; `downgrade` remove a tabela; o banco recusa tipo fora da lista.

- [x] **03. Templates e criação de notificação** — NT
  `app/notificacoes/textos.py` (título/texto por tipo com variáveis; data/hora formatada em
  `America/Sao_Paulo`) e `service.criar` (renderiza na criação e valida o tipo).
  Teste: textos em português com os dados da consulta (profissional, unidade, tipo, data/hora;
  na remarcação, data antiga e nova).

- [x] **04. Notificação ao marcar** — NT
  `agendamento.service.marcar`: cria `consulta_marcada` para o paciente na mesma transação,
  antes do `_commit` (sem commit próprio), tanto quando o paciente marca para si quanto quando
  a recepção marca em nome dele.
  Testes: os dois casos criam notificação não lida para o **paciente** (não para a recepção);
  marcar para horário ocupado (409) não cria notificação.

- [x] **05. Notificação ao remarcar (com atomicidade)** — NT
  `agendamento.service.remarcar`: cria `consulta_remarcada` para o paciente na mesma transação,
  antes do `_commit`.
  Testes: remarcar cria a notificação (paciente e recepção); remarcar para horário ocupado →
  409 e **zero** notificações (rollback da transação); a original continua intacta.

- [x] **06. Notificação ao cancelar pela clínica** — NT
  `agendamento.service.cancelar`: cria `consulta_cancelada` **somente** quando o autor é
  recepção/admin, na mesma transação, antes do commit.
  Testes: cancelamento pela recepção cria; cancelamento pelo paciente não cria; cancelamento
  de consulta já cancelada não cria nada além do 422.

- [x] **07. Endpoints da central** — NT
  `app/notificacoes/{schemas,service,router}.py` + registro em `app/main.py`:
  GET `/notificacoes` (paginado, 20/página, mais recentes primeiro, com `nao_lidas`),
  PATCH `/notificacoes/{id}/lida` e POST `/notificacoes/marcar-todas-lidas`.
  Testes: lista só as próprias (privacidade); PATCH de notificação alheia → 404 (autorização);
  paginação; contagem de não lidas; marcar todas devolve o total atualizado; 401 sem token.

- [x] **08. Sino no cabeçalho (paciente)** — NT
  `features/notificacoes/{tipos.ts,Sino.tsx}`; `shared/Layout.tsx` renderiza o sino apenas
  para pacientes; badge com o total de não lidas (até "9+").
  Testes: sino visível para paciente e ausente para os demais perfis e deslogado; contagem
  correta a partir do mock da API.

- [x] **09. Central de notificações** — NT
  `features/notificacoes/CentralNotificacoes.tsx`: lista paginada, não lidas destacadas,
  botão "Marcar todas como lidas", clique na notificação marca como lida (PATCH) e navega
  para `/minhas-consultas`.
  Testes: renderização e destaque de não lidas; clique chama PATCH e navega; marcar todas
  chama POST e zera o badge; erro da API em português; link presente.

- [x] **10. Rota, estilo e revisão final** — NT
  Rota `/notificacoes` protegida para `["paciente"]` em `App.tsx`; classes do sino/badge/central
  em `estilos.css`; revisão do diff; `pytest` e `npm test` completos verdes.
  Teste: suíte completa (backend + frontend) verde.

---

### Critérios adiados (fases seguintes — nenhuma spec alterada)

- Canal e-mail e caixa simulada visível ao admin em `/admin/emails`.
- Lembretes 24h e 2h antes por tarefa periódica, com idempotência.
- Consulta cancelada não recebe lembretes pendentes.
- Preferência do paciente por e-mails de lembrete no perfil.
- Vaga da lista de espera, convite de profissional e recuperação de senha.
- Aviso de cancelamento pelo paciente para a clínica (quando a equipe tiver central própria).
- SMS, WhatsApp e push: fora do escopo da spec (permanente).
