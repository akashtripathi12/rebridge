import { z } from "zod";
import { config } from "./config";
import { authProvider } from "./auth";

/** Error carrying the HTTP status so callers can branch (404/409/etc.). */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Method = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions<T> {
  method?: Method;
  body?: unknown;
  schema?: z.ZodType<T>;
  /** Skip auth header (public routes like /cards/{id}/verify, /healthz). */
  public?: boolean;
  query?: Record<string, string | number | undefined>;
}

/**
 * Single fetch seam for every LIVE call. Attaches the bearer from authProvider,
 * parses + validates the response with the endpoint's Zod schema, and maps
 * non-2xx to ApiError(status). Mock services never go through here.
 */
export async function apiFetch<T>(
  path: string,
  opts: RequestOptions<T> = {},
): Promise<T> {
  const url = new URL(config.apiBaseUrl + path);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (!opts.public) {
    const token = await authProvider.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url.toString(), {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });

  const text = await res.text();
  const json = text ? safeJson(text) : null;

  if (!res.ok) {
    const detail =
      (json as { detail?: string } | null)?.detail ?? res.statusText;
    throw new ApiError(res.status, detail, json);
  }
  if (!opts.schema) return json as T;
  return opts.schema.parse(json);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
