import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AgendaProfissional from "@/features/agenda/AgendaProfissional";
import MinhasConsultas from "@/features/agendamento/MinhasConsultas";
import FilaDoDia from "@/features/atendimento/FilaDoDia";
import VinculosRecepcao from "@/features/atendimento/VinculosRecepcao";
import { mockFetch, renderizar } from "./apoio";

const UNIDADES = [{ id: 5, nome: "Unidade Centro", endereco: "Rua A, 1" }];

const filaItem = (extra = {}) => ({
  id: 1,
  inicio: "2026-10-12T12:00:00Z",
  fim: "2026-10-12T12:30:00Z",
  status: "marcada",
  forma_pagamento: "particular",
  preco_centavos: 25000,
  remarcacoes: 0,
  paciente: { id: 2, nome: "Maria Paciente" },
  profissional: { id: 10, nome: "Dr. João Souza" },
  unidade: { id: 5, nome: "Unidade Centro", endereco: "Rua A, 1" },
  tipo_consulta: { id: 3, nome: "Consulta", duracao_min: 30 },
  pode_cancelar: true,
  pode_remarcar: true,
  chegada_em: null,
  pode_check_in: true,
  pode_faltou: false,
  ...extra,
});

function rotasFila(itens: unknown[] = [filaItem()]) {
  return [
    (url: string) => (url.endsWith("/fila/unidades") ? { corpo: UNIDADES } : undefined),
    (url: string) => (url.includes("/fila?") ? { corpo: itens } : undefined),
  ];
}

