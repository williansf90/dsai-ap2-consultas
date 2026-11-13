import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/shared/api";
import { formatarDataHora } from "@/shared/datas";
import type { ListaNotificacoes, Notificacao } from "./tipos";

const POR_PAGINA = 20;

/** Central de notificações do paciente: listar, marcar como lida (no clique) e marcar todas. */
export default function CentralNotificacoes() {
  const [pagina, setPagina] = useState(1);
  const queryClient = useQueryClient();
  const navegar = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["notificacoes", "lista", pagina],
    queryFn: () => api<ListaNotificacoes>(`/notificacoes?pagina=${pagina}&por_pagina=${POR_PAGINA}`),
  });
  const marcarTodas = useMutation({
    mutationFn: () => api<{ atualizadas: number }>("/notificacoes/marcar-todas-lidas", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notificacoes"] }),
  });
  const marcarLida = useMutation({
    mutationFn: (id: number) => api<Notificacao>(`/notificacoes/${id}/lida`, { method: "PATCH" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notificacoes"] }),
  });

  const abrir = (notificacao: Notificacao) => {
    if (!notificacao.lida_em) marcarLida.mutate(notificacao.id);
    navegar("/minhas-consultas");
  };

  const lista = data?.itens ?? [];
  return (
    <section>
      <h1>Notificações</h1>
      <p className="acoes">
        <button
          className="secundario"
          disabled={(data?.nao_lidas ?? 0) === 0 || marcarTodas.isPending}
          onClick={() => marcarTodas.mutate()}
        >
          Marcar todas como lidas
        </button>
      </p>
      {isLoading && <p className="suave">Carregando…</p>}
      {error && (
        <p role="alert" className="erro">
          {(error as Error).message}
        </p>
      )}
      {(marcarTodas.error || marcarLida.error) && (
        <p role="alert" className="erro">
          {((marcarTodas.error ?? marcarLida.error) as Error).message}
        </p>
      )}
      {data && lista.length === 0 && <p className="suave">Nenhuma notificação.</p>}
      {lista.map((n) => (
        <button
          key={n.id}
          type="button"
          className={`cartao notificacao${n.lida_em ? "" : " nao-lida"}`}
          onClick={() => abrir(n)}
        >
          <span className="notificacao-titulo">{n.titulo}</span>
          <span className="suave">{formatarDataHora(n.criado_em)}</span>
          <span className="notificacao-texto">{n.texto}</span>
        </button>
      ))}
      {data && data.paginas > 1 && (
        <p className="acoes">
          <button className="secundario" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
            Anterior
          </button>
          <span className="suave">
            Página {data.pagina} de {data.paginas}
          </span>
          <button className="secundario" disabled={pagina >= data.paginas} onClick={() => setPagina(pagina + 1)}>
            Próxima
          </button>
        </p>
      )}
    </section>
  );
}
