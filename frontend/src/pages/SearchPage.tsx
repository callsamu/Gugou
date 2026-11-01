import type { RoutableProps } from "preact-router";
import { Link } from "preact-router";
import { useCallback, useEffect, useState } from "preact/hooks";

import { search, type SearchResult } from "../api";
import { Logo } from "../components/Logo";

function readQuery(): string {
  return new URLSearchParams(window.location.search).get("q")?.trim() ?? "";
}

export function SearchPage(_props: RoutableProps) {
  const [query, setQuery] = useState(readQuery);
  const [searchedFor, setSearchedFor] = useState(readQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState("");

  const runSearch = useCallback(async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    setStatus("loading");
    setError("");
    setResults([]);
    setSearchedFor(trimmed);
    try {
      const response = await search(trimmed);
      setResults(response.results);
      setStatus("done");
    } catch (err) {
      setResults([]);
      setError(err instanceof Error ? err.message : "Search failed");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    const initial = readQuery();
    if (initial) {
      void runSearch(initial);
    }
  }, [runSearch]);

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    window.history.replaceState(null, "", `/?q=${encodeURIComponent(trimmed)}`);
    void runSearch(trimmed);
  };

  return (
    <main class="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-6">
      <header class="flex items-center justify-end py-4 text-sm">
        <Link href="/crawl" class="text-slate-600 hover:text-slate-900 hover:underline">
          Add a page
        </Link>
      </header>

      <section class={status === "idle" ? "mt-[18vh]" : "mt-10"}>
        <div class="flex justify-center">
          <Logo size={status === "idle" ? "large" : "small"} />
        </div>

        <form
          onSubmit={submit}
          class="mx-auto mt-8 flex w-full max-w-2xl items-center gap-3 rounded-full border border-slate-300 px-5 py-3 shadow-sm transition hover:shadow-md focus-within:border-transparent focus-within:shadow-md"
        >
          <svg
            class="h-5 w-5 shrink-0 text-slate-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            type="search"
            value={query}
            onInput={(event) => setQuery(event.currentTarget.value)}
            placeholder="Search the web"
            aria-label="Search"
            class="min-w-0 flex-1 bg-transparent text-lg outline-none placeholder:text-slate-400"
            autoFocus
          />
          <button
            type="submit"
            class="rounded-full bg-[#4285F4] px-5 py-2 text-sm font-medium text-white hover:bg-[#3367d6]"
          >
            Search
          </button>
        </form>

        {status === "idle" && (
          <p class="mt-6 text-center text-sm text-slate-500">
            Searches the page index. Crawl pages first to fill it.
          </p>
        )}
      </section>

      <section class="mt-10 w-full pb-16">
        {status === "loading" && <p class="text-center text-slate-500">Searching…</p>}
        {status === "error" && <p class="text-center text-red-600">{error}</p>}
        {status === "done" && results.length === 0 && (
          <p class="text-center text-slate-500">No results for “{searchedFor}”.</p>
        )}
        {results.length > 0 && (
          <ul class="space-y-7">
            {results.map((result) => (
              <li key={result.id}>
                <ResultLink result={result} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function ResultLink({ result }: { result: SearchResult }) {
  const label = result.title?.trim() || result.url || result.id;
  const href = result.url ?? undefined;

  return (
    <div>
      <div class="truncate text-sm text-slate-600">{result.url ?? `id: ${result.id}`}</div>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          class="text-xl text-[#1a0dab] hover:underline"
        >
          {label}
        </a>
      ) : (
        <span class="text-xl text-slate-800">{label}</span>
      )}
    </div>
  );
}
