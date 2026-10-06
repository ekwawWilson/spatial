import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, createApi, normaliseServer, OfflineError, type Api, type Session } from "../services/api";
import * as store from "../services/authStore";
import type { Me, Membership } from "../types";

interface AuthState {
  ready: boolean;
  me: Me | null;
  server: string;
  /** Signed in without the server: only downloaded projects are available. */
  offline: boolean;
  districtId: number | null;
  membership: Membership | null;
  api: Api;
  signIn(server: string, email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  setDistrict(id: number): Promise<void>;
  can(permission: string): boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const session = useRef<Session>({
    server: "",
    tokens: null,
    districtId: null,
    onTokens: (tokens) => void store.saveTokens(tokens),
  });
  const api = useMemo(() => createApi(session.current), []);
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [server, setServer] = useState("");
  const [offline, setOffline] = useState(false);
  const [districtId, setDistrictId] = useState<number | null>(null);
  // The app locks when it starts: the stored profile is shown only after the
  // password is entered again (online or offline).
  useEffect(() => {
    (async () => {
      const savedServer = (await store.loadServer()) ?? "";
      session.current.server = savedServer;
      setServer(savedServer);
      setReady(true);
    })();
  }, []);

  const adopt = useCallback(async (profile: Me) => {
    const saved = await store.loadDistrict();
    const ids = profile.memberships.map((m) => m.district.id);
    const chosen = saved !== null && ids.includes(saved) ? saved : (ids[0] ?? null);
    session.current.districtId = chosen;
    setDistrictId(chosen);
    setMe(profile);
  }, []);

  const signIn = useCallback(
    async (serverInput: string, email: string, password: string) => {
      const address = normaliseServer(serverInput);
      if (!address) throw new Error("Enter the server's address.");
      session.current.server = address;
      try {
        await api.login(email, password);
        const profile = await api.me();
        await Promise.all([store.saveServer(address), store.saveProfile(profile), store.rememberForOffline(email, password)]);
        setServer(address);
        setOffline(false);
        await adopt(profile);
      } catch (error) {
        if (!(error instanceof OfflineError)) {
          if (error instanceof ApiError && error.status === 401) throw new Error("The email or password is wrong.");
          throw error;
        }
        // No connection: fall back to the last account that signed in on this device.
        const result = await store.checkOffline(email, password);
        const profile = await store.loadProfile();
        if (result === "never-signed-in" || !profile) {
          throw new Error("No connection. Sign in once with a connection; after that you can sign in offline.");
        }
        if (result === "wrong") throw new Error("No connection, and that isn't the email and password last used on this device.");
        session.current.tokens = await store.loadTokens();
        setServer(address);
        setOffline(true);
        await adopt(profile);
      }
    },
    [adopt, api],
  );

  const signOut = useCallback(async () => {
    session.current.tokens = null;
    setMe(null);
    setOffline(false);
  }, []);

  const setDistrict = useCallback(async (id: number) => {
    session.current.districtId = id;
    setDistrictId(id);
    await store.saveDistrict(id);
  }, []);

  const membership = me?.memberships.find((m) => m.district.id === districtId) ?? null;
  const value: AuthState = {
    ready,
    me,
    server,
    offline,
    districtId,
    membership,
    api,
    signIn,
    signOut,
    setDistrict,
    can: (permission) => Boolean(me?.is_system_admin || membership?.permissions.includes(permission)),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
