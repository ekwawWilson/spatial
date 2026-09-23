import { ROLE_LABELS, type Member, type Role } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const ROLES = Object.keys(ROLE_LABELS) as Role[];

export function MembersPage() {
  const { api, districtId, districts, can, me } = useSession();
  const district = districts.find((d) => d.id === districtId);
  const { data, error, loading, reload } = useLoad(() => api.listMembers(), [api, districtId]);
  const [actionError, setActionError] = useState<unknown>(null);
  const canManage = can("membership.manage");

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setActionError(null);
    try {
      await action();
      reload();
      return true;
    } catch (err) {
      setActionError(err);
      return false;
    }
  }

  return (
    <section className="page">
      <h1>Members of {district?.name}</h1>
      <ErrorMessage error={error ?? actionError} />
      {canManage && <AddMemberForm onAdd={(data) => run(() => api.addMember(data))} />}
      {loading && !data ? (
        <p>Loading…</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              {canManage && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {data?.results.map((m) => (
              <MemberRow
                key={m.id}
                member={m}
                isSelf={m.user.id === me?.id}
                canManage={canManage}
                onRole={(role) => run(() => api.updateMember(m.id, { role }))}
                onRemove={() => run(() => api.removeMember(m.id))}
                onRestore={() => run(() => api.updateMember(m.id, { is_active: true }))}
              />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function MemberRow(props: {
  member: Member;
  isSelf: boolean;
  canManage: boolean;
  onRole(role: Role): void;
  onRemove(): void;
  onRestore(): void;
}) {
  const { member, canManage } = props;
  const name = `${member.user.first_name} ${member.user.last_name}`.trim() || "—";
  return (
    <tr className={member.is_active ? "" : "inactive"}>
      <td>{name}</td>
      <td>{member.user.email}</td>
      <td>
        {canManage && member.is_active ? (
          <select
            aria-label={`Role of ${member.user.email}`}
            value={member.role}
            onChange={(e) => props.onRole(e.target.value as Role)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        ) : (
          ROLE_LABELS[member.role]
        )}
      </td>
      <td>{member.is_active ? "Active" : "Removed"}</td>
      {canManage && (
        <td>
          {member.is_active ? (
            <button type="button" className="link danger" onClick={props.onRemove}>
              {props.isSelf ? "Leave district" : "Remove"}
            </button>
          ) : (
            <button type="button" className="link" onClick={props.onRestore}>
              Restore
            </button>
          )}
        </td>
      )}
    </tr>
  );
}

function AddMemberForm({ onAdd }: { onAdd(data: { email: string; role: Role; first_name: string; last_name: string }): Promise<boolean> }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await onAdd({ email, role, first_name: firstName, last_name: lastName }))) return;
    setEmail("");
    setFirstName("");
    setLastName("");
  }

  return (
    <form className="inline-form" onSubmit={submit} aria-label="Add member">
      <input type="email" required placeholder="Email" aria-label="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="First name" aria-label="First name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
      <input placeholder="Last name" aria-label="Last name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
      <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </select>
      <button type="submit">Add member</button>
      <span className="muted">New people get an email to set their password.</span>
    </form>
  );
}
