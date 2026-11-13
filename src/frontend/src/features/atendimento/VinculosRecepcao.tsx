import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api";
import type { UnidadeRef, VinculoRecepcao } from "./tipos";

/** Admin: liga e desliga o acesso das recepções às unidades (fila do dia). */
export default function VinculosRecepcao() {
  const queryClient = useQueryClient();
  const { data: vinculos, isLoading, error } = useQuery({
    queryKey: ["recepcao-unidades"],
    queryFn: () => api<VinculoRecepcao[]>("/recepcao-unidades"),
  });
  const { data: unidades } = useQuery({
    queryKey: ["fila", "unidades"],
    queryFn: () => api<UnidadeRef[]>("/fila/unidades"),
  });
  const alterar = useMutation({
    mutationFn: (corpo: { usuario_id: number; unidade_id: number; ligada: boolean }) =>
      api("/recepcao-unidades", {
        method: corpo.ligada ? "DELETE" : "POST",
        body: JSON.stringify({ usuario_id: corpo.usuario_id, unidade_id: corpo.unidade_id }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recepcao-unidades"] }),
  });

  return (
    <section>
      <h1>Vínculos da recepção</h1>
      <p className="suave">Clique numa unidade para conceder ou remover o acesso da recepção à fila do dia.</p>
      {isLoading && <p className="suave">Carregando…</p>}
      {error && (
        <p role="alert" className="erro">
          {(error as Error).message}
        </p>
      )}
      {alterar.error && (
        <p role="alert" className="erro">
          {(alterar.error as Error).message}
        </p>
      )}
      {(vinculos ?? []).map((v) => (
        <article key={v.usuario.id} className="cartao">
          <p>
            <strong>{v.usuario.nome}</strong> <span className="suave">{v.usuario.email}</span>
          </p>
          <p className="acoes">
            {(unidades ?? []).map((u) => {
              const ligada = v.unidade_ids.includes(u.id);
              return (
                <button
                  key={u.id}
                  className={ligada ? "" : "secundario"}
                  disabled={alterar.isPending}
                  onClick={() => alterar.mutate({ usuario_id: v.usuario.id, unidade_id: u.id, ligada })}
                >
                  {u.nome}
                </button>
              );
            })}
          </p>
        </article>
      ))}
    </section>
  );
}
