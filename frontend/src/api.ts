const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export interface SearchResult {
  id: string;
  url: string | null;
  title: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface CrawlResponse {
  task_id: string;
  url: string;
  status: string;
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
