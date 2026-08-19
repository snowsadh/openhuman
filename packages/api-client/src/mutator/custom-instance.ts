const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, statusText: string, body: string) {
    super(statusText);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("oh_token");
  }
  return null;
}

export const customInstance = async <T>(
  config: {
    url: string;
    method: string;
    headers?: Record<string, string>;
    params?: unknown;
    data?: unknown;
    signal?: AbortSignal;
  },
  options?: RequestInit & {
    next?: { revalidate?: number; tags?: string[] };
  },
): Promise<T> => {
  const { url, method, headers: configHeaders, params, data, signal } = config;

  const token = getAuthToken();

  let queryParams = "";
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
      if (value !== undefined && value !== null) {
        if (Array.isArray(value)) {
          value.forEach((v) => {
            if (v !== undefined && v !== null) {
              searchParams.append(key, String(v));
            }
          });
        } else {
          searchParams.append(key, String(value));
        }
      }
    }
    const str = searchParams.toString();
    if (str) {
      queryParams = `?${str}`;
    }
  }

  const mergedHeaders: Record<string, string> = {
    ...(data instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...configHeaders,
    ...(options?.headers as Record<string, string> | undefined),
  };

  if (data instanceof FormData) {
    const keysToDelete = Object.keys(mergedHeaders).filter(
      (k) => k.toLowerCase() === "content-type"
    );
    for (const key of keysToDelete) {
      delete mergedHeaders[key];
    }
  }

  const response = await fetch(`${API_BASE_URL}${url}${queryParams}`, {
    ...options,
    method,
    signal,
    headers: mergedHeaders,
    body: data instanceof FormData ? data : data ? JSON.stringify(data) : undefined,
  });

  if (response.status === 401 && !url.startsWith("/api/auth/")) {
    const errorBody = await response.text().catch(() => "");
    throw new ApiError(401, "Unauthorized", errorBody || "Session expired");
  }

  if (!response.ok) {
    const errorBody = await response.text();
    throw new ApiError(
      response.status,
      response.statusText,
      errorBody,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    return text as T;
  }

  return response.json() as Promise<T>;
};

export default customInstance;
