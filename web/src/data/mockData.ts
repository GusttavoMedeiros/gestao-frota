import type { FleetData } from '../types';

export const emptyFleetData: FleetData = {
  dashboard: {},
  alerts: [],
  vehicles: [],
  drivers: [],
  fuelLogs: [],
  maintenances: [],
  expenses: [],
  documents: [],
  reportCosts: [],
  settings: {
    dias_aviso_vencimento: 30,
    km_aviso_manutencao: 1000
  }
};

export const mockFleetData: FleetData = {
  dashboard: {
    veiculos_ativos: 18,
    motoristas_ativos: 12,
    custo_mes: 84320,
    abastecimentos_mes: 147,
    manutencoes_pendentes: 5,
    alertas_abertos: 9
  },
  alerts: [
    {
      tipo: 'documento',
      referencia_id: 'alerta-1',
      veiculo_id: 'v1',
      titulo: 'CRLV 2026 - KGF1A23',
      vencimento: '2026-07-10',
      dias_restantes: 14,
      situacao: 'vence_em_breve'
    },
    {
      tipo: 'manutencao',
      referencia_id: 'alerta-2',
      veiculo_id: 'v2',
      titulo: 'Troca de oleo - KGF7B80',
      vencimento: '2026-06-24',
      dias_restantes: -2,
      situacao: 'vencido'
    },
    {
      tipo: 'despesa',
      referencia_id: 'alerta-3',
      veiculo_id: 'v3',
      titulo: 'Seguro mensal pendente',
      vencimento: '2026-07-03',
      dias_restantes: 7,
      situacao: 'vence_em_breve'
    }
  ],
  vehicles: [
    {
      id: 'v1',
      placa: 'KGF1A23',
      marca: 'Volkswagen',
      modelo: 'Delivery 11.180',
      ano: 2022,
      tipo: 'caminhao',
      km_atual: 84210,
      status: 'ativo'
    },
    {
      id: 'v2',
      placa: 'KGF7B80',
      marca: 'Mercedes-Benz',
      modelo: 'Accelo 815',
      ano: 2020,
      tipo: 'caminhao',
      km_atual: 154300,
      status: 'manutencao'
    },
    {
      id: 'v3',
      placa: 'KGF4C11',
      marca: 'Fiat',
      modelo: 'Fiorino',
      ano: 2023,
      tipo: 'utilitario',
      km_atual: 31280,
      status: 'ativo'
    }
  ],
  drivers: [
    {
      id: 'm1',
      nome: 'Carlos Andrade',
      cnh_numero: '04892738111',
      cnh_categoria: 'D',
      cnh_validade: '2027-03-12',
      telefone: '(31) 99931-2201',
      status: 'ativo'
    },
    {
      id: 'm2',
      nome: 'Marcos Lima',
      cnh_numero: '01928477102',
      cnh_categoria: 'C',
      cnh_validade: '2026-07-18',
      telefone: '(31) 98882-0144',
      status: 'ativo'
    }
  ],
  fuelLogs: [
    {
      id: 'a1',
      veiculo_id: 'v2',
      motorista_id: 'm1',
      data: '2026-06-25',
      km: 154300,
      litros: 180.5,
      valor_total: 1100.5,
      valor_litro: 6.097,
      tipo_combustivel: 'diesel_s10',
      posto: 'Posto BR Gloria',
      veiculos: { placa: 'KGF7B80', modelo: 'Accelo 815' },
      motoristas: { nome: 'Carlos Andrade' }
    },
    {
      id: 'a2',
      veiculo_id: 'v1',
      motorista_id: 'm2',
      data: '2026-06-24',
      km: 84210,
      litros: 112,
      valor_total: 683.2,
      valor_litro: 6.1,
      tipo_combustivel: 'diesel',
      posto: 'Auto Posto Avenida',
      veiculos: { placa: 'KGF1A23', modelo: 'Delivery 11.180' },
      motoristas: { nome: 'Marcos Lima' }
    }
  ],
  maintenances: [
    {
      id: 'ma1',
      veiculo_id: 'v2',
      tipo: 'preventiva',
      categoria: 'oleo',
      descricao: 'Troca de oleo e filtros',
      data: '2026-06-24',
      km: 154300,
      valor: 1280,
      oficina: 'Oficina Central',
      status: 'agendada',
      proxima_km: 164300,
      veiculos: { placa: 'KGF7B80' }
    }
  ],
  expenses: [
    {
      id: 'd1',
      veiculo_id: 'v3',
      categoria: 'seguro',
      descricao: 'Parcela seguro frota',
      data: '2026-06-10',
      valor: 1850,
      vencimento: '2026-07-03',
      status: 'pendente',
      veiculos: { placa: 'KGF4C11' }
    },
    {
      id: 'd2',
      veiculo_id: 'v1',
      categoria: 'pedagio',
      descricao: 'Pedagios rota Contagem',
      data: '2026-06-20',
      valor: 238.9,
      status: 'pago',
      veiculos: { placa: 'KGF1A23' }
    }
  ],
  documents: [
    {
      id: 'doc1',
      veiculo_id: 'v1',
      tipo: 'crlv',
      descricao: 'CRLV 2026',
      validade: '2026-07-10',
      arquivo_path: null,
      veiculos: { placa: 'KGF1A23' }
    },
    {
      id: 'doc2',
      motorista_id: 'm2',
      tipo: 'cnh',
      descricao: 'CNH Marcos Lima',
      validade: '2026-07-18',
      arquivo_path: null,
      motoristas: { nome: 'Marcos Lima' }
    }
  ],
  reportCosts: [
    { categoria: 'Combustivel', total: 38540 },
    { categoria: 'Manutencao', total: 18400 },
    { categoria: 'Despesas', total: 27380 }
  ],
  settings: {
    dias_aviso_vencimento: 30,
    km_aviso_manutencao: 1000
  }
};
