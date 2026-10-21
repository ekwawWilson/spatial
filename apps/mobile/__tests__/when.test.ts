import { ago, stale } from "../src/utils/when";

const now = new Date("2026-10-21T12:00:00Z");

describe("how long since the last sync", () => {
  it("reads like a person would say it", () => {
    expect(ago(null, now)).toBe("never");
    expect(ago("2026-10-21T11:59:40Z", now)).toBe("just now");
    expect(ago("2026-10-21T11:59:00Z", now)).toBe("1 minute ago");
    expect(ago("2026-10-21T11:15:00Z", now)).toBe("45 minutes ago");
    expect(ago("2026-10-21T07:00:00Z", now)).toBe("5 hours ago");
    expect(ago("2026-10-20T09:00:00Z", now)).toBe("yesterday");
    expect(ago("2026-10-17T12:00:00Z", now)).toBe("4 days ago");
    expect(ago("2026-09-01T12:00:00Z", now)).toBe("2026-09-01");
    expect(ago("not a date", now)).toBe("never");
  });

  it("reminds after a day without a sync", () => {
    expect(stale(null, now)).toBe(true);
    expect(stale("2026-10-21T08:00:00Z", now)).toBe(false);
    expect(stale("2026-10-20T08:00:00Z", now)).toBe(true);
  });
});
