import type { SchemaField } from "../src/types";
import { initialValues, labelOf, validate } from "../src/utils/forms";

const schema: SchemaField[] = [
  { name: "use", label: "Land use", type: "choice", required: true, choices: ["house", "shop"] },
  { name: "storeys", type: "integer", default: 1 },
  { name: "height", type: "decimal" },
  { name: "occupied", type: "boolean" },
  { name: "built", type: "date" },
  { name: "owner", type: "text" },
];

describe("forms from a layer's fields", () => {
  it("starts with defaults and labels fields", () => {
    expect(initialValues(schema)).toEqual({ use: "", storeys: "1", height: "", occupied: null, built: "", owner: "" });
    expect(labelOf(schema[0]!)).toBe("Land use");
    expect(labelOf(schema[1]!)).toBe("storeys");
  });

  it("starts from an existing feature's values", () => {
    expect(initialValues(schema, { use: "shop", storeys: 3, occupied: false }).use).toBe("shop");
    expect(initialValues(schema, { occupied: false }).occupied).toBe(false);
  });

  it("requires required fields and converts types", () => {
    const empty = validate(schema, initialValues(schema));
    expect(empty).toEqual({ ok: false, errors: { use: "Required." } });

    const good = validate(schema, { use: "shop", storeys: " 2 ", height: "3.5", occupied: true, built: "2024-02-29", owner: " Ama " });
    expect(good).toEqual({ ok: true, properties: { use: "shop", storeys: 2, height: 3.5, occupied: true, built: "2024-02-29", owner: "Ama" } });
  });

  it("leaves optional fields empty as null", () => {
    const result = validate(schema, { use: "house", storeys: "", height: "", occupied: null, built: "", owner: "" });
    expect(result).toEqual({ ok: true, properties: { use: "house", storeys: null, height: null, occupied: null, built: null, owner: null } });
  });

  it("explains values that don't fit", () => {
    const result = validate(schema, { use: "farm", storeys: "2.5", height: "tall", occupied: null, built: "2023-02-29", owner: "" });
    expect(result).toEqual({
      ok: false,
      errors: {
        use: "Pick one of the listed values.",
        storeys: "Enter a whole number.",
        height: "Enter a number.",
        built: "Enter a date as YYYY-MM-DD.",
      },
    });
  });

  it("keeps a numeric choice as a number", () => {
    const numeric: SchemaField[] = [{ name: "zone", type: "choice", choices: [1, 2] }];
    expect(validate(numeric, { zone: "2" })).toEqual({ ok: true, properties: { zone: 2 } });
  });
});
