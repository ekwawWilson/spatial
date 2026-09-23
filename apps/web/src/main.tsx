import { createApiClient, localStorageTokenStore } from "@spatial/map-core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { SESSION_EXPIRED_EVENT, SessionProvider, type DistrictHolder } from "./session";
import "./styles.css";

const district: DistrictHolder = { current: null };
const api = createApiClient({
  tokens: localStorageTokenStore(),
  getDistrictId: () => district.current,
  onSessionExpired: () => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)),
});

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider api={api} district={district}>
        <App />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
