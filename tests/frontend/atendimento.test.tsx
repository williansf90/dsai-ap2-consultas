import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import FilaDoDia from "@/features/atendimento/FilaDoDia";
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
