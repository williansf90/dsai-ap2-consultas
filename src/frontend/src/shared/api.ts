export class ErroApi extends Error {
  constructor(
    public status: number,
    mensagem: string,
    public dados: Record<string, unknown> = {},
  ) {
    super(mensagem);
  }
}

const CHAVE_TOKENS = "marcaconsulta.tokens";

export type Tokens = { access_token: string; refresh_token: string };

export function lerTokens(): Tokens | null {
  try {
    const bruto = localStorage.getItem(CHAVE_TOKENS);
    return bruto ? (JSON.parse(bruto) as Tokens) : null;
  } catch {
    return null;
  }
}

export function salvarTokens(tokens: Tokens | null) {
  try {
    if (tokens) localStorage.setItem(CHAVE_TOKENS, JSON.stringify(tokens));
    else localStorage.removeItem(CHAVE_TOKENS);
  } catch {
    /* armazenamento indisponível: segue sem guardar a sessão */
  }
}

function mensagemDeErro(status: number, corpo: unknown): string {
  const detail = (corpo as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Dados inválidos. Confira os campos.";
  if (status >= 500) return "Erro no servidor. Tente novamente em instantes.";
  return "Não foi possível concluir a operação.";
}

async function renovar(): Promise<boolean> {
  const tokens = lerTokens();
  if (!tokens) return false;
  const r = await fetch("/api/auth/renovar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!r.ok) {
    salvarTokens(null);
    return false;
  }
  const novo = (await r.json()) as { access_token: string };
  salvarTokens({ ...tokens, access_token: novo.access_token });
  return true;
}

export async function api<T>(caminho: string, opcoes: RequestInit = {}, tentarRenovar = true): Promise<T> {
  const tokens = lerTokens();
  const headers = new Headers(opcoes.headers);
  if (opcoes.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  const r = await fetch(`/api${caminho}`, { ...opcoes, headers });
  if (r.status === 401 && tokens && tentarRenovar && (await renovar())) {
    return api<T>(caminho, opcoes, false);
  }
  const corpo = r.status === 204 ? null : await r.json().catch(() => null);
  if (!r.ok) throw new ErroApi(r.status, mensagemDeErro(r.status, corpo), (corpo ?? {}) as Record<string, unknown>);
  return corpo as T;
}

function headersAutorizados(): Headers {
  const tokens = lerTokens();
  const headers = new Headers();
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  return headers;
}

/**
 * Baixa um arquivo (resposta não-JSON) reutilizando o fluxo de autenticação do `api()`:
 * em 401, renova o token e repete a requisição uma única vez.
 */
export async function apiDownload(caminho: string): Promise<{ blob: Blob; texto: string; nomeArquivo: string }> {
  let r = await fetch(`/api${caminho}`, { headers: headersAutorizados() });
  if (r.status === 401 && lerTokens() && (await renovar())) {
    r = await fetch(`/api${caminho}`, { headers: headersAutorizados() });
  }
  if (!r.ok) {
    const corpo = await r.json().catch(() => null);
    throw new ErroApi(r.status, mensagemDeErro(r.status, corpo), (corpo ?? {}) as Record<string, unknown>);
  }
  const texto = await r.text();
  const disposicao = r.headers.get("Content-Disposition") ?? "";
  const casado = /filename="?([^";]+)"?/.exec(disposicao);
  return {
    blob: new Blob([texto], { type: r.headers.get("Content-Type") ?? "application/octet-stream" }),
    texto,
    nomeArquivo: casado?.[1] ?? "arquivo",
  };
}

/** Dispara o download de um Blob no navegador. */
export function salvarBlob(blob: Blob, nomeArquivo: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
