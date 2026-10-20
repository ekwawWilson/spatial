import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Icon, Logo } from "../components/Icon";
import { useSession } from "../session";

export function LoginPage() {
  const { me, signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-hero" aria-hidden="true">
        <div className="brand">
          <Logo size={36} />
          <span className="brand-text">
            <span className="brand-name">Spatial Planning Platform</span>
            <span className="brand-sub">For Metropolitan, Municipal and District Assemblies</span>
          </span>
        </div>
        <div>
          <h2>Plan, permit and enforce on one map.</h2>
          <p>Local plans, zoning, development permits and enforcement, kept to the time limits of the Land Use and Spatial Planning Regulations.</p>
          <ul>
            <li>
              <Icon name="map" /> Survey-accurate maps in the Ghana National Grid
            </li>
            <li>
              <Icon name="stamp" /> Permits from receipt to certificate, with every statutory clock
            </li>
            <li>
              <Icon name="globe" /> A Public Data Room for residents and investors
            </li>
            <li>
              <Icon name="sync" /> Field capture that works offline
            </li>
          </ul>
        </div>
        <p className="small">Land Use and Spatial Planning Act, 2016 (Act 925) · L.I. 2384</p>
      </section>
      <section className="auth-panel">
        <form className="card" onSubmit={submit}>
          <h1>Sign in</h1>
          <p className="muted">Spatial Planning Platform</p>
          <label>
            Email
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <ErrorMessage error={error} />
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <Link to="/forgot-password">Forgotten your password?</Link>
        </form>
      </section>
    </main>
  );
}
