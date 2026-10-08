import { describe, expect, it } from "vitest";

import { locateProblem } from "./locate";

describe("My location", () => {
  it("explains in plain words why the position wasn't found", () => {
    expect(locateProblem({ code: 1 })).toMatch(/blocked for this site/);
    expect(locateProblem({ code: 3 })).toMatch(/took too long/);
    expect(locateProblem({ code: 2 })).toMatch(/couldn't be found/);
  });
});
