export type Notificacao = {
  id: number;
  tipo: "consulta_marcada" | "consulta_remarcada" | "consulta_cancelada";
  titulo: string;
  texto: string;
  consulta_id: number | null;
  lida_em: string | null;
  criado_em: string;
};

export type ListaNotificacoes = {
  itens: Notificacao[];
  total: number;
  pagina: number;
  paginas: number;
  nao_lidas: number;
};
