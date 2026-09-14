export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type ClientOptions = {
  baseUrl: string;
  getToken: () => string | null;
  onUnauthorized?: () => void;
};

export interface ApiRequest {
  <T = any>(path: string, init?: RequestInit): Promise<T>;
  raw?(path: string, init?: RequestInit): Promise<Response>;
}

export function createApiClient(options: ClientOptions) {
  async function raw(path: string, init: RequestInit = {}): Promise<Response> {
    const token = options.getToken();
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${options.baseUrl}${path}`, { ...init, headers });
    if (response.status === 401) options.onUnauthorized?.();
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: "Request failed" }));
      const detail = typeof body.detail === "string" ? body.detail : "Request failed";
      throw new ApiError(response.status, detail);
    }
    return response;
  }
  const request = async function request<T = any>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await raw(path, init);
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } as ApiRequest;
  request.raw=raw;
  return request;
}
