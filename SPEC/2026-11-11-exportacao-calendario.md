# SPEC — Exportação de consultas para calendário

**Data:** 2026-11-11

**Projeto:** MarcaConsulta — AP2

**Status:** Aprovada para implementação

## 1. Contexto

Atualmente, o MarcaConsulta permite que pacientes visualizem suas consultas futuras e passadas por meio da tela "Minhas consultas".

Entretanto, não foi encontrada uma funcionalidade que permita exportar os compromissos para aplicativos externos de calendário.

Esta especificação descreve a implementação de uma funcionalidade para exportar as consultas futuras do paciente autenticado no formato iCalendar (.ics).

## 2. Objetivo

Permitir que pacientes exportem suas consultas futuras para aplicativos compatíveis com o formato iCalendar, como Google Calendar, Outlook e Apple Calendar.

A exportação deverá gerar um único arquivo contendo todos os compromissos elegíveis do paciente.

## 3. Usuários envolvidos

Exclusivamente pacientes autenticados no sistema.

Profissionais, recepcionistas e administradores não terão acesso a esse endpoint de exportação.

## 4. Regras de negócio

### RN01 — Autenticação

A exportação deverá exigir autenticação e perfil de paciente.

### RN02 — Propriedade dos agendamentos

O sistema deverá recuperar exclusivamente consultas vinculadas ao identificador do paciente autenticado.

Não deverá ser aceito um identificador de paciente fornecido livremente pelo frontend para selecionar os agendamentos exportados.

### RN03 — Consultas elegíveis

Somente consultas futuras com status "marcada" ou "confirmada" deverão ser exportadas.

### RN04 — Consultas não elegíveis

Não deverão ser exportadas consultas:
- Com início anterior ou igual ao momento da exportação.
- Canceladas pelo paciente.
- Canceladas pela clínica.
- Com status de falta.
- Com status de atendimento já realizado.

### RN05 — Informações do evento

Cada evento deverá conter:
- Identificador único e estável.
- Data e hora de início.
- Data e hora de término.
- Título genérico: "Consulta médica".
- Nome do profissional.
- Nome da unidade.
- Endereço da unidade, quando disponível.

Não deverão ser incluídos CPF, nome do paciente, diagnóstico, observações clínicas ou outras informações médicas sensíveis.

### RN06 — Fuso horário

O banco de dados utiliza UTC e a aplicação utiliza o fuso configurado em `APP_TIMEZONE`, atualmente `America/Sao_Paulo`.

Os eventos deverão ser exportados com timestamps UTC no formato iCalendar, utilizando o sufixo `Z`.

Os aplicativos de calendário serão responsáveis pela apresentação dos horários no fuso local do usuário.

### RN07 — Consultas simultâneas

A exportação deverá considerar os dados disponíveis no momento da requisição, sem modificar ou bloquear agendamentos.

### RN08 — Ausência de consultas

Caso não existam consultas elegíveis, o sistema deverá disponibilizar um calendário válido, sem eventos, ou apresentar uma mensagem adequada ao usuário, conforme a solução técnica definida na implementação.

## 5. Backend

Criar um endpoint:

`GET /api/consultas/minhas/exportar.ics`

O endpoint deverá:

- Utilizar a infraestrutura de autenticação existente.
- Exigir o perfil paciente.
- Consultar os agendamentos pertencentes exclusivamente ao usuário autenticado.
- Aplicar os filtros de elegibilidade.
- Ordenar os eventos por data de início.
- Gerar um arquivo válido no padrão iCalendar.
- Retornar o conteúdo com `Content-Type: text/calendar; charset=utf-8`.
- Disponibilizar o arquivo para download por meio do cabeçalho `Content-Disposition`.

Não deverão ser criadas novas tabelas no banco de dados.

A implementação deverá respeitar os serviços e padrões arquiteturais existentes.

## 6. Formato do arquivo

O arquivo deverá seguir a estrutura do padrão iCalendar, contendo:

