import { Router } from "preact-router";

import { ControlPage } from "./pages/ControlPage";
import { SearchPage } from "./pages/SearchPage";

export function App() {
  return (
    <Router>
      <SearchPage path="/" />
      <ControlPage path="/crawl" />
    </Router>
  );
}
