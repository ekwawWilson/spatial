/** "just now", "5 minutes ago", "3 hours ago", "yesterday", "4 days ago", or the date. */
export function ago(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "never";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "never";
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  return iso.slice(0, 10);
}

/** Whether the last sync is old enough to remind the officer (a day). */
export function stale(iso: string | null, now: Date = new Date()): boolean {
  if (!iso) return true;
  const then = new Date(iso).getTime();
  return Number.isNaN(then) || now.getTime() - then > 24 * 3600 * 1000;
}
