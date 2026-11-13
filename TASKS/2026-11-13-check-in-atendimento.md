# Tarefas — Check-in e Atendimento, fase 1 (2026-11-13)

Plano: [`PLAN/2026-11-13-check-in-atendimento.md`](../PLAN/2026-11-13-check-in-atendimento.md).
Spec: [`SPEC/2026-09-30-check-in-e-atendimento.md`](../SPEC/2026-09-30-check-in-e-atendimento.md).

Como usar:
- Executar **na ordem**, uma por vez. Marcar `[x]` ao terminar.
- "Pronto" = testes da tarefa passando + `pytest` e `npm test` verdes + commit.
- Commit: `<parte>: <o que mudou>` com os trailers `Agent: ...` e
  `Spec: SPEC/2026-09-30-check-in-e-atendimento.md`.
- Abreviação de spec: **CH** check-in-e-atendimento (`SPEC/2026-09-30-check-in-e-atendimento.md`).

Critérios adiados (não implementar nesta fase; nenhuma spec é alterada): marcação automática
de `faltou` às 23:59 por tarefa agendada (decisão 3 — sem processamento no startup e sem
efeitos colaterais em GETs) e WebSocket para a fila (a V1 usa polling de 30 s). Painel de TV
e prontuário estruturado são fora do escopo da spec (permanente).

---

- [ ] **01. Documentação da fase** — CH
  `PLAN/2026-11-13-check-in-atendimento.md` e `TASKS/2026-11-13-check-in-atendimento.md`:
  matriz de critérios, decisões aprovadas, escopo V1. Sem código.
  Teste: nenhum (documentação); `git diff --check` limpo.

- [x] **02. Migração: colunas de atendimento e vínculo recepção↔unidade** — CH
  Colunas `chegada_em`, `atendimento_inicio`, `atendimento_fim` (timestamptz NULL) e
  `anotacao` (Text NULL, CHECK `char_length <= 5000`) em `consultas`; tabela `recepcao_unidade`
  (`usuario_id` + `unidade_id`, FKs CASCADE, PK composto) em `app/atendimento/models.py`;
  registro em `app/modelos.py`.
  Testes (`tests/backend/test_migracoes.py`): upgrade cria colunas/tabela com o CHECK;
  downgrade remove; CHECK recusa anotação > 5.000.

- [x] **03. Transições protegidas contra concorrência** — CH
  Helper em `app/atendimento/service.py`: obter consulta com `SELECT ... FOR UPDATE` antes de
  validar e transicionar; todas as ações passam por ele.
  Testes: duas threads fazem check-in na mesma consulta → exatamente uma vence (201/200) e a
  outra recebe 422; chamar simultâneo idem; histórico registra apenas a transição vencedora.

- [x] **04. Check-in** — CH
  `POST /consultas/{id}/check-in` para paciente (dono), recepção e admin: `marcada → confirmada`,
  mesmo dia no fuso local e `agora >= inicio − 1h`, grava `chegada_em` e histórico.
  Testes: paciente dono OK; recepção e admin OK; antes de 1h → 422; dia errado → 422;
  duplicado (já confirmada) → 422; cancelada/realizada → 422; paciente não dono → 404;
  `chegada_em` gravada; histórico registra quem.

- [x] **05. Chamar** — CH
  `POST /consultas/{id}/chamar` somente para o profissional dono da consulta:
  `confirmada → em_atendimento` + `atendimento_inicio` + histórico.
  Testes: dono OK; outro profissional → 403; recepção → 403; paciente → 403; sem check-in
  (marcada) → 422; horário de início gravado.

- [x] **06. Finalizar com anotação** — CH
  `POST /consultas/{id}/finalizar` somente para o profissional dono: `em_atendimento →
  realizada` + `atendimento_fim`; `anotacao` obrigatória, não vazia e ≤ 5.000 (422).
  Testes: anotação salva; vazia/só espaços → 422; > 5.000 → 422; hora de fim gravada;
  perfis errados → 403; transação atômica (anotação inválida não muda o status).

