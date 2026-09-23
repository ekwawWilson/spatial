import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useSession } from "../session";

export function ForgotPasswordPage() {
  const { api } = useSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <main className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>Reset your password</h1>
        {sent ? (
          <p role="status">If an account exists for {email}, we've emailed a link to reset its password.</p>
        ) : (
          <>
            <label>
              Email
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <ErrorMessage error={error} />
            <button type="submit">Send reset link</button>
          </>
        )}
        <Link to="/login">Back to sign in</Link>
      </form>
    </main>
  );
}

/** Also used by invitations: new users set their first password here. */
export function ResetPasswordPage() {
  const { api } = useSession();
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(new Error("The two passwords don't match."));
      return;
    }
    try {
      await api.confirmPasswordReset(params.get("uid") ?? "", params.get("token") ?? "", password);
      setDone(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <main className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>Choose a password</h1>
        {done ? (
          <p role="status">
            Your password is set. <Link to="/login">Sign in</Link>
          </p>
        ) : (
          <>
            <label>
              New password
              <input type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label>
              Repeat new password
              <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
            <p className="muted">At least 8 characters; not entirely numeric or too common.</p>
            <ErrorMessage error={error} />
            <button type="submit">Set password</button>
          </>
        )}
      </form>
    </main>
  );
}
