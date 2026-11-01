import { useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { show, specsFrom, toRaw, type Raw } from "../specs";
import type { SpecFieldDef } from "../types";
import { Card, Field, FormError } from "./ui";

// A part's properties (stem length, reach, integration ...): the fields of its type (product_specs.py,
// sent with meta.component_types), in Add part and on the part's page. Empty = not known.

export function SpecInputs({
  fields,
  raw,
  onChange,
}: {
  fields: SpecFieldDef[];
  raw: Raw;
  onChange: (r: Raw) => void;
}) {
  const set = (k: string, v: string) => onChange({ ...raw, [k]: v });
  return (
    <div className="spec-inputs">
      {fields.map((f) => {
        const label = f.unit ? `${f.label} (${f.unit})` : f.label;
        return (
          <Field key={f.key} label={label}>
            {f.kind === "enum" || f.kind === "boolean" ? (
              <select
                aria-label={label}
                value={raw[f.key] ?? ""}
                onChange={(e) => set(f.key, e.target.value)}
              >
                <option value="">—</option>
                {(f.kind === "boolean" ? ["yes", "no"] : f.values).map((v) => (
                  <option key={v} value={v}>
                    {v.charAt(0).toUpperCase() + v.slice(1)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={label}
                inputMode={f.kind === "string" ? undefined : "decimal"}
                value={raw[f.key] ?? ""}
                onChange={(e) => set(f.key, e.target.value)}
              />
            )}
          </Field>
        );
      })}
    </div>
  );
}

// Part page: the properties that are known (own values; the product's where none is entered), and Edit.
export function PropertiesCard({
  componentId,
  fields,
  specs,
  productSpecs,
  notes,
  onChanged,
}: {
  componentId: number;
  fields: SpecFieldDef[];
  specs: Record<string, unknown>;
  productSpecs: Record<string, unknown> | null;
  notes: string | null;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const [edit, setEdit] = useState<Raw | null>(null);
  const [note, setNote] = useState(notes ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const value = (k: string) => (specs[k] ?? productSpecs?.[k]) as unknown;
  const known = fields.filter(
    (f) =>
      value(f.key) !== undefined &&
      value(f.key) !== null &&
      value(f.key) !== "",
  );
  async function save() {
    if (!edit) return;
    setErr(null);
    setBusy(true);
    try {
      const keys = new Set(fields.map((f) => f.key));
      const others = Object.fromEntries(
        Object.entries(specs).filter(([k]) => !keys.has(k)),
      );
      await api.patch(`/components/${componentId}`, {
        specs: { ...others, ...specsFrom(fields, edit) },
        notes: note.trim() || null,
      });
      toast("Properties saved.");
      setEdit(null);
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card
      title="Properties"
      className="properties-card"
      actions={
        !edit && (
          <button
            className="btn btn-small"
            onClick={() => (
              setNote(notes ?? ""),
              setEdit(toRaw(fields, { ...(productSpecs ?? {}), ...specs }))
            )}
          >
            Edit properties
          </button>
        )
      }
    >
      {edit ? (
        <div className="form">
          <SpecInputs fields={fields} raw={edit} onChange={setEdit} />
          <Field label="Notes">
            <textarea
              rows={3}
              aria-label="Notes"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anything worth knowing about this part"
            />
          </Field>
          <FormError error={err} />
          <div className="form-actions">
            <button className="btn btn-primary" disabled={busy} onClick={save}>
              Save
            </button>
            <button className="btn" onClick={() => setEdit(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : known.length === 0 && !notes ? (
        <p className="small muted">
          None entered yet. Edit properties to add them (all optional), and
          notes.
        </p>
      ) : (
        <>
          <dl className="props">
            {known.map((f) => (
              <div key={f.key}>
                <dt>{f.label}</dt>
                <dd>
                  {show(value(f.key))}
                  {f.unit && f.unit !== "°" ? ` ${f.unit}` : (f.unit ?? "")}
                  {specs[f.key] === undefined && (
                    <span className="muted small"> (from the product)</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {notes && (
            <p className="part-notes">
              <span className="muted small">Notes</span>
              <br />
              {notes}
            </p>
          )}
        </>
      )}
    </Card>
  );
}
