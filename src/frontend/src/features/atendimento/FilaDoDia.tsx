import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ROTULO_STATUS } from "@/features/agendamento/tipos";
import { api } from "@/shared/api";
import { diaLocal, formatarHora } from "@/shared/datas";
import type { FilaItem, UnidadeRef } from "./tipos";

/** Fila do dia da recepção: consultas por unidade, com check-in e falta. Atualiza a cada 30 s. */
export default function FilaDoDia() {
  const queryClient = useQueryClient();
  const [dia, setDia] = useState(() => diaLocal(new Date().toISOString()));
  const [unidadeId, setUnidadeId] = useState<number | null>(null);
  const { data: unidades } = useQuery({
    queryKey: ["fila", "unidades"],
    queryFn: () => api<UnidadeRef[]>("/fila/unidades"),
  });
  const unidade = unidadeId ?? unidades?.[0]?.id;
  const { data: itens, isLoading, error } = useQuery({
    queryKey: ["fila", unidade, dia],
    queryFn: () => api<FilaItem[]>(`/fila?unidade_id=${unidade}&data=${dia}`),
    enabled: unidade !== undefined,
    refetchInterval: 30_000,
  });
  const checkIn = useMutation({
    mutationFn: (id: number) => api(`/consultas/${id}/check-in`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["fila"] }),
  });
  const faltou = useMutation({
    mutationFn: (id: number) => api(`/consultas/${id}/faltou`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["fila"] }),
  });

  return (
    <section>
      <h1>Fila do dia</h1>
      <div className="acoes">
        <select
          aria-label="Unidade"
          value={unidade ?? ""}
          onChange={(e) => setUnidadeId(Number(e.target.value))}
        >
          {(unidades ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.nome}
            </option>
          ))}
        </select>
        <input type="date" aria-label="Data" value={dia} onChange={(e) => e.target.value && setDia(e.target.value)} />
      </div>
      {unidades && unidades.length === 0 && (
        <p className="suave">Nenhuma unidade vinculada ao seu acesso.</p>
      )}
      {isLoading && <p className="suave">Carregando…</p>}
      {error && (
        <p role="alert" className="erro">
          {(error as Error).message}
        </p>
      )}
      {(checkIn.error || faltou.error) && (
        <p role="alert" className="erro">
          {((checkIn.error ?? faltou.error) as Error).message}
        </p>
      )}
      {itens && itens.length === 0 && !isLoading && <p className="suave">Nenhuma consulta neste dia.</p>}
      <ul>
        {itens?.map((item) => (
          <li key={item.id} className="cartao">
            <p className="acoes">
              <strong>
                {formatarHora(item.inicio)}–{formatarHora(item.fim)}
              </strong>
              <span>{item.paciente.nome}</span>
              <span className="suave">
                {item.profissional.nome} · {item.tipo_consulta.nome}
              </span>
              <span className={`status status-${item.status}`}>{ROTULO_STATUS[item.status] ?? item.status}</span>
            </p>
            {item.chegada_em && <p className="suave">Chegada: {formatarHora(item.chegada_em)}</p>}
            <p className="acoes">
              {item.pode_check_in && (
                <button disabled={checkIn.isPending} onClick={() => checkIn.mutate(item.id)}>
                  Fazer check-in
                </button>
              )}
              {item.pode_faltou && (
                <button
                  className="secundario"
                  disabled={faltou.isPending}
                  onClick={() => {
                    if (window.confirm("Marcar falta nesta consulta?")) faltou.mutate(item.id);
                  }}
                >
                  Marcar falta
                </button>
              )}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
