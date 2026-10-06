// What the device remembers about the signed-in user. Tokens and the offline
// verifier live in the phone's secure storage; the profile and settings in
// the app database.

import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import type { Me, Tokens } from "../types";
import { checkVerifier, makeVerifier, type Verifier } from "../utils/verifier";
import { getMeta, setMeta } from "./db";

const TOKENS = "spatial.tokens";
const VERIFIER = "spatial.verifier";

export async function loadTokens(): Promise<Tokens | null> {
  const raw = await SecureStore.getItemAsync(TOKENS);
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export async function saveTokens(tokens: Tokens | null): Promise<void> {
  if (tokens) await SecureStore.setItemAsync(TOKENS, JSON.stringify(tokens));
  else await SecureStore.deleteItemAsync(TOKENS);
}

/** Remembers a password hash after an online sign-in, for signing in offline later. */
export async function rememberForOffline(email: string, password: string): Promise<void> {
  const verifier = makeVerifier(email, password, Crypto.getRandomBytes(16));
  await SecureStore.setItemAsync(VERIFIER, JSON.stringify(verifier));
}

export async function checkOffline(email: string, password: string): Promise<"ok" | "wrong" | "never-signed-in"> {
  const raw = await SecureStore.getItemAsync(VERIFIER);
  if (!raw) return "never-signed-in";
  return checkVerifier(JSON.parse(raw) as Verifier, email, password) ? "ok" : "wrong";
}

export async function forgetOffline(): Promise<void> {
  await SecureStore.deleteItemAsync(VERIFIER);
}

export async function loadProfile(): Promise<Me | null> {
  const raw = await getMeta("profile");
  return raw ? (JSON.parse(raw) as Me) : null;
}

export const saveProfile = (me: Me | null) => setMeta("profile", me ? JSON.stringify(me) : null);
export const loadServer = () => getMeta("server");
export const saveServer = (server: string) => setMeta("server", server);

export async function loadDistrict(): Promise<number | null> {
  const raw = await getMeta("district");
  return raw ? Number(raw) : null;
}

export const saveDistrict = (id: number | null) => setMeta("district", id === null ? null : String(id));
