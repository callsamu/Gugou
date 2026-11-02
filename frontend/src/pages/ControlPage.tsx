import type { RoutableProps } from "preact-router";
import { Link } from "preact-router";
import { useCallback, useEffect, useState } from "preact/hooks";

import {
  crawl,
  getQueueStatus,
  listUrls,
  pauseQueue,
  resumeQueue,
  type CrawlResponse,
  type StoredUrl,
  type UrlState,
} from "../api";
import { Logo } from "../components/Logo";

const PAGE_SIZE = 50;

const STATUS_OPTIONS: Array<{ value: "" | UrlState; label: string }> = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

const ORDER_BY_OPTIONS: Array<{ value: "priority" | "createdAt"; label: string }> = [
  { value: "createdAt", label: "Created time" },
  { value: "priority", label: "Priority" },
];

const ORDER_OPTIONS: Array<{ value: "asc" | "desc"; label: string }> = [
  { value: "desc", label: "Descending" },
  { value: "asc", label: "Ascending" },
];

function formatDate(value: string | number): string {
  const date = typeof value === "number" ? new Date(value / 1_000_000) : new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function stateBadge(state: UrlState): string {
  switch (state) {
    case "pending":
      return "bg-amber-100 text-amber-800";
    case "completed":
      return "bg-green-100 text-green-800";
    case "failed":
      return "bg-red-100 text-red-800";
  }
  return "bg-slate-100 text-slate-700";
}

export function ControlPage(_props: RoutableProps) {
  const [url, setUrl] = useState("");
  const [crawlResult, setCrawlResult] = useState<CrawlResponse | null>(null);
  const [crawlError, setCrawlError] = useState("");
  const [crawling, setCrawling] = useState(false);

  const [paused, setPaused] = useState<boolean | null>(null);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [queueError, setQueueError] = useState("");

  const [status, setStatus] = useState<"" | UrlState>("");
  const [orderBy, setOrderBy] = useState<"priority" | "createdAt">("createdAt");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [urls, setUrls] = useState<StoredUrl[]>([]);
  const [urlsLoading, setUrlsLoading] = useState(false);
  const [urlsError, setUrlsError] = useState("");
  const [lastLoaded, setLastLoaded] = useState<Date | null>(null);

  const loadUrls = useCallback(async () => {
    setUrlsLoading(true);
    setUrlsError("");
    try {
      const result = await listUrls({
        status: status || null,
        orderBy,
        order,
        limit: PAGE_SIZE,
      });
      setUrls(result);
      setLastLoaded(new Date());
    } catch (err) {
      setUrlsError(err instanceof Error ? err.message : "Could not load URLs");
    } finally {
      setUrlsLoading(false);
    }
  }, [status, orderBy, order]);

  useEffect(() => {
    void getQueueStatus()
      .then((result) => {
        setPaused(result.paused);
        setQueueError("");
      })
      .catch((err: unknown) => {
        setQueueError(err instanceof Error ? err.message : "Could not read queue status");
      });
  }, []);

  useEffect(() => {
    void loadUrls();
  }, [loadUrls]);

  const toggleQueue = async () => {
    setPauseBusy(true);
    setQueueError("");
    try {
      const result = paused ? await resumeQueue() : await pauseQueue();
      setPaused(result.paused);
      await loadUrls();
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Could not update the queue");
    } finally {
      setPauseBusy(false);
    }
  };

  const submit = async (event: SubmitEvent) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) {
      return;
    }
    setCrawling(true);
    setCrawlError("");
    setCrawlResult(null);
    try {
      setCrawlResult(await crawl(trimmed));
      setUrl("");
      await loadUrls();
    } catch (err) {
      setCrawlError(err instanceof Error ? err.message : "Could not queue the URL");
    } finally {
      setCrawling(false);
    }
  };

  const queueLabel =
    paused === null ? "Checking queue status…" : paused ? "Queue paused" : "Queue running";
  const queueDescription =
    paused === null
      ? "Reading the frontier state."
      : paused
        ? "New URLs are accepted, but consumption is paused."
        : "The frontier is consuming its queue one URL at a time.";

  return (
    <main class="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 pb-12">
      <header class="flex items-center justify-between py-4 text-sm">
        <Link href="/" aria-label="Gugou">
          <Logo size="small" />
        </Link>
        <Link href="/" class="text-slate-600 hover:text-slate-900 hover:underline">
          Back to search
        </Link>
      </header>

      <section class="mt-8">
        <h1 class="text-3xl font-semibold">Crawler control</h1>
        <p class="mt-2 text-slate-600">
          Add seed URLs, pause the frontier queue, and inspect the URLs it has stored.
        </p>
      </section>

      <section class="mt-6 rounded-2xl border border-slate-200 p-5">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="font-medium">{queueLabel}</p>
            <p class="mt-1 text-sm text-slate-600">{queueDescription}</p>
          </div>
          <button
            type="button"
            onClick={() => void toggleQueue()}
            disabled={paused === null || pauseBusy}
            class={`rounded-full px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50 ${
              paused ? "bg-[#34A853] hover:bg-[#2d8f46]" : "bg-[#EA4335] hover:bg-[#c5372c]"
            }`}
          >
            {pauseBusy ? "Updating…" : paused ? "Resume queue" : "Pause queue"}
          </button>
        </div>
        {queueError && <p class="mt-3 text-sm text-red-600">{queueError}</p>}
      </section>

      <section class="mt-6 rounded-2xl border border-slate-200 p-5">
        <h2 class="text-lg font-semibold">Add a seed URL</h2>
        <form onSubmit={submit} class="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            type="url"
            required
            value={url}
            onInput={(event) => setUrl(event.currentTarget.value)}
            placeholder="https://example.com"
            aria-label="Seed URL"
            class="min-w-0 flex-1 rounded-full border border-slate-300 px-5 py-3 outline-none focus:border-[#4285F4]"
          />
          <button
            type="submit"
            disabled={crawling}
            class="rounded-full bg-[#4285F4] px-6 py-3 font-medium text-white hover:bg-[#3367d6] disabled:opacity-50"
          >
            {crawling ? "Adding…" : "Add to frontier"}
          </button>
        </form>

        {crawlError && <p class="mt-4 text-sm text-red-600">{crawlError}</p>}

        {crawlResult && (
          <div
            class={`mt-4 rounded-xl border p-4 ${
              crawlResult.queued
                ? "border-green-200 bg-green-50 text-green-900"
                : "border-amber-200 bg-amber-50 text-amber-900"
            }`}
          >
            <p class="font-medium">{crawlResult.queued ? "Queued!" : "Not queued"}</p>
            <p class="mt-1 text-sm">
              {crawlResult.queued
                ? "The frontier accepted this URL and will process it."
                : "The frontier did not accept this URL."}
            </p>
          </div>
        )}
      </section>

      <section class="mt-6 rounded-2xl border border-slate-200 p-5">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 class="text-lg font-semibold">Stored URLs</h2>
            <p class="mt-1 text-sm text-slate-500">
              {lastLoaded ? `Updated ${lastLoaded.toLocaleTimeString()}` : "Loading…"}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select
              value={status}
              onChange={(event) => setStatus(event.currentTarget.value as "" | UrlState)}
              class="rounded-full border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#4285F4]"
              aria-label="Filter by status"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={orderBy}
              onChange={(event) =>
                setOrderBy(event.currentTarget.value as "priority" | "createdAt")
              }
              class="rounded-full border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#4285F4]"
              aria-label="Order by"
            >
              {ORDER_BY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={order}
              onChange={(event) => setOrder(event.currentTarget.value as "asc" | "desc")}
              class="rounded-full border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#4285F4]"
              aria-label="Sort direction"
            >
              {ORDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void loadUrls()}
              disabled={urlsLoading}
              class="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {urlsLoading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>

        {urlsError && <p class="mt-4 text-sm text-red-600">{urlsError}</p>}

        {urlsLoading && urls.length === 0 && (
          <p class="mt-4 text-sm text-slate-500">Loading URLs…</p>
        )}

        {!urlsLoading && urls.length === 0 && !urlsError && (
          <p class="mt-4 text-sm text-slate-500">No URLs match these filters.</p>
        )}

        {urls.length > 0 && (
          <ul class="mt-4 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200">
            {urls.map((item) => (
              <li key={item.url_hash} class="p-4">
                <div class="flex items-start justify-between gap-4">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    class="min-w-0 break-all text-sm font-medium text-[#1a0dab] hover:underline"
                  >
                    {item.url}
                  </a>
                  <span
                    class={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${stateBadge(item.state)}`}
                  >
                    {item.state}
                  </span>
                </div>
                <div class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
                  <span>Host: {item.host}</span>
                  <span>Priority: {item.priority ? formatDate(item.priority) : "—"}</span>
                  <span>Created: {formatDate(item.createdAt)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
