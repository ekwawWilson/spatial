// Offline sign-in. After a successful online sign-in the device keeps a
// salted, slow hash of the password (never the password) in the phone's
// secure storage. Offline, the same password must produce the same hash.

import { pbkdf2 } from "@noble/hashes/pbkdf2.js";
import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, hexToBytes, utf8ToBytes } from "@noble/hashes/utils.js";

export const ITERATIONS = 30_000;

export interface Verifier {
  email: string;
  salt: string; // hex
  hash: string; // hex
  iterations: number;
}

export function makeVerifier(email: string, password: string, salt: Uint8Array, iterations = ITERATIONS): Verifier {
  const hash = pbkdf2(sha256, utf8ToBytes(password), salt, { c: iterations, dkLen: 32 });
  return { email: email.trim().toLowerCase(), salt: bytesToHex(salt), hash: bytesToHex(hash), iterations };
}

export function checkVerifier(verifier: Verifier, email: string, password: string): boolean {
  if (verifier.email !== email.trim().toLowerCase()) return false;
  const again = makeVerifier(email, password, hexToBytes(verifier.salt), verifier.iterations);
  // Compare every character, so timing doesn't reveal where they differ.
  let diff = again.hash.length ^ verifier.hash.length;
  for (let i = 0; i < Math.min(again.hash.length, verifier.hash.length); i++) {
    diff |= again.hash.charCodeAt(i) ^ verifier.hash.charCodeAt(i);
  }
  return diff === 0;
}
