import { useState } from "react";
import { Link } from "react-router-dom";
import { api, newOpId } from "../api";
import { useApp } from "../context";
import { today, when } from "../format";
import { useApi } from "../hooks";
import type {
  Bike,
  IncidentChoice,
  JournalRow,
  RideDetail,
  RideIncident,
} from "../types";
import { Empty, ErrorBox, Field, FormError, Loading, Tag } from "./ui";

// An incident (flat, shifting problem, empty battery, numb hands ...) is stored as one journal issue per
// affected part, so each part shows it in its own journal. What can be picked depends on the incident type
// and on the parts that were on the bike that day; several can be picked (two flats, both derailleurs).
// Removing an incident never deletes it: it is voided and can be restored.
type IncidentForm = {
  incident_type: string;
  affected: string[];
  text: string;
  fixed: boolean;
};

function IncidentEditor({
  ride,
  choices,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  ride: RideDetail;
  choices: Record<string, IncidentChoice[]>;
  initial: IncidentForm;
  submitLabel: string;
  onSubmit: (f: IncidentForm) => Promise<void>;
  onCancel?: () => void;
}) {
  const { meta } = useApp();
  const [f, setF] = useState<IncidentForm>(initial);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options = choices[f.incident_type] ?? [];
  const forRider = f.incident_type === "FIT";
  function toggle(key: string) {
    setF({
      ...f,
      affected: f.affected.includes(key)
        ? f.affected.filter((k) => k !== key)
        : [...f.affected, key],
    });
  }
  async function submit() {
    if (!f.affected.length)
      return setErr(
        forRider
          ? "Tick at least one problem."
          : "Tick at least one affected part (or Whole bike).",
      );
    setBusy(true);
    setErr(null);
    try {
      await onSubmit(f);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="incident-form">
      <Field label="What happened">
        <select
          aria-label="Incident type"
          value={f.incident_type}
          onChange={(e) =>
            setF({ ...f, incident_type: e.target.value, affected: [] })
          }
        >
          {meta.incident_types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </select>
      </Field>
      <fieldset className="incident-affected">
        <legend className="field-label">
          {forRider ? "Where (tick all that apply)" : "Affected (tick all that apply)"}
        </legend>
        <div className="chips" role="group" aria-label="Affected">
          {options.map((o) => (
            <label
              key={o.key}
              className={`chip chip-check ${f.affected.includes(o.key) ? "chip-on" : ""}`}
              title={
                o.recorded
                  ? undefined
                  : "No such part recorded on this bike for that day"
              }
            >
              <input
                type="checkbox"
                checked={f.affected.includes(o.key)}
                onChange={() => toggle(o.key)}
              />
              {o.label}
            </label>
          ))}
        </div>
        {options.some((o) => !o.recorded) && (
          <span className="field-hint">
            Names without a part: nothing of that kind is recorded on{" "}
            {ride.bike ?? "the bike"} for this day. You can still pick it.
          </span>
        )}
      </fieldset>
      <Field label="Details (optional)">
        <input
          aria-label="Incident details"
          value={f.text}
          onChange={(e) => setF({ ...f, text: e.target.value })}
          placeholder="e.g. glass shard, plugged and continued"
        />
      </Field>
      <label className="check">
        <input
          type="checkbox"
          checked={f.fixed}
          onChange={(e) => setF({ ...f, fixed: e.target.checked })}
        />{" "}
        Already fixed
      </label>
      <FormError error={err} />
      <div className="form-actions">
        {onCancel && (
          <button className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </div>
  );
}

export function RideIncidents({
  ride,
  onChanged,
}: {
  ride: RideDetail;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const { data, error, reload } = useApi<{
    incidents: RideIncident[];
    choices: Record<string, IncidentChoice[]>;
  }>(`/rides/${ride.id}/incidents`);
  const [mode, setMode] = useState<"list" | "add" | string>("list");
  const [opId, setOpId] = useState(newOpId);
  const [err, setErr] = useState<string | null>(null);
  function changed() {
    setMode("list");
    reload();
    onChanged();
  }
  async function add(f: IncidentForm) {
    await api.post(
      `/rides/${ride.id}/incidents`,
      {
        incident_type: f.incident_type,
        affected: f.affected,
        text: f.text || null,
        resolved_on: f.fixed ? ride.ride_date : null,
      },
      opId,
    );
    setOpId(newOpId());
    changed();
  }
  async function save(r: RideIncident, f: IncidentForm) {
    await api.patch(`/incidents/${r.group}`, {
      incident_type: f.incident_type,
      affected: f.affected,
      text: f.text || null,
      resolved_on: f.fixed ? (r.resolved_on ?? today()) : null,
    });
    changed();
  }
  async function act(r: RideIncident, what: "remove" | "restore") {
    setErr(null);
    try {
      await api.post(`/incidents/${r.group}/${what}`, {});
      toast(
        what === "remove"
          ? `${r.label} removed from this ride. It is kept and can be restored.`
          : `${r.label} restored.`,
      );
      changed();
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  const live = data?.incidents.filter((r) => !r.removed) ?? [];
  const removed = data?.incidents.filter((r) => r.removed) ?? [];
  return (
    <section className="ride-section incidents" aria-label="Incidents">
      <div className="ride-section-head">
        <h3>Incidents</h3>
        {mode === "list" && data && (
          <button className="btn btn-small" onClick={() => setMode("add")}>
            Log incident
          </button>
        )}
      </div>
      {error && <ErrorBox error={error} onRetry={reload} />}
      <FormError error={err} />
      {data && live.length === 0 && mode !== "add" && (
        <p className="small muted">None logged.</p>
      )}
      {live.length > 0 && (
        <ul className="incident-list">
          {live.map((r) =>
            mode === r.group && data ? (
              <li key={r.group}>
                <IncidentEditor
                  ride={ride}
                  choices={data.choices}
                  initial={{
                    incident_type: r.incident_type,
                    affected: r.affected.map((a) => a.key),
                    text: r.text ?? "",
                    fixed: !r.open,
                  }}
                  submitLabel="Save changes"
                  onSubmit={(f) => save(r, f)}
                  onCancel={() => setMode("list")}
                />
              </li>
            ) : (
              <li key={r.group} className="incident-row">
                <div>
                  <Tag tone="bad">{r.label.toLowerCase()}</Tag>{" "}
                  {r.affected.map((a, i) => (
                    <span key={a.key}>
                      {i > 0 && ", "}
                      {a.component_id ? (
                        <Link to={`/inventory/${a.component_id}`}>{a.label}</Link>
                      ) : (
                        a.label
                      )}
                    </span>
                  ))}
                  {r.text && <div className="small">{r.text}</div>}
                </div>
                <div className="incident-actions">
                  {r.open ? (
                    <Tag tone="warn">open</Tag>
                  ) : (
                    <Tag tone="good">fixed {when(r.resolved_on)}</Tag>
                  )}
                  <button
                    className="btn btn-small"
                    onClick={() => setMode(r.group)}
                  >
                    Edit
                  </button>
                  <button
                    className="btn btn-small"
                    onClick={() => act(r, "remove")}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ),
          )}
        </ul>
      )}
      {mode === "add" && data && (
        <IncidentEditor
          ride={ride}
          choices={data.choices}
          initial={{ incident_type: "FLAT", affected: [], text: "", fixed: false }}
          submitLabel="Log incident"
          onSubmit={add}
          onCancel={() => setMode("list")}
        />
      )}
      {removed.length > 0 && (
        <details className="small">
          <summary>Removed incidents ({removed.length})</summary>
          <ul className="incident-list">
            {removed.map((r) => (
              <li key={r.group} className="incident-row muted">
                <span>
                  {r.label}: {r.affected.map((a) => a.label).join(", ")}
                </span>
                <button
                  className="btn btn-small"
                  onClick={() => act(r, "restore")}
                >
                  Restore
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

// All incidents, newest first (Rides → Incidents).
export function IncidentList({ bikes }: { bikes: Bike[] }) {
  const { meta } = useApp();
  const [bike, setBike] = useState("");
  const [type, setType] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  const q = new URLSearchParams();
  if (bike) q.set("bike_id", bike);
  if (type) q.set("incident_type", type);
  if (openOnly) q.set("open_only", "true");
  const { data, error, loading, reload } = useApi<JournalRow[]>(
    `/incidents?${q.toString()}`,
  );
  async function resolve(r: JournalRow) {
    // the whole incident is fixed (both tires of a double flat), not just this row
    if (r.incident_group)
      await api.patch(`/incidents/${r.incident_group}`, { resolved_on: today() });
    else await api.patch(`/journal/${r.id}`, { resolved_on: today() });
    reload();
  }
  return (
    <>
      <div className="row filters">
        <select
          aria-label="Filter incidents by bike"
          value={bike}
          onChange={(e) => setBike(e.target.value)}
        >
          <option value="">All bikes</option>
          {bikes.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter incidents by type"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">All incidents</option>
          {meta.incident_types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </select>
        <label className="check">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => setOpenOnly(e.target.checked)}
          />{" "}
          Open only
        </label>
      </div>
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <Empty title="No incidents">
          Open a ride and use "Log incident" for a flat, a shifting problem, an empty battery or anything else that happened.
        </Empty>
      )}
      {data && data.length > 0 && (
        <table className="table incidents-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>What</th>
              <th>Part</th>
              <th>Ride</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td>{when(r.on)}</td>
                <td>
                  <Tag tone="bad">{(r.incident_label ?? "").toLowerCase()}</Tag>{" "}
                  <span className="small">
                    {r.text !== r.incident_label ? r.text : ""}
                  </span>
                </td>
                <td>
                  {r.component_id ? (
                    <Link to={`/inventory/${r.component_id}`}>
                      {r.component_label}
                    </Link>
                  ) : (
                    (r.affected ?? r.bike)
                  )}
                </td>
                <td>
                  {r.ride_id ? (
                    <Link to={`/rides?open=${r.ride_id}`}>{r.ride_label}</Link>
                  ) : (
                    "—"
                  )}
                  {r.ride_conditions === "WET" && <Tag tone="info">wet</Tag>}
                </td>
                <td>
                  {r.open_issue ? (
                    <button
                      className="btn btn-small"
                      onClick={() => resolve(r)}
                    >
                      Mark fixed
                    </button>
                  ) : (
                    <span className="small muted">
                      fixed {when(r.resolved_on)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
