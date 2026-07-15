import { emptyFleetData, mockFleetData } from '../data/mockData';
import type { FleetData, ScreenKey } from '../types';
import { ApiError, apiConfigured, apiFile, apiRequest, type ApiSession } from './api';

type Payload = Record<string, string | number | null | undefined>;

const resourceByScreen: Partial<Record<ScreenKey, string>> = {
  veiculos: 'veiculos',
  motoristas: 'motoristas',
  abastecimentos: 'abastecimentos',
  manutencoes: 'manutencoes',
  despesas: 'despesas',
  documentos: 'documentos'
};

export async function loadFleetData(session: ApiSession | null): Promise<{
  data: FleetData;
  warning?: string;
  unauthorized?: boolean;
}> {
  if (!apiConfigured || !session) return { data: mockFleetData };
  try {
    return { data: await apiRequest<FleetData>('/api/dados') };
  } catch (error) {
    return {
      data: emptyFleetData,
      warning: friendlyFleetError(error),
      unauthorized: error instanceof ApiError && error.status === 401
    };
  }
}

export async function saveRecord(screen: ScreenKey, payload: Payload, id?: string) {
  const resource = resourceByScreen[screen];
  if (!resource) return { data: null, error: new Error('Tela sem cadastro configurado.') };
  try {
    const data = await apiRequest(`/api/${resource}${id ? `/${id}` : ''}`, {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(cleanPayload(payload))
    });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function deleteRecord(screen: ScreenKey, id: string) {
  const resource = resourceByScreen[screen];
  if (!resource) return { data: null, error: new Error('Tela sem exclusao configurada.') };
  try {
    const data = await apiRequest<{ id: string }>(`/api/${resource}/${id}`, { method: 'DELETE' });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function updateSettings(_empresaId: string, payload: Payload) {
  try {
    const data = await apiRequest('/api/configuracoes', {
      method: 'PUT',
      body: JSON.stringify(cleanPayload(payload))
    });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function uploadDocument(file: File, _type: string, _userId: string) {
  const form = new FormData();
  form.append('arquivo', file);
  try {
    const data = await apiRequest<{ path: string }>('/api/arquivos', { method: 'POST', body: form });
    return { path: data.path, error: null };
  } catch (error) {
    return { path: null, error };
  }
}

export async function removeDocument(path: string) {
  try {
    await apiRequest(`/api/arquivos/${encodeURIComponent(path)}`, { method: 'DELETE' });
    return { error: null };
  } catch (error) {
    return { error };
  }
}

export async function getDocumentUrl(path: string) {
  try {
    const blob = await apiFile(`/api/arquivos/${encodeURIComponent(path)}`);
    return { data: { signedUrl: URL.createObjectURL(blob) }, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export function friendlyFleetError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Nao foi possivel concluir a acao.';
}

function cleanPayload(payload: Payload) {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined && value !== ''));
}
