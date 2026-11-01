import { Router } from "preact-router";

import { CrawlPage } from "./pages/CrawlPage";
import { SearchPage } from "./pages/SearchPage";

export function App() {
  return (
    <Router>
      <SearchPage path="/" />
      <CrawlPage path="/crawl" />
    </Router>
  );
}
