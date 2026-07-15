export type ScreenKey =
  | 'dashboard'
  | 'veiculos'
  | 'motoristas'
  | 'abastecimentos'
  | 'manutencoes'
  | 'despesas'
  | 'documentos'
  | 'relatorios'
  | 'configuracoes';

export type Vehicle = {
  id: string;
  placa: string;
  marca?: string | null;
  modelo?: string | null;
  ano?: number | null;
  tipo: 'caminhao' | 'carro' | 'moto' | 'utilitario' | 'outro';
  km_atual?: number | null;
  status: 'ativo' | 'inativo' | 'vendido' | 'manutencao';
};

export type Driver = {
  id: string;
  nome: string;
  cnh_numero?: string | null;
  cnh_categoria?: string | null;
  cnh_validade?: string | null;
  telefone?: string | null;
  status: 'ativo' | 'inativo';
};

export type FuelLog = {
  id: string;
  veiculo_id: string;
  motorista_id?: string | null;
  data: string;
  km: number;
  litros: number;
  valor_total: number;
  valor_litro?: number | null;
  tipo_combustivel?: string | null;
  posto?: string | null;
  veiculos?: Pick<Vehicle, 'placa' | 'modelo'> | null;
  motoristas?: Pick<Driver, 'nome'> | null;
};

export type Maintenance = {
  id: string;
  veiculo_id: string;
  tipo: 'preventiva' | 'corretiva';
  categoria: string;
  descricao: string;
  data: string;
  km?: number | null;
  valor: number;
  oficina?: string | null;
  status: 'agendada' | 'em_andamento' | 'concluida';
  proxima_data?: string | null;
  proxima_km?: number | null;
  veiculos?: Pick<Vehicle, 'placa'> | null;
};

export type Expense = {
  id: string;
  veiculo_id?: string | null;
  categoria: string;
  descricao: string;
  data: string;
  valor: number;
  vencimento?: string | null;
  status: 'pendente' | 'pago';
  veiculos?: Pick<Vehicle, 'placa'> | null;
};

export type DocumentRecord = {
  id: string;
  veiculo_id?: string | null;
  motorista_id?: string | null;
  tipo: string;
  descricao?: string | null;
  validade?: string | null;
  arquivo_path?: string | null;
  veiculos?: Pick<Vehicle, 'placa'> | null;
  motoristas?: Pick<Driver, 'nome'> | null;
};

export type AlertRecord = {
  tipo: string;
  referencia_id: string;
  veiculo_id?: string | null;
  titulo: string;
  vencimento?: string | null;
  dias_restantes: number;
  situacao: 'vencido' | 'vence_em_breve' | 'ok';
};

export type DashboardSummary = {
  veiculos_ativos?: number;
  motoristas_ativos?: number;
  custo_mes?: number;
  abastecimentos_mes?: number;
  manutencoes_pendentes?: number;
  alertas_abertos?: number;
};

export type ReportCost = {
  categoria: string;
  total: number;
};

export type Settings = {
  empresa_id?: string;
  dias_aviso_vencimento: number;
  km_aviso_manutencao: number;
};

export type FleetData = {
  dashboard: DashboardSummary;
  alerts: AlertRecord[];
  vehicles: Vehicle[];
  drivers: Driver[];
  fuelLogs: FuelLog[];
  maintenances: Maintenance[];
  expenses: Expense[];
  documents: DocumentRecord[];
  reportCosts: ReportCost[];
  settings: Settings;
};
