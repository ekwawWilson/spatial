import { checkVerifier, makeVerifier } from "../src/utils/verifier";

const salt = new Uint8Array(16).fill(7);

describe("offline sign-in", () => {
  const verifier = makeVerifier("Kofi@Example.test ", "Correct-Horse-9", salt, 1000);

  it("accepts the same email and password", () => {
    expect(checkVerifier(verifier, "kofi@example.test", "Correct-Horse-9")).toBe(true);
  });

  it("refuses another password or another person", () => {
    expect(checkVerifier(verifier, "kofi@example.test", "correct-horse-9")).toBe(false);
    expect(checkVerifier(verifier, "ama@example.test", "Correct-Horse-9")).toBe(false);
  });

  it("stores a hash, never the password", () => {
    expect(JSON.stringify(verifier)).not.toContain("Correct-Horse-9");
    expect(verifier.hash).toMatch(/^[0-9a-f]{64}$/);
    // The same password with another salt gives another hash.
    expect(makeVerifier("kofi@example.test", "Correct-Horse-9", new Uint8Array(16).fill(8), 1000).hash).not.toBe(verifier.hash);
  });

  it("matches the published PBKDF2-HMAC-SHA256 test vector", () => {
    // RFC 7914 section 11: P="passwd", S="salt", c=1, dkLen=64 (first 32 bytes).
    const vector = makeVerifier("x", "passwd", new TextEncoder().encode("salt"), 1);
    expect(vector.hash).toBe("55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc");
  });
});
