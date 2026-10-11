import type { PermitVerification } from "@spatial/map-core";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useSession } from "../session";

type State = { kind: "loading" } | { kind: "found"; permit: PermitVerification } | { kind: "none" } | { kind: "error" };

/** Where a permit certificate's QR code leads: the Assembly's own record of
 * the permit, for anyone holding the certificate. No sign-in. */
export function VerifyPage() {
  const { token = "" } = useParams();
  const { api } = useSession();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    api
      .verifyPermit(token)
      .then((permit) => setState(permit ? { kind: "found", permit } : { kind: "none" }))
      .catch(() => setState({ kind: "error" }));
  }, [api, token]);

  return (
    <main className="page">
      <h1>Permit check</h1>
      {state.kind === "loading" && <p>Checking the Assembly's record…</p>}
      {state.kind === "error" && <p role="alert">The record can't be reached right now. Try again shortly.</p>}
      {state.kind === "none" && (
        <div role="alert" className="card wide">
          <h2 className="error">No such permit</h2>
          <p>
            This code doesn't match any permit issued by an Assembly on this system. If it came from a certificate, the certificate
            may not be genuine: ask the Assembly's Physical Planning Department.
          </p>
        </div>
      )}
      {state.kind === "found" && (
        <section className="card wide" aria-label="Permit">
          <h2 className={state.permit.valid ? undefined : "error"}>{state.permit.valid ? "A genuine permit, in force" : "A genuine permit, but it has expired"}</h2>
          <dl className="facts">
            <dt>Issued by</dt>
            <dd>{state.permit.assembly}</dd>
            <dt>Number</dt>
            <dd>{state.permit.number}</dd>
            <dt>Permit</dt>
            <dd>
              {state.permit.permit}: {state.permit.for}
            </dd>
            <dt>To</dt>
            <dd>{state.permit.applicant}</dd>
            <dt>Locality</dt>
            <dd>{state.permit.locality}</dd>
            <dt>Use</dt>
            <dd>{state.permit.proposed_use || "—"}</dd>
            <dt>Issued on</dt>
            <dd>{state.permit.issued_on}</dd>
            <dt>Valid until</dt>
            <dd>{state.permit.expires_on}</dd>
          </dl>
          <p className="muted small">Compare these details with the certificate in your hand. If they differ, the certificate has been altered.</p>
        </section>
      )}
    </main>
  );
}
