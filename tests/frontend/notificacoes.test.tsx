import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router-dom";
import CentralNotificacoes from "@/features/notificacoes/CentralNotificacoes";
import Layout from "@/shared/Layout";
import { mockFetch, renderizar } from "./apoio";

const TOKENS = { access_token: "access-1", refresh_token: "refresh-1" };
const PACIENTE = { id: 2, nome: "Maria", email: "maria@teste.com", perfil: "paciente" };
const RECEPCAO = { id: 3, nome: "Rita", email: "rita@teste.com", perfil: "recepcao" };

function entrarComo(usuario: typeof PACIENTE) {
  localStorage.setItem("marcaconsulta.tokens", JSON.stringify(TOKENS));
  mockFetch((url: string) => (url.endsWith("/auth/eu") ? { corpo: usuario } : undefined));
}

function rotasDoSino(naoLidas: number) {
  return [
    (url: string) => (url.endsWith("/auth/eu") ? { corpo: PACIENTE } : undefined),
    (url: string) =>
      url.includes("/notificacoes")
        ? { corpo: { itens: [], total: 0, pagina: 1, paginas: 1, nao_lidas: naoLidas } }
        : undefined,
  ];
}

test("sino do cabeçalho mostra o contador de não lidas e leva à central", async () => {
  localStorage.setItem("marcaconsulta.tokens", JSON.stringify(TOKENS));
  mockFetch(...rotasDoSino(3));
  renderizar(<Layout />);
  const sino = await screen.findByRole("link", { name: "Notificações: 3 não lidas" });
  expect(sino).toHaveAttribute("href", "/notificacoes");
  expect(sino).toHaveTextContent("3");
});

test("sino com mais de 9 não lidas mostra 9+", async () => {
  localStorage.setItem("marcaconsulta.tokens", JSON.stringify(TOKENS));
  mockFetch(...rotasDoSino(12));
  renderizar(<Layout />);
  expect(await screen.findByRole("link", { name: "Notificações: 12 não lidas" })).toHaveTextContent("9+");
});

test("sino sem não lidas não mostra contador", async () => {
  localStorage.setItem("marcaconsulta.tokens", JSON.stringify(TOKENS));
  mockFetch(...rotasDoSino(0));
  renderizar(<Layout />);
  const sino = await screen.findByRole("link", { name: "Notificações" });
  expect(sino.querySelector(".sino-contador")).toBeNull();
});

test("sino não aparece para outros perfis", async () => {
  entrarComo(RECEPCAO);
  renderizar(<Layout />);
  await screen.findByText("Rita");
  expect(screen.queryByRole("link", { name: /notificações/i })).not.toBeInTheDocument();
});

test("sino não aparece deslogado", () => {
  mockFetch();
  renderizar(<Layout />);
  expect(screen.getByRole("link", { name: "Entrar" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /notificações/i })).not.toBeInTheDocument();
});

// ---------- central de notificações ----------

const notificacao = (extra = {}) => ({
  id: 1,
  tipo: "consulta_marcada",
  titulo: "Consulta marcada",
  texto: "Sua consulta com Dr. João Souza foi marcada para 12/10/2026.",
  consulta_id: 7,
  lida_em: null,
  criado_em: "2026-10-12T12:00:00Z",
  ...extra,
});

const lista = (extra = {}) => ({
  itens: [notificacao()],
  total: 1,
  pagina: 1,
  paginas: 1,
  nao_lidas: 1,
  ...extra,
});

function rotasDaCentral(corpo: unknown) {
  return (url: string) => (url.includes("/notificacoes?") ? { corpo } : undefined);
}

function renderizarCentral(comExtras = true) {
  return renderizar(<CentralNotificacoes />, {
    rota: "/notificacoes",
    caminho: "/notificacoes",
    extras: comExtras ? [<Route path="/minhas-consultas" element={<p>Minhas consultas</p>} />] : [],
  });
}

test("central lista notificações e destaca as não lidas", async () => {
  mockFetch(
    rotasDaCentral(
      lista({
        itens: [notificacao(), notificacao({ id: 2, titulo: "Consulta remarcada", lida_em: "2026-10-12T13:00:00Z" })],
        nao_lidas: 1,
      }),
    ),
  );
  renderizarCentral(false);
  const naoLida = await screen.findByRole("button", { name: /Consulta marcada/ });
  const lida = screen.getByRole("button", { name: /Consulta remarcada/ });
  expect(naoLida).toHaveClass("nao-lida");
  expect(lida).not.toHaveClass("nao-lida");
  expect(lida).toHaveTextContent("12/10/2026");
});

test("central vazia mostra mensagem e desabilita marcar todas", async () => {
  mockFetch(rotasDaCentral(lista({ itens: [], total: 0, nao_lidas: 0 })));
  renderizarCentral(false);
  expect(await screen.findByText("Nenhuma notificação.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Marcar todas como lidas" })).toBeDisabled();
});

test("clique na notificação marca como lida e vai para minhas consultas", async () => {
  const fetch = mockFetch(
    rotasDaCentral(lista()),
    (url: string, init?: RequestInit) =>
      url.includes("/notificacoes/1/lida") && init?.method === "PATCH"
        ? { corpo: notificacao({ lida_em: "2026-10-12T13:00:00Z" }) }
        : undefined,
  );
  renderizarCentral();
  await userEvent.click(await screen.findByRole("button", { name: /Consulta marcada/ }));
  expect(await screen.findByText("Minhas consultas")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true);
});

test("clique em notificação já lida não dispara PATCH", async () => {
  const fetch = mockFetch(
    rotasDaCentral(lista({ itens: [notificacao({ lida_em: "2026-10-12T13:00:00Z" })], nao_lidas: 0 })),
  );
  renderizarCentral();
  await userEvent.click(await screen.findByRole("button", { name: /Consulta marcada/ }));
  expect(await screen.findByText("Minhas consultas")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
});

test("marcar todas como lidas chama o endpoint e atualiza", async () => {
  const fetch = mockFetch(
    rotasDaCentral(lista()),
    (url: string, init?: RequestInit) =>
      url.includes("/notificacoes/marcar-todas-lidas") && init?.method === "POST"
        ? { corpo: { atualizadas: 1 } }
        : undefined,
  );
  renderizarCentral(false);
  await userEvent.click(await screen.findByRole("button", { name: "Marcar todas como lidas" }));
  await waitFor(() => expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
});

test("erro da central aparece em português", async () => {
  mockFetch((url: string) =>
    url.includes("/notificacoes?")
      ? { status: 500, corpo: { detail: "Erro no servidor. Tente novamente em instantes." } }
      : undefined,
  );
  renderizarCentral(false);
  expect(await screen.findByRole("alert")).toHaveTextContent("Erro no servidor");
});

test("paginação busca a próxima página", async () => {
  const fetch = mockFetch((url: string) => {
    if (!url.includes("/notificacoes?")) return undefined;
    return url.includes("pagina=2&")
      ? { corpo: lista({ itens: [notificacao({ id: 99, titulo: "Consulta cancelada" })], pagina: 2, paginas: 2, total: 2 }) }
      : { corpo: lista({ pagina: 1, paginas: 2, total: 2 }) };
  });
  renderizarCentral(false);
  await userEvent.click(await screen.findByRole("button", { name: "Próxima" }));
  expect(await screen.findByRole("button", { name: /Consulta cancelada/ })).toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => String(u).includes("pagina=2&"))).toBe(true);
});