- [x] **07. Visibilidade da anotação** — CH
  `GET /consultas/{id}/anotacao`: autor (profissional da consulta) e profissionais com ao
  menos uma especialidade em comum veem; recepção, admin, paciente e profissionais sem
  especialidade comum → 403.
  Testes: autor vê; mesma especialidade vê; especialidade diferente → 403; paciente/recepção →
  403; consulta inexistente → 404.

- [x] **08. Faltou manual** — CH
  `POST /consultas/{id}/faltou` para recepção/admin: `marcada → faltou` somente com
  `agora >= inicio + 30min`.
  Testes: antes dos 30 min → 422; depois OK + histórico; paciente/profissional → 403;
  consulta cancelada → 422.

- [x] **09. Fila do dia com permissão por unidade** — CH
  `GET /fila?unidade_id=&data=` e `GET /fila/unidades` (recepção/admin); itens ordenados por
  início com `chegada_em` e flags `pode_check_in`/`pode_faltou`; admin em qualquer unidade,
  recepção só nas vinculadas (403); endpoints `GET/POST/DELETE /recepcao-unidades` (admin).
  Testes: ordenação e flags; recepção sem vínculo → 403; com vínculo → OK; admin em qualquer
  unidade; vínculo/desvínculo só admin; 401 sem token; unidade inexistente → 404.

- [ ] **10. Seed vincula recepção de demonstração** — CH
  `seed.py`: vincula a recepção demo às unidades demo (via `recepcao_unidade`).
  Teste: `test_seed.py` continua verde e a recepção demo aparece vinculada.

- [ ] **11. Comprovante PDF com ReportLab** — CH
  Adicionar `reportlab` (versão fixada) em `requirements.txt`; `GET
  /consultas/{id}/comprovante.pdf` para o paciente dono, só `realizada` (422): PDF em memória
  com paciente, profissional (nome e registro), unidade, tipo, data/hora no fuso local e hora
  de realização — **sem a anotação** (decisões 1, 9 e 10).
  Testes: content-type `application/pdf`; conteúdo contém os dados e **não** contém a
  anotação; não realizada → 422; não dono → 404; datas em `America/Sao_Paulo`.

- [ ] **12. Fila da recepção (frontend)** — CH
  `features/atendimento/{tipos.ts,FilaDoDia.tsx}`: seletor de unidade (só as permitidas),
  lista do dia com status e horário de chegada, botões Check-in/Faltou conforme as flags,
  **refresh automático de 30 s** (`refetchInterval`); rota `/recepcao/fila` (recepção/admin)
  e item "Fila do dia" no menu.
  Testes: lista renderiza; check-in chama POST e atualiza; faltou só com a flag; fake timers
  avançam 30 s e refazem a busca; erro 403 de unidade não permitida aparece em português.

- [ ] **13. Ações do profissional na agenda (frontend)** — CH
  `AgendaProfissional.tsx`: "Chamar" em confirmada, "Finalizar" em em_atendimento (textarea
  com contador até 5.000, erro 422 exibido), "Ver anotação" em realizada (GET sob demanda).
  Testes: botões por status; finalizar envia anotação; contador limita a 5.000; erro do
  servidor em português; anotação carregada e exibida.

- [ ] **14. Comprovante, vínculos do admin e revisão final** — CH
  `MinhasConsultas.tsx`: botão "Comprovante (PDF)" só em realizada (download via
  `apiDownload`); `VinculosRecepcao.tsx` em `/admin/recepcao` (vincular/desvincular recepção
  de unidades); rota e menu; estilos; revisão do diff; `pytest` e `npm test` completos verdes.
  Testes: comprovante presente/ausente conforme o status; download autenticado; tela de
  vínculos chama POST/DELETE e atualiza; suíte completa verde.

---

### Critérios adiados (fases seguintes — nenhuma spec alterada)

- Marcação automática de `faltou` às 23:59 por tarefa agendada (decisão 3).
- WebSocket para atualização da fila (a V1 usa polling de 30 s).
- Painel de TV e prontuário estruturado: fora do escopo da spec (permanente).
