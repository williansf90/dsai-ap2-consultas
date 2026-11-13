import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ConfirmarAgendamento from "@/features/agendamento/ConfirmarAgendamento";
import MinhasConsultas from "@/features/agendamento/MinhasConsultas";
import { mockFetch, renderizar } from "./apoio";

const prof = {
  id: 10, nome: "Dr. João Souza", registro: "CRM 1/PA", foto_url: null, biografia: "",
  especialidades: [{ id: 1, nome: "Cardiologia", tipos: [{ id: 3, nome: "Consulta", duracao_min: 30, preco_centavos: 25000 }] }],
  unidades: [{ id: 5, nome: "Unidade Centro", endereco: "Rua A, 1", telefone: "91" }],
  nota_media: null, total_avaliacoes: 0,
};

const consulta = (extra = {}) => ({
  id: 1, inicio: "2026-10-12T12:00:00Z", fim: "2026-10-12T12:30:00Z", status: "marcada", forma_pagamento: "particular",
  preco_centavos: 25000, remarcacoes: 0, paciente: { id: 2, nome: "Maria" }, profissional: { id: 10, nome: "Dr. João Souza" },
  unidade: { id: 5, nome: "Unidade Centro", endereco: "Rua A, 1" }, tipo_consulta: { id: 3, nome: "Consulta", duracao_min: 30 },
  pode_cancelar: true, pode_remarcar: true, ...extra,
});

const ROTA_CONFIRMAR = "/agendar/confirmar?profissional=10&tipo=3&unidade=5&inicio=2026-10-12T12%3A00%3A00Z";

test("confirmação mostra o resumo e marca a consulta", async () => {
  const fetch = mockFetch(
    (url) => (url.endsWith("/publico/profissionais/10") ? { corpo: prof } : undefined),
    (url, init) => (url.endsWith("/consultas") && init?.method === "POST" ? { status: 201, corpo: consulta() } : undefined),
  );
  renderizar(<ConfirmarAgendamento />, { rota: ROTA_CONFIRMAR });
  expect(await screen.findByText("Dr. João Souza")).toBeInTheDocument();
  expect(screen.getByText("12/10/2026, 09:00")).toBeInTheDocument();
  expect(screen.getByText("R$ 250,00", { normalize: (t) => t.replace(/\s/g, " ") })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  expect(await screen.findByRole("heading", { name: "Consulta marcada!" })).toBeInTheDocument();
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ profissional_id: 10, tipo_consulta_id: 3, unidade_id: 5 });
});

