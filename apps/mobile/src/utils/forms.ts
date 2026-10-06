// Forms are generated from each layer's schema. The rules mirror the server's
// (backend/projects/schema.py), so what the device accepts the server accepts.

import type { SchemaField } from "../types";

export type FormValues = Record<string, string | boolean | null>;

export function labelOf(field: SchemaField): string {
  return field.label?.trim() || field.name;
}

/** Starting values for a new feature: each field's default, else empty. */
export function initialValues(schema: SchemaField[], existing?: Record<string, unknown>): FormValues {
  const values: FormValues = {};
  for (const field of schema) {
    const raw = existing && field.name in existing ? existing[field.name] : field.default;
    if (field.type === "boolean") values[field.name] = raw === undefined || raw === null ? null : Boolean(raw);
    else values[field.name] = raw === undefined || raw === null ? "" : String(raw);
  }
  return values;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function validDate(text: string): boolean {
  if (!DATE.test(text)) return false;
  const [y, m, d] = text.split("-").map(Number) as [number, number, number];
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

/** Checks the form. Returns the properties to store, or a message per field. */
export function validate(
  schema: SchemaField[],
  values: FormValues,
): { ok: true; properties: Record<string, unknown> } | { ok: false; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const properties: Record<string, unknown> = {};
  for (const field of schema) {
    const raw = values[field.name];
    const empty = raw === null || raw === undefined || (typeof raw === "string" && raw.trim() === "");
    if (empty) {
      if (field.required) errors[field.name] = "Required.";
      else properties[field.name] = null;
      continue;
    }
    if (field.type === "boolean") {
      properties[field.name] = raw === true || raw === "true";
      continue;
    }
    const text = String(raw).trim();
    switch (field.type) {
      case "integer":
        if (!/^[+-]?\d+$/.test(text)) errors[field.name] = "Enter a whole number.";
        else properties[field.name] = Number(text);
        break;
      case "decimal":
        if (!/^[+-]?(\d+\.?\d*|\.\d+)$/.test(text)) errors[field.name] = "Enter a number.";
        else properties[field.name] = Number(text);
        break;
      case "date":
        if (!validDate(text)) errors[field.name] = "Enter a date as YYYY-MM-DD.";
        else properties[field.name] = text;
        break;
      case "choice": {
        const match = (field.choices ?? []).find((c) => String(c) === text);
        if (match === undefined) errors[field.name] = "Pick one of the listed values.";
        else properties[field.name] = match;
        break;
      }
      default:
        properties[field.name] = text;
    }
  }
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, properties };
}
