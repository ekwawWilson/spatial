import type { ApiClient, DistrictBrief, Me, MyMembership, Permission } from "@spatial/map-core";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/** Shared between the session and the API client, which reads the active
 * district on every request (X-District-ID). */
export interface DistrictHolder {
  current: number | null;
}

export interface Session {
  api: ApiClient;
  me: Me | null;
  loading: boolean;
  /** Signed in and the active district (if any) is resolved. Pages that depend
   * on the district wait for this, so they never act on a half-restored session. */
  ready: boolean;
  /** Districts the user can switch to: their memberships, or all for system admins. */
  districts: DistrictBrief[];
  districtId: number | null;
  membership: MyMembership | null;
  setDistrictId(id: number): void;
  can(permission: Permission): boolean;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export const SESSION_EXPIRED_EVENT = "spatial:session-expired";

const storageKey = (userId: number) => `spatial.district.${userId}`;

function readStored(key: string): number | null {
  try {
    const value = Number(localStorage.getItem(key));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function SessionProvider({
  api,
  district,
  children,
}: {
  api: ApiClient;
  district: DistrictHolder;
  children: ReactNode;
}) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [allDistricts, setAllDistricts] = useState<DistrictBrief[] | null>(null);
  const [districtId, setDistrictIdState] = useState<number | null>(null);

  const districts = useMemo(
    () => (me?.is_system_admin ? (allDistricts ?? []) : (me?.memberships.map((m) => m.district) ?? [])),
    [me, allDistricts],
  );

  const setDistrictId = useCallback(
    (id: number) => {
      district.current = id;
      setDistrictIdState(id);
      if (me) {
        try {
          localStorage.setItem(storageKey(me.id), String(id));
        } catch {
          // storage unavailable: choice lasts for this session only
        }
      }
    },
    [district, me],
  );

  // The API client fires this when the refresh token is rejected.
  useEffect(() => {
    const expire = () => setMe(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);

  // Restore the session on load (tokens survive a page reload).
  useEffect(() => {
    if (!api.tokens.get()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (me?.is_system_admin) {
      api
        .listDistricts()
        .then((list) => setAllDistricts(list.filter((d) => d.is_active).map(({ id, name, code }) => ({ id, name, code }))))
        .catch(() => setAllDistricts([]));
    }
  }, [api, me]);

  // Pick the remembered district, else the first available one.
  useEffect(() => {
    if (!me || districts.length === 0) return;
    const stored = readStored(storageKey(me.id));
    const chosen = districts.find((d) => d.id === stored) ?? districts[0];
    if (chosen && chosen.id !== districtId) setDistrictId(chosen.id);
  }, [me, districts, districtId, setDistrictId]);

  const membership = useMemo(
    () => me?.memberships.find((m) => m.district.id === districtId) ?? null,
    [me, districtId],
  );

  const ready =
    me !== null &&
    (!me.is_system_admin || allDistricts !== null) &&
    (districts.length === 0 || districtId !== null);

  const can = useCallback(
    (permission: Permission) => Boolean(me?.is_system_admin || membership?.permissions.includes(permission)),
    [me, membership],
  );

  const signIn = useCallback(
    async (email: string, password: string) => {
      setMe(await api.login(email, password));
    },
    [api],
  );

  const signOut = useCallback(async () => {
    await api.logout();
    district.current = null;
    setDistrictIdState(null);
    setAllDistricts(null);
    setMe(null);
  }, [api, district]);

  const value = useMemo<Session>(
    () => ({ api, me, loading, ready, districts, districtId, membership, setDistrictId, can, signIn, signOut }),
    [api, me, loading, ready, districts, districtId, membership, setDistrictId, can, signIn, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside <SessionProvider>");
  return session;
}
