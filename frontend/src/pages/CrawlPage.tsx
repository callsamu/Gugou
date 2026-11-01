import type { RoutableProps } from "preact-router";
import { Link } from "preact-router";
import { useState } from "preact/hooks";

import { crawl, type CrawlResponse } from "../api";
import { Logo } from "../components/Logo";

export function CrawlPage(_props: RoutableProps) {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<CrawlResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: SubmitEvent) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) {
      return;
    }

    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await crawl(trimmed));
      setUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not queue the URL");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-6">
      <header class="flex items-center justify-between py-4 text-sm">
        <Link href="/" aria-label="OBuscador">
          <Logo size="small" />
        </Link>
        <Link href="/" class="text-slate-600 hover:text-slate-900 hover:underline">
          Back to search
        </Link>
      </header>

      <section class="mt-16">
        <h1 class="text-2xl font-semibold">Add a page to the index</h1>
        <p class="mt-2 text-slate-600">
          Send a seed URL to the crawler. It will be downloaded, parsed and indexed.
        </p>

        <form onSubmit={submit} class="mt-8 flex flex-col gap-3 sm:flex-row">
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
            disabled={busy}
            class="rounded-full bg-[#4285F4] px-6 py-3 font-medium text-white hover:bg-[#3367d6] disabled:opacity-50"
          >
            {busy ? "Sending…" : "Crawl"}
          </button>
        </form>

        {error && <p class="mt-6 text-red-600">{error}</p>}

        {result && (
          <div
            class={`mt-6 rounded-xl border p-4 ${
              result.queued
                ? "border-green-200 bg-green-50 text-green-900"
                : "border-amber-200 bg-amber-50 text-amber-900"
            }`}
          >
            <p class="font-medium">{result.queued ? "Queued!" : "Already known"}</p>
            <p class="mt-1 text-sm">
              {result.queued
                ? "The frontier will download, parse and index this page."
                : "This URL is already in the frontier."}
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
