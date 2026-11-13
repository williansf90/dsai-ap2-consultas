export type FilaItem = {
  id: number;
  inicio: string;
  fim: string;
  status: string;
  forma_pagamento: string;
  preco_centavos: number;
  remarcacoes: number;
  paciente: { id: number; nome: string };
  profissional: { id: number; nome: string };
  unidade: { id: number; nome: string; endereco: string };
  tipo_consulta: { id: number; nome: string; duracao_min: number };
  pode_cancelar: boolean;
  pode_remarcar: boolean;
  chegada_em: string | null;
  pode_check_in: boolean;
  pode_faltou: boolean;
};

export type UnidadeRef = { id: number; nome: string; endereco: string };

export type VinculoRecepcao = {
  usuario: { id: number; nome: string; email: string };
  unidade_ids: number[];
};
