import { screen } from "@testing-library/react";
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
