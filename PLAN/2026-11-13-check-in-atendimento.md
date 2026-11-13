# Plano — Check-in e Atendimento, fase 1 (2026-11-13)

Tarefas: [`TASKS/2026-11-13-check-in-atendimento.md`](../TASKS/2026-11-13-check-in-atendimento.md).
Spec: [`SPEC/2026-09-30-check-in-e-atendimento.md`](../SPEC/2026-09-30-check-in-e-atendimento.md).

## 1. Escopo da fase 1 (V1)

Do dia da consulta até a finalização, passando pela fila da recepção e pelo comprovante do
paciente. A spec original **não é alterada**; critérios não cobertos ficam listados como adiados.

### Matriz de critérios da spec

| Critério da spec | Situação |
|---|---|
| Recepção vê a fila do dia por unidade, ordenada por horário, com status | **Atendido na V1** — com permissão de acesso por unidade (decisão 7) |
| Check-in no dia, a partir de 1h antes → `confirmada` + hora de chegada | **Atendido na V1** — por paciente (dono), recepção ou admin (decisão 2) |
| Profissional clica em "chamar" → `em_atendimento` + hora de início | **Atendido na V1** — somente o profissional dono da consulta |
| Finalizar com anotação ≤ 5.000 → `realizada` + hora de fim | **Atendido na V1** — anotação obrigatória e não vazia (decisão 5) |
| Anotação visível só para o autor e profissionais da mesma especialidade | **Atendido na V1** (decisão 6) |
| 30 min após o horário sem check-in, a recepção pode marcar `faltou` | **Atendido na V1** (decisão 4) |
| Às 23:59, consultas ainda `marcada` viram `faltou` (tarefa agendada) | **Adiado** (decisão 3: sem processamento no startup e sem efeitos colaterais em GETs) |
| Paciente baixa comprovante de comparecimento em PDF de `realizada` | **Atendido na V1** — ReportLab; PDF não expõe a anotação (decisões 1 e 10) |
| Fila atualiza sozinha a cada 30 segundos (ou por WebSocket) | **Parcial** — polling de 30 s no frontend (`refetchInterval`); WebSocket adiado |
| Painel de TV chamando senha; prontuário estruturado | Fora do escopo da spec (permanente) |

### Base já existente (partes anteriores)

Status completos em `consultas` com CHECK, tabela `TRANSICOES` (marcada→confirmada→
em_atendimento→realizada; marcada→faltou), `HistoricoStatus` com quem/quando/de→para,
vínculo profissional↔usuário e especialidades do profissional (m2m). Nenhum endpoint de
check-in/fila/finalização existe hoje: as transições desses status só ocorrem em teste.

## 2. Decisões aprovadas (2026-11-13)

1. Comprovante PDF usa biblioteca própria, preferencialmente **ReportLab**, registrada nas
   dependências do projeto (`requirements.txt`).
2. Check-in pode ser feito pelo próprio paciente, pela recepção ou pelo admin, respeitando
   autorização e vínculo com a consulta.
3. A rotina automática de faltas às 23:59 fica **adiada**; nada de processamento no startup
   nem efeitos colaterais em `GET /fila`.
4. A recepção pode marcar manualmente `faltou` após 30 minutos do horário previsto.
5. Anotação obrigatória na finalização, limite de 5.000 caracteres, validação contra conteúdo
   vazio.
6. Anotação visível somente ao autor e a profissionais que compartilhem especialidade.
7. A fila respeita permissões de acesso **por unidade**.
8. Transições simultâneas protegidas contra duplicidade (lock pessimista na consulta).
9. Horários em UTC no banco, exibidos no fuso local configurado (`America/Sao_Paulo`).
10. O comprovante PDF não expõe a anotação clínica.

## 3. Arquitetura

### Backend — módulo novo `app/atendimento/`
```
app/atendimento/
  models.py   # RecepcaoUnidade (vínculo recepção ↔ unidade)
  schemas.py  # FilaItem, FinalizarIn, AnotacaoOut, etc.
  service.py  # check_in, chamar, finalizar, marcar_faltou, fila, anotacao, comprovante
  router.py   # endpoints abaixo; registro em app/main.py
```
As colunas novas de `chegada_em`/`atendimento_inicio`/`atendimento_fim`/`anotacao` ficam em
`app/agendamento/models.py` (tabela `consultas`), e as transições continuam passando pelo
`mudar_status` de `app/agendamento/service.py` (histórico preservado).

**Concorrência (decisão 8):** toda transição de check-in/atendimento obtém a consulta com
`SELECT ... FOR UPDATE` (lock na linha) antes de validar e mudar o status — dois pedidos
simultâneos para a mesma consulta são serializados; o segundo recebe 422 pela tabela
`TRANSICOES`. Mesmo padrão do lock de profissional usado na marcação.

**Horários (decisão 9):** colunas `timestamptz` em UTC; janelas do check-in/faltou calculadas
com `Relogio.agora()` (controlável nos testes) e fuso `FUSO_LOCAL`; o PDF imprime as datas no
fuso local.

**PDF (decisões 1 e 10):** `reportlab` (versão fixada em `requirements.txt`), gerado em
memória a partir de um template simples; contém nome do paciente, profissional (nome e
registro), unidade, tipo de consulta, data/hora (local) e hora de realização — **sem a
anotação**.

