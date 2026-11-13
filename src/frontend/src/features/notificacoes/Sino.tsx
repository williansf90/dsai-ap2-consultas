import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/shared/api";
import type { ListaNotificacoes } from "./tipos";

/** Sino do cabeçalho com o total de não lidas; leva à central. */
export default function Sino() {
  const { data } = useQuery({
    queryKey: ["notificacoes", "contagem"],
    queryFn: () => api<ListaNotificacoes>("/notificacoes?pagina=1&por_pagina=1"),
    refetchInterval: 60_000,
  });
  const naoLidas = data?.nao_lidas ?? 0;
  return (
    <Link
      to="/notificacoes"
      className="sino"
      aria-label={naoLidas ? `Notificações: ${naoLidas} não lidas` : "Notificações"}
    >
      <span aria-hidden="true">🔔</span>
      {naoLidas > 0 && <span className="sino-contador">{naoLidas > 9 ? "9+" : naoLidas}</span>}
    </Link>
  );
}
