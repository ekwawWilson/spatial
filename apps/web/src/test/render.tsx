import { createApiClient, memoryTokenStore, type Tokens } from "@spatial/map-core";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { SESSION_EXPIRED_EVENT, SessionProvider, type DistrictHolder } from "../session";

/** Renders the whole app at `route` against a fake backend, the way main.tsx does. */
export function renderApp(fetch: typeof globalThis.fetch, { route = "/", tokens = null as Tokens | null } = {}) {
  const district: DistrictHolder = { current: null };
  const api = createApiClient({
    fetch,
    tokens: memoryTokenStore(tokens),
    getDistrictId: () => district.current,
    onSessionExpired: () => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)),
  });
  const view = render(
    <MemoryRouter initialEntries={[route]}>
      <SessionProvider api={api} district={district}>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { ...view, api, district };
}

export const signedIn: Tokens = { access: "A", refresh: "R" };
