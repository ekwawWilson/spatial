import type { Tokens } from "./types";

/** Where the session's tokens live. The web app uses localStorage; the Android
 * app (Phase 9) will supply a secure-storage implementation. */
export interface TokenStore {
  get(): Tokens | null;
  set(tokens: Tokens): void;
  clear(): void;
}

export function memoryTokenStore(initial: Tokens | null = null): TokenStore {
  let tokens = initial;
  return {
    get: () => tokens,
    set: (t) => {
      tokens = t;
    },
    clear: () => {
      tokens = null;
    },
  };
}

export function localStorageTokenStore(key = "spatial.tokens"): TokenStore {
  return {
    get() {
      try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as Tokens) : null;
      } catch {
        return null;
      }
    },
    set(tokens) {
      localStorage.setItem(key, JSON.stringify(tokens));
    },
    clear() {
      localStorage.removeItem(key);
    },
  };
}