test("fila do dia lista as consultas com botões conforme as flags", async () => {
  mockFetch(
    ...rotasFila([
      filaItem(),
      filaItem({
        id: 2,
        paciente: { id: 9, nome: "Outro Paciente" },
        inicio: "2026-10-12T13:00:00Z",
        fim: "2026-10-12T13:30:00Z",
        pode_check_in: false,
        pode_faltou: true,
      }),
    ]),
  );
  renderizar(<FilaDoDia />);
  expect(await screen.findByText("Maria Paciente")).toBeInTheDocument();
  expect(screen.getByText("Outro Paciente")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Fazer check-in" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "Marcar falta" })).toHaveLength(1);
});

test("check-in na fila chama o endpoint e atualiza a lista", async () => {
  const fetch = mockFetch(
    ...rotasFila(),
    (url: string, init?: RequestInit) =>
      url.includes("/check-in") && init?.method === "POST" ? { corpo: filaItem({ status: "confirmada" }) } : undefined,
  );
  renderizar(<FilaDoDia />);
  await userEvent.click(await screen.findByRole("button", { name: "Fazer check-in" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([u, init]) => String(u).includes("/check-in") && init?.method === "POST")).toBe(true),
  );
});

test("fila recarrega sozinha a cada 30 segundos", async () => {
  vi.useFakeTimers();
  try {
    const fetch = mockFetch(...rotasFila());
    renderizar(<FilaDoDia />);
    // resolve a primeira busca sem depender de waitFor (que trava com fake timers)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    const antes = fetch.mock.calls.filter(([u]) => String(u).includes("/fila?")).length;
    expect(antes).toBeGreaterThan(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    const depois = fetch.mock.calls.filter(([u]) => String(u).includes("/fila?")).length;
    expect(depois).toBeGreaterThan(antes);
  } finally {
    vi.useRealTimers();
  }
});

test("erro de acesso à fila aparece em português", async () => {
  mockFetch(
    (url: string) => (url.endsWith("/fila/unidades") ? { corpo: UNIDADES } : undefined),
    (url: string) =>
      url.includes("/fila?")
        ? { status: 403, corpo: { detail: "Você não tem acesso à fila desta unidade." } }
        : undefined,
  );
  renderizar(<FilaDoDia />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Você não tem acesso à fila desta unidade.");
});

test("recepção sem unidades vinculadas vê o aviso", async () => {
  mockFetch((url: string) => (url.endsWith("/fila/unidades") ? { corpo: [] } : undefined));
  renderizar(<FilaDoDia />);
  expect(await screen.findByText("Nenhuma unidade vinculada ao seu acesso.")).toBeInTheDocument();
});

// ---------- ações de atendimento na agenda do profissional ----------

const consultaAgenda = (extra = {}) => ({
  id: 1,
  inicio: "2026-10-12T12:00:00Z",
  fim: "2026-10-12T12:30:00Z",
  status: "confirmada",
  forma_pagamento: "particular",
  preco_centavos: 25000,
  remarcacoes: 0,
  paciente: { id: 2, nome: "Maria Paciente" },
  profissional: { id: 10, nome: "Dr. João Souza" },
  unidade: { id: 5, nome: "Unidade Centro", endereco: "Rua A, 1" },
  tipo_consulta: { id: 3, nome: "Consulta", duracao_min: 30 },
  pode_cancelar: false,
  pode_remarcar: false,
  ...extra,
});

function rotasAgenda(consultas: unknown[] = [consultaAgenda()]) {
  return [
    (url: string) =>
      url.endsWith("/eu/profissional")
        ? { corpo: { id: 10, nome: "Dr. João Souza", unidades: [{ id: 5, nome: "Unidade Centro" }] } }
        : undefined,
    (url: string) => (url.includes("/profissionais/10/agenda") ? { corpo: consultas } : undefined),
  ];
}

async function abrirAgendaNaData() {
  renderizar(<AgendaProfissional />);
  await screen.findByLabelText("Data");
  fireEvent.change(screen.getByLabelText("Data"), { target: { value: "2026-10-12" } });
  await screen.findByText("Maria Paciente");
}

test("agenda oferece chamar para consulta confirmada e envia o POST", async () => {
  const fetch = mockFetch(
    ...rotasAgenda([consultaAgenda({ status: "confirmada" })]),
    (url: string, init?: RequestInit) =>
      url.includes("/chamar") && init?.method === "POST" ? { corpo: consultaAgenda({ status: "em_atendimento" }) } : undefined,
  );
  await abrirAgendaNaData();
  await userEvent.click(screen.getByRole("button", { name: "Chamar" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([u, init]) => String(u).includes("/chamar") && init?.method === "POST")).toBe(true),
  );
});

test("finalizar exige anotação e envia o texto digitado", async () => {
  const fetch = mockFetch(
    ...rotasAgenda([consultaAgenda({ status: "em_atendimento" })]),
    (url: string, init?: RequestInit) =>
      url.includes("/finalizar") && init?.method === "POST" ? { corpo: consultaAgenda({ status: "realizada" }) } : undefined,
  );
  await abrirAgendaNaData();
  await userEvent.click(screen.getByRole("button", { name: "Finalizar" }));
  const botao = screen.getByRole("button", { name: "Finalizar atendimento" });
  expect(botao).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Anotação do atendimento"), "Boa evolução.");
  expect(screen.getByText("13/5000")).toBeInTheDocument();
  expect(botao).toBeEnabled();
  await userEvent.click(botao);
  await waitFor(() =>
    expect(fetch.mock.calls.some(([u, init]) => String(u).includes("/finalizar") && init?.method === "POST")).toBe(true),
  );
  const post = fetch.mock.calls.find(([u, init]) => String(u).includes("/finalizar") && init?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ anotacao: "Boa evolução." });
});

test("erro do finalizar aparece em português", async () => {
  mockFetch(
    ...rotasAgenda([consultaAgenda({ status: "em_atendimento" })]),
    (url: string, init?: RequestInit) =>
      url.includes("/finalizar") && init?.method === "POST"
        ? { status: 422, corpo: { detail: "A anotação deve ter no máximo 5000 caracteres." } }
        : undefined,
  );
  await abrirAgendaNaData();
  await userEvent.click(screen.getByRole("button", { name: "Finalizar" }));
  await userEvent.type(screen.getByLabelText("Anotação do atendimento"), "teste");
  await userEvent.click(screen.getByRole("button", { name: "Finalizar atendimento" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("A anotação deve ter no máximo");
});

test("ver anotação de consulta realizada carrega da API", async () => {
  mockFetch(
    ...rotasAgenda([consultaAgenda({ status: "realizada" })]),
    (url: string) => (url.includes("/anotacao") ? { corpo: { anotacao: "Evolução boa." } } : undefined),
  );
  await abrirAgendaNaData();
  await userEvent.click(screen.getByRole("button", { name: "Ver anotação" }));
  expect(await screen.findByText("Evolução boa.")).toBeInTheDocument();
});

test("consulta marcada não mostra ações de atendimento", async () => {
  mockFetch(...rotasAgenda([consultaAgenda({ status: "marcada" })]));
  await abrirAgendaNaData();
  expect(screen.queryByRole("button", { name: "Chamar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Finalizar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Ver anotação" })).not.toBeInTheDocument();
});

// ---------- comprovante em minhas consultas ----------

function rotasMinhas(extra = {}) {
  return (url: string) =>
    url.endsWith("/consultas/minhas")
      ? {
          corpo: {
            proximas: [consultaAgenda({ status: "marcada", pode_cancelar: true, pode_remarcar: true })],
            passadas: [consultaAgenda({ id: 3, status: "realizada" })],
            ...extra,
          },
        }
      : undefined;
}

test("minhas consultas mostra comprovante somente para realizada", async () => {
  mockFetch(rotasMinhas());
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("tab", { name: "Passadas (1)" }));
  expect(screen.getByRole("button", { name: "Comprovante (PDF)" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Próximas (1)" }));
  expect(screen.queryByRole("button", { name: "Comprovante (PDF)" })).not.toBeInTheDocument();
});

test("comprovante baixa o PDF com o tipo do servidor", async () => {
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  mockFetch(
    rotasMinhas(),
    (url: string) =>
      url.endsWith("/comprovante.pdf")
        ? {
            texto: "%PDF-1.4 comprovante",
            cabecalhos: {
              "Content-Type": "application/pdf",
              "Content-Disposition": 'attachment; filename="comprovante-3.pdf"',
            },
          }
        : undefined,
  );
  renderizar(<MinhasConsultas />);
  await userEvent.click(await screen.findByRole("tab", { name: "Passadas (1)" }));
  await userEvent.click(screen.getByRole("button", { name: "Comprovante (PDF)" }));
  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
  expect(blob.type).toBe("application/pdf");
});

// ---------- vínculos da recepção (admin) ----------

test("admin liga e desliga unidades da recepção", async () => {
  const fetch = mockFetch(
    (url: string, init?: RequestInit) =>
      url.endsWith("/recepcao-unidades") && (init?.method === "POST" || init?.method === "DELETE")
        ? { corpo: { usuario: { id: 3, nome: "Rita", email: "rita@demo.com" }, unidade_ids: init.method === "POST" ? [5] : [] } }
        : undefined,
    (url: string) =>
      url.endsWith("/recepcao-unidades")
        ? { corpo: [{ usuario: { id: 3, nome: "Rita", email: "rita@demo.com" }, unidade_ids: [5] }] }
        : undefined,
    (url: string) => (url.endsWith("/fila/unidades") ? { corpo: UNIDADES } : undefined),
  );
  renderizar(<VinculosRecepcao />);
  expect(await screen.findByText("Rita")).toBeInTheDocument();
  const botao = screen.getByRole("button", { name: "Unidade Centro" });
  expect(botao).not.toHaveClass("secundario");
  await userEvent.click(botao);
  await waitFor(() =>
    expect(fetch.mock.calls.some(([u, init]) => String(u).includes("/recepcao-unidades") && init?.method === "DELETE")).toBe(true),
  );
});