- `BEGIN:VCALENDAR`
- `VERSION:2.0`
- `PRODID`
- `CALSCALE:GREGORIAN`
- Um bloco `VEVENT` para cada consulta elegível.
- `END:VCALENDAR`

Cada evento deverá conter:
- `UID`
- `DTSTAMP`
- `DTSTART`
- `DTEND`
- `SUMMARY`
- `DESCRIPTION`
- `LOCATION`, quando houver endereço disponível.

Os identificadores deverão ser estáveis para cada consulta.

O conteúdo textual deverá respeitar as regras de escape do iCalendar, incluindo caracteres especiais, quebras de linha e acentuação.

As linhas deverão respeitar os limites de tamanho previstos no padrão RFC 5545, incluindo a dobra de linhas quando necessária.

## 7. Frontend

Na tela `MinhasConsultas.tsx`, deverá ser disponibilizado um botão:

**Exportar calendário (.ics)**

O botão deverá:
- Permitir o download do arquivo.
- Utilizar a autenticação existente.
- Preservar o mecanismo de renovação de tokens.
- Informar adequadamente eventuais erros.
- Apresentar uma mensagem quando não houver consultas elegíveis.

Como a função `api()` existente espera respostas JSON, deverá ser implementado um mecanismo apropriado para download de respostas binárias, preservando o tratamento de autenticação já utilizado pelo sistema.

## 8. Testes automatizados

### Backend

Os testes deverão comprovar:

1. Usuário não autenticado não consegue acessar o endpoint.
2. Usuário com perfil diferente de paciente recebe acesso negado.
3. Paciente exporta somente suas próprias consultas.
4. Consultas de outros pacientes não aparecem no arquivo.
5. Consultas passadas não são exportadas.
6. Consultas canceladas não são exportadas.
7. Consultas marcadas e confirmadas futuras são exportadas.
8. Datas, horários e duração dos eventos estão corretos.
9. Caracteres especiais e acentuação são tratados corretamente.
10. Os cabeçalhos de resposta indicam o download de um arquivo iCalendar.
11. A ausência de consultas gera uma resposta válida.

### Frontend

Os testes deverão comprovar:

1. Exibição da opção de exportação na tela Minhas Consultas.
2. Realização da requisição autenticada.
3. Download do arquivo `.ics`.
4. Tratamento de erros na exportação.
5. Mensagem adequada quando não existem consultas elegíveis.

## 9. Critérios de aceitação

A funcionalidade será considerada concluída quando:

- O paciente conseguir baixar o arquivo `.ics`.
- O arquivo puder ser importado em um aplicativo compatível.
- Somente consultas elegíveis e pertencentes ao paciente forem exportadas.
- Os horários forem preservados corretamente.
- As informações sensíveis forem omitidas.
- Os testes automatizados forem aprovados.
- O build do frontend for concluído sem erros.
- A implementação estiver integrada por meio de Pull Request aprovado.

## 10. Restrições

- Não modificar a arquitetura original do projeto.
- Não substituir frameworks ou tecnologias.
- Não criar tabelas desnecessárias.
- Não modificar as regras existentes de agendamento.
- Não expor informações de pacientes.
- Não adicionar dependências externas sem justificativa técnica.

A implementação deverá aproveitar os módulos existentes de agendamento, autenticação e comunicação com a API.

## 11. Referências técnicas

- `src/backend/app/agendamento/router.py`
- `src/backend/app/agendamento/service.py`
- `src/backend/app/agendamento/models.py`
- `src/backend/app/core/tempo.py`
- `src/backend/app/core/config.py`
- `src/frontend/src/features/agendamento/MinhasConsultas.tsx`
- `src/frontend/src/features/agendamento/tipos.ts`
- `src/frontend/src/shared/api.ts`
- `tests/backend/test_agendamento.py`
- `tests/frontend/agendamento.test.tsx`

**Referência do formato:** RFC 5545 — Internet Calendaring and Scheduling Core Object Specification.