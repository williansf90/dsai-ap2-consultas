import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Consulta } from "@/features/agendamento/tipos";
import { api } from "@/shared/api";

const MAX_ANOTACAO = 5000;

/** Ações de atendimento da agenda do profissional: chamar, finalizar (com anotação) e ver anotação. */
export default function AcoesAtendimento({ consulta }: { consulta: Consulta }) {
  const queryClient = useQueryClient();
  const [aberto, setAberto] = useState(false);
  const [anotacao, setAnotacao] = useState("");
  const chamar = useMutation({
    mutationFn: () => api<Consulta>(`/consultas/${consulta.id}/chamar`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agenda"] }),
  });
  const finalizar = useMutation({
    mutationFn: () =>
      api<Consulta>(`/consultas/${consulta.id}/finalizar`, { method: "POST", body: JSON.stringify({ anotacao }) }),
    onSuccess: () => {
      setAberto(false);
      setAnotacao("");
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
    },
  });
  const consultaAnotacao = useQuery({
    queryKey: ["agenda", "anotacao", consulta.id],
    queryFn: () => api<{ anotacao: string | null }>(`/consultas/${consulta.id}/anotacao`),
    enabled: aberto && consulta.status === "realizada",
  });

  if (consulta.status === "confirmada") {
    return (
      <span className="acoes">
        <button disabled={chamar.isPending} onClick={() => chamar.mutate()}>
          Chamar
        </button>
        {chamar.error && (
          <span role="alert" className="erro">
            {(chamar.error as Error).message}
          </span>
        )}
      </span>
    );
  }
  if (consulta.status === "em_atendimento") {
    return (
      <span className="acoes">
        {aberto ? (
          <>
            <textarea
              aria-label="Anotação do atendimento"
              value={anotacao}
              maxLength={MAX_ANOTACAO}
              onChange={(e) => setAnotacao(e.target.value)}
            />
            <span className="suave">
              {anotacao.length}/{MAX_ANOTACAO}
            </span>
            <button disabled={finalizar.isPending || anotacao.trim() === ""} onClick={() => finalizar.mutate()}>
              Finalizar atendimento
            </button>
            <button className="secundario" onClick={() => setAberto(false)}>
              Cancelar
            </button>
          </>
        ) : (
          <button onClick={() => setAberto(true)}>Finalizar</button>
        )}
        {finalizar.error && (
          <span role="alert" className="erro">
            {(finalizar.error as Error).message}
          </span>
        )}
      </span>
    );
  }
  if (consulta.status === "realizada") {
    return (
      <span className="acoes">
        <button className="secundario" onClick={() => setAberto((v) => !v)}>
          {aberto ? "Ocultar anotação" : "Ver anotação"}
        </button>
        {aberto && consultaAnotacao.isLoading && <span className="suave">Carregando…</span>}
        {aberto && consultaAnotacao.data && <span>{consultaAnotacao.data.anotacao ?? "Sem anotação."}</span>}
        {aberto && consultaAnotacao.error && (
          <span role="alert" className="erro">
            {(consultaAnotacao.error as Error).message}
          </span>
        )}
      </span>
    );
  }
  return null;
}