### Frontend — `src/frontend/src/features/atendimento/`
```
FilaDoDia.tsx            # recepção/admin: fila por unidade, check-in, faltou, refresh 30 s
VinculosRecepcao.tsx     # admin: vincula recepção a unidades
tipos.ts                 # FilaItem e respostas
```
Além disso: ações na `AgendaProfissional` (chamar/finalizar/ver anotação) e botão de
comprovante em `MinhasConsultas`. Menu da recepção ganha "Fila do dia"; rota `/recepcao/fila`
protegida para recepção/admin; rota `/admin/recepcao` para o admin.

## 4. Modelo de dados (migração nova)

**Alteração em `consultas`** (ADD COLUMN, seguro no deploy):

| Coluna | Tipo | Uso |
|---|---|---|
| `chegada_em` | timestamptz NULL | hora do check-in |
| `atendimento_inicio` | timestamptz NULL | hora do chamar |
| `atendimento_fim` | timestamptz NULL | hora do finalizar |
| `anotacao` | Text NULL, CHECK `char_length(anotacao) <= 5000` | anotação clínica; autor = profissional da consulta |

**Nova tabela `recepcao_unidade`** (decisão 7): `usuario_id` FK `usuarios` CASCADE e
`unidade_id` FK `unidades` CASCADE, PK composto. Admin tem acesso a todas as unidades;
recepção só às vinculadas (403 sem vínculo). O seed vincula a recepção de demonstração às
unidades de demonstração.

## 5. Rotas da API (prefixo `/api`)

| Método | Rota | Perfis | Regras |
|---|---|---|---|
| GET | `/fila?unidade_id=&data=` | recepção, admin | consultas do dia/unidade ordenadas por início, com `chegada_em` e flags `pode_check_in`/`pode_faltou`; recepção só na unidade vinculada (403) |
| GET | `/fila/unidades` | recepção, admin | unidades permitidas para o seletor (admin: todas ativas) |
| POST | `/consultas/{id}/check-in` | paciente (dono), recepção, admin | `marcada`; mesmo dia (local) e `agora >= inicio − 1h`; duplicado/cancelada/finalizada → 422 |
| POST | `/consultas/{id}/chamar` | profissional dono | `confirmada → em_atendimento` + `atendimento_inicio`; outros → 403 |
| POST | `/consultas/{id}/finalizar` | profissional dono | `em_atendimento → realizada` + `atendimento_fim`; `anotacao` obrigatória, não vazia, ≤ 5.000 (422) |
| GET | `/consultas/{id}/anotacao` | autor + profissionais com especialidade em comum | demais → 403 |
| POST | `/consultas/{id}/faltou` | recepção, admin | `marcada`; `agora >= inicio + 30min` (422 antes) |
| GET | `/consultas/{id}/comprovante.pdf` | paciente (dono) | só `realizada` (422); PDF sem anotação |
| GET/POST/DELETE | `/recepcao-unidades` | admin | lista/víncula/desvincula recepção ↔ unidades |

## 6. Testes

- **Backend** (`tests/backend/test_atendimento.py`): check-in (janela, duplicado, dono,
  cancelada → 422, recepção/admin OK, `chegada_em` e histórico); chamar (dono OK, outro
  profissional/recepção → 403, sem check-in → 422); finalizar (anotação salva, vazia → 422,
  > 5.000 → 422, hora de fim); visibilidade da anotação (autor, mesma especialidade,
  especialidade diferente → 403, paciente/recepção → 403); faltou (antes dos 30 min → 422,
  depois OK, paciente → 403); fila (ordenação, flags, 401/403, **recepção sem vínculo → 403,
  admin em qualquer unidade**); comprovante (content-type, conteúdo em fuso local, **sem
  anotação no corpo**, não realizada → 422, não dono → 404); **concorrência** (duas threads
  fazem check-in/chamar na mesma consulta → exatamente uma vence); migração (upgrade/downgrade
  em banco temporário, padrão `test_migracoes.py`).
- **Frontend** (`tests/frontend/atendimento.test.tsx`): FilaDoDia (lista, check-in chama POST
  e atualiza, faltou só com a flag, **refresh automático de 30 s** com fake timers); ações na
  agenda do profissional (chamar/finalizar, textarea + contador, erro 422 em português,
  anotação sob demanda); comprovante em MinhasConsultas (só realizada, download via
  `apiDownload`); vínculo recepção↔unidade no admin.

## 7. Riscos

- **ReportLab** entra em `requirements.txt` (versão fixada); instalado no CI e no Render via
  `pip install -r requirements.txt` (fluxo atual). Teste de PDF não depende de fontes do
  sistema (fontes padrão do ReportLab).
- **Vínculo recepção↔unidade** exige atualizar o seed (a recepção de demonstração precisa de
  vínculo para a demonstração funcionar); `test_seed.py` continua verde.
- **Lock na transição**: só PostgreSQL (mesmo padrão da marcação); testes de concorrência com
  threads, como o teste de marcação simultânea.
- Sweep automático adiado: consultas esquecidas ficam `marcada` até alguém agir — comportamento
  aceito nesta fase (decisão 3).
