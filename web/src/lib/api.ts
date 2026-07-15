export type ApiSession = {
  user: { id: string; name: string };
};

type ApiErrorBody = { erro?: string };

const apiUrl = ((import.meta.env.VITE_API_URL as string | undefined) || '').replace(/\/$/, '');
const tokenKey = 'kg-frota-token';

export const apiConfigured = true;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function getApiSession(): Promise<ApiSession | null> {
  if (!apiConfigured || !localStorage.getItem(tokenKey)) return null;
  try {
    const data = await apiRequest<{ usuario: { id: string; nome: string } }>('/api/sessao');
    return { user: { id: data.usuario.id, name: data.usuario.nome } };
  } catch {
    logoutApi();
    return null;
  }
}

export async function loginApi(username: string, password: string): Promise<ApiSession> {
  const data = await apiRequest<{ token: string; usuario: { id: string; nome: string } }>('/api/login', {
    method: 'POST',
    body: JSON.stringify({ usuario: username, senha: password }),
    skipAuth: true
  });
  localStorage.setItem(tokenKey, data.token);
  return { user: { id: data.usuario.id, name: data.usuario.nome } };
}

export function logoutApi() {
  localStorage.removeItem(tokenKey);
}

export async function apiRequest<T>(path: string, options: RequestInit & { skipAuth?: boolean } = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!options.skipAuth) {
    const token = localStorage.getItem(tokenKey);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${apiUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(body.erro || 'Nao foi possivel concluir a acao.', response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiFile(path: string): Promise<Blob> {
  const token = localStorage.getItem(tokenKey);
  const response = await fetch(`${apiUrl}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined
  });
  if (!response.ok) throw new ApiError('Arquivo nao encontrado.', response.status);
  return response.blob();
}