test("conflito de horário mostra a mensagem e oferece outro horário", async () => {
  mockFetch(
    (url) => (url.endsWith("/publico/profissionais/10") ? { corpo: prof } : undefined),
    (url, init) =>
      url.endsWith("/consultas") && init?.method === "POST"
        ? { status: 409, corpo: { detail: "Horário não está mais disponível." } }
        : undefined,
  );
  renderizar(<ConfirmarAgendamento />, { rota: ROTA_CONFIRMAR });
  await userEvent.click(await screen.findByRole("button", { name: "Confirmar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Horário não está mais disponível.");
  expect(screen.getByRole("link", { name: "Escolher outro horário" })).toHaveAttribute("href", "/profissionais/10");
});

test("minhas consultas separa próximas e passadas e mostra ações permitidas", async () => {
  mockFetch((url) =>
    url.endsWith("/consultas/minhas")
      ? {
          corpo: {
            proximas: [consulta(), consulta({ id: 2, pode_cancelar: false, pode_remarcar: false })],
            passadas: [consulta({ id: 3, status: "realizada", pode_cancelar: false, pode_remarcar: false })],
          },
        }
      : undefined,
  );
  renderizar(<MinhasConsultas />);
  expect(await screen.findByRole("tab", { name: "Próximas (2)" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Cancelar" })).toHaveLength(1);
  expect(screen.getAllByRole("link", { name: "Remarcar" })).toHaveLength(1);
  await userEvent.click(screen.getByRole("tab", { name: "Passadas (1)" }));
  expect(screen.getByText("Realizada")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancelar" })).not.toBeInTheDocument();
});

// ---------- exportação de calendário (.ics) ----------

const TOKENS = { access_token: "access-1", refresh_token: "refresh-1" };
const USUARIO = { id: 2, nome: "Maria", email: "maria@teste.com", perfil: "paciente" };

const ICS_COM_EVENTO = [
  "BEGIN:VCALENDAR",
  "VERSION:2.0",
  "PRODID:-//MarcaConsulta//Consultas//PT-BR",
  "CALSCALE:GREGORIAN",
  "BEGIN:VEVENT",
  "UID:7f2c9a1e-3b4d-4c8a-9e5f-1a2b3c4d5e6f",
  "DTSTAMP:20261005T110000Z",
  "DTSTART:20261012T120000Z",
  "DTEND:20261012T123000Z",
  "SUMMARY:Consulta médica",
  "DESCRIPTION:Profissional: Dr. João Souza\\nUnidade: Unidade Centro",
  "END:VEVENT",
  "END:VCALENDAR",
  "",
].join("\r\n");

const ICS_SEM_EVENTOS = [
  "BEGIN:VCALENDAR",
  "VERSION:2.0",
  "PRODID:-//MarcaConsulta//Consultas//PT-BR",
  "CALSCALE:GREGORIAN",
  "END:VCALENDAR",
  "",
].join("\r\n");

function entrarComoPaciente() {
  localStorage.setItem("marcaconsulta.tokens", JSON.stringify(TOKENS));
}

function stubsDeDownload() {
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
}

function rotasMinhas() {
  return [
    (url: string) => (url.endsWith("/auth/eu") ? { corpo: USUARIO } : undefined),
    (url: string) => (url.endsWith("/consultas/minhas") ? { corpo: { proximas: [consulta()], passadas: [] } } : undefined),
  ];
}

test("minhas consultas mostra o botão de exportação somente na aba próximas", async () => {
  mockFetch(...rotasMinhas());
  renderizar(<MinhasConsultas />);
  expect(await screen.findByRole("button", { name: "Exportar calendário (.ics)" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Passadas (0)" }));
  expect(screen.queryByRole("button", { name: "Exportar calendário (.ics)" })).not.toBeInTheDocument();
});

test("exportação faz requisição autenticada e baixa o arquivo .ics", async () => {
  entrarComoPaciente();
  stubsDeDownload();
  let nomeBaixado = "";
  let enderecoBaixado = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    nomeBaixado = this.download;
    enderecoBaixado = this.href;
  });
  const fetch = mockFetch(
    ...rotasMinhas(),
    (url) =>
      url.endsWith("/consultas/minhas/exportar.ics")
        ? { texto: ICS_COM_EVENTO, cabecalhos: { "Content-Disposition": 'attachment; filename="consultas.ics"' } }
        : undefined,
  );
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("button", { name: "Exportar calendário (.ics)" }));
  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  const get = fetch.mock.calls.find(([u]) => String(u).endsWith("/consultas/minhas/exportar.ics"));
  expect((get?.[1]?.headers as Headers).get("Authorization")).toBe("Bearer access-1");
  expect(nomeBaixado).toBe("consultas.ics");
  expect(enderecoBaixado).toBe("blob:mock");
  const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
  expect(blob.type).toBe("text/calendar; charset=utf-8");
  expect(blob.size).toBe(new TextEncoder().encode(ICS_COM_EVENTO).length);
});

test("erro na exportação mostra mensagem e não baixa nada", async () => {
  entrarComoPaciente();
  stubsDeDownload();
  mockFetch(
    ...rotasMinhas(),
    (url) =>
      url.endsWith("/exportar.ics")
        ? { status: 403, corpo: { detail: "Seu perfil não tem permissão para esta ação." } }
        : undefined,
  );
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("button", { name: "Exportar calendário (.ics)" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Seu perfil não tem permissão para esta ação.");
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

test("calendário sem eventos elegíveis mostra mensagem e não baixa nada", async () => {
  entrarComoPaciente();
  stubsDeDownload();
  mockFetch(
    ...rotasMinhas(),
    (url) => (url.endsWith("/exportar.ics") ? { texto: ICS_SEM_EVENTOS } : undefined),
  );
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("button", { name: "Exportar calendário (.ics)" }));
  expect(await screen.findByText("Não há consultas elegíveis para exportar.")).toBeInTheDocument();
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

test("exportação renova o token em 401 e repete a requisição", async () => {
  entrarComoPaciente();
  stubsDeDownload();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  let chamadasExportar = 0;
  const fetch = mockFetch(
    ...rotasMinhas(),
    (url, init) =>
      url.endsWith("/auth/renovar") && init?.method === "POST" ? { corpo: { access_token: "access-novo" } } : undefined,
    (url) => {
      if (!url.endsWith("/exportar.ics")) return undefined;
      chamadasExportar += 1;
      return chamadasExportar === 1
        ? { status: 401, corpo: { detail: "Sessão expirada. Entre novamente." } }
        : { texto: ICS_COM_EVENTO };
    },
  );
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("button", { name: "Exportar calendário (.ics)" }));
  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  expect(chamadasExportar).toBe(2);
  const chamadas = fetch.mock.calls.filter(([u]) => String(u).endsWith("/exportar.ics"));
  expect((chamadas[1][1]?.headers as Headers).get("Authorization")).toBe("Bearer access-novo");
  expect(JSON.parse(localStorage.getItem("marcaconsulta.tokens") ?? "{}")).toMatchObject({ access_token: "access-novo" });
});
