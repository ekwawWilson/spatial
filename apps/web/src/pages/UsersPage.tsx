import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

export function UsersPage() {
  const { api, me } = useSession();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, reload } = useLoad(() => api.listUsers({ search, page }), [api, search, page]);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");

  async function run(action: () => Promise<unknown>, message = ""): Promise<boolean> {
    setActionError(null);
    setNotice("");
    try {
      await action();
      setNotice(message);
      reload();
      return true;
    } catch (err) {
      setActionError(err);
      return false;
    }
  }

  return (
    <section className="page">
      <h1>Users</h1>
      <p className="muted">
        District administrators add people to their own district from the Members page. Use this page for accounts,
        system administrators and locked accounts.
      </p>
      <CreateUserForm onCreate={(data) => run(() => api.createUser(data), `Invitation sent to ${data.email}.`)} />
      <input
        type="search"
        placeholder="Search by email"
        aria-label="Search users"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      <ErrorMessage error={error ?? actionError} />
      {notice && <p role="status">{notice}</p>}
      <table className="data">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>System admin</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {data?.results.map((u) => (
            <tr key={u.id} className={u.is_active ? "" : "inactive"}>
              <td>{u.email}</td>
              <td>{`${u.first_name} ${u.last_name}`.trim() || "—"}</td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`System admin: ${u.email}`}
                  checked={u.is_system_admin}
                  disabled={u.id === me?.id}
                  onChange={() => run(() => api.updateUser(u.id, { is_system_admin: !u.is_system_admin }))}
                />
              </td>
              <td>{!u.is_active ? "Deactivated" : u.is_locked ? "Locked" : "Active"}</td>
              <td className="actions">
                {u.is_locked && (
                  <button type="button" className="link" onClick={() => run(() => api.unlockUser(u.id), `${u.email} unlocked.`)}>
                    Unlock
                  </button>
                )}
                <button
                  type="button"
                  className="link"
                  onClick={() => run(() => api.sendPasswordReset(u.id), `Password reset sent to ${u.email}.`)}
                >
                  Send password reset
                </button>
                {u.id !== me?.id && (
                  <button type="button" className="link danger" onClick={() => run(() => api.updateUser(u.id, { is_active: !u.is_active }))}>
                    {u.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        <button type="button" disabled={!data?.previous} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} · {data?.count ?? 0} users
        </span>
        <button type="button" disabled={!data?.next} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </section>
  );
}

function CreateUserForm({
  onCreate,
}: {
  onCreate(data: { email: string; first_name: string; last_name: string; is_system_admin: boolean }): Promise<boolean>;
}) {
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [sysadmin, setSysadmin] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await onCreate({ email, first_name: firstName, last_name: lastName, is_system_admin: sysadmin }))) return;
    setEmail("");
    setFirstName("");
    setLastName("");
    setSysadmin(false);
  }
  return (
    <form className="inline-form" onSubmit={submit} aria-label="Create user">
      <input type="email" required placeholder="Email" aria-label="New user email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="First name" aria-label="New user first name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
      <input placeholder="Last name" aria-label="New user last name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
      <label className="checkbox">
        <input type="checkbox" checked={sysadmin} onChange={(e) => setSysadmin(e.target.checked)} /> System admin
      </label>
      <button type="submit">Create and invite</button>
    </form>
  );
}
