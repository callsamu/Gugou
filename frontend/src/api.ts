const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export interface SearchResult {
  id: string;
  url: string | null;
  title: string | null;
  description: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface CrawlResponse {
  url: string;
  queued: boolean;
}

export type UrlState = "pending" | "completed" | "failed";

export interface StoredUrl {
  url: string;
  url_hash: string;
  host: string;
  state: UrlState;
  priority: number;
  createdAt: string;
  updatedAt: string;
}

export interface QueueStatus {
  paused: boolean;
}

export interface UrlQuery {
  status?: UrlState | null;
  orderBy?: "priority" | "createdAt";
  order?: "asc" | "desc";
  limit?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`.trim();
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Keep the status line when the body is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function search(query: string, limit = 20): Promise<SearchResponse> {
  return request<SearchResponse>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

export function crawl(url: string): Promise<CrawlResponse> {
  return request<CrawlResponse>("/crawl", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export function getQueueStatus(): Promise<QueueStatus> {
  return request<QueueStatus>("/queue");
}

export function pauseQueue(): Promise<QueueStatus> {
  return request<QueueStatus>("/pause", { method: "POST" });
}

export function resumeQueue(): Promise<QueueStatus> {
  return request<QueueStatus>("/resume", { method: "POST" });
}

export function listUrls(query: UrlQuery = {}): Promise<StoredUrl[]> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  params.set("order_by", query.orderBy ?? "createdAt");
  params.set("order", query.order ?? "desc");
  params.set("limit", String(query.limit ?? 50));
  return request<StoredUrl[]>(`/urls?${params.toString()}`);
}
