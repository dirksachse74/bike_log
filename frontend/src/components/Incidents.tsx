import { useState } from "react";
import { Link } from "react-router-dom";
import { api, newOpId } from "../api";
import { useApp } from "../context";
import { today, when } from "../format";
import { useApi } from "../hooks";
import type {
  Bike,
  IncidentChoice,
  RideDetail,
  RideIncident,
  SpareCheck,
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
  bikeName,
  choices,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  bikeName: string | null;
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
      {f.incident_type === "FLAT" && options.some((o) => o.wheel) ? (
        <FlatDamage
          options={options}
          affected={f.affected}
          onChange={(affected) => setF({ ...f, affected })}
        />
      ) : (
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
            {bikeName ?? "the bike"} for this day. You can still pick it.
          </span>
        )}
      </fieldset>
      )}
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
        Already solved
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

// A flat, per wheel: not affected, the tube only, or the tube and the tire (a tubeless or tubular wheel:
// the tire). Still one incident; the answer becomes the affected tube and/or tire of that wheel.
const WHEELS: [string, string][] = [
  ["FRONT_WHEEL", "Front wheel"],
  ["REAR_WHEEL", "Rear wheel"],
];

function FlatDamage({
  options,
  affected,
  onChange,
}: {
  options: IncidentChoice[];
  affected: string[];
  onChange: (affected: string[]) => void;
}) {
  const spares = useApi<SpareCheck[]>("/spares/check");
  const shown = (spares.data ?? []).filter(
    (r) => r.component_type === "INNER_TUBE" || r.component_type === "TIRE",
  );
  return (
    <fieldset className="incident-affected">
      <legend className="field-label">What was damaged?</legend>
      {WHEELS.map(([wheel, name]) => {
        const tubes = options.filter((o) => o.wheel === wheel && o.damage === "TUBE");
        const tires = options.filter((o) => o.wheel === wheel && o.damage === "TIRE");
        if (!tubes.length && !tires.length) return null;
        const hasTube = tubes.some((o) => affected.includes(o.key));
        const hasTire = tires.some((o) => affected.includes(o.key));
        const value = hasTube && hasTire ? "both" : hasTube ? "tube" : hasTire ? "tire" : "none";
        const picks: [string, string][] = tubes.length
          ? [
              ["none", "Not affected"],
              ["tube", "Tube only"],
              ["both", "Tube and tire"],
              ...(value === "tire" ? [["tire", "Tire only"] as [string, string]] : []),
            ]
          : [
              ["none", "Not affected"],
              ["tire", "Tire"],
            ];
        const mine = new Set([...tubes, ...tires].map((o) => o.key));
        const set = (v: string) =>
          onChange([
            ...affected.filter((k) => !mine.has(k)),
            ...(v === "tube" || v === "both" ? tubes.map((o) => o.key) : []),
            ...(v === "tire" || v === "both" ? tires.map((o) => o.key) : []),
          ]);
        const recorded = [...tubes, ...tires].filter((o) => o.recorded).map((o) => o.label.split(": ").pop());
        return (
          <div key={wheel} className="flat-wheel" role="radiogroup" aria-label={name}>
            <span className="flat-wheel-name">
              {name}
              {recorded.length > 0 && <span className="small muted"> · {recorded.join(", ")}</span>}
              {!tubes.length && <span className="small muted"> · tubeless or tubular</span>}
            </span>
            <div className="chips">
              {picks.map(([v, label]) => (
                <label key={v} className={`chip ${value === v ? "chip-on" : ""}`}>
                  <input
                    type="radio"
                    className="sr-only"
                    name={`flat-${wheel}`}
                    checked={value === v}
                    onChange={() => set(v)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
        );
      })}
      {shown.length > 0 && (
        <p className="small spare-hint">
          Spares at home:{" "}
          {shown.map((r, i) => (
            <span key={r.component_type}>
              {i > 0 && " · "}
              {r.text} {r.low && <Tag tone="warn">low</Tag>}
            </span>
          ))}{" "}
          <Link to="/inventory?tab=shopping">Shopping list</Link>
        </p>
      )}
    </fieldset>
  );
}

type Choices = Record<string, IncidentChoice[]>;

// The incident rows with Solved / Re-open, Edit and Remove, plus the removed ones with Restore. Used on the
// ride (choices already loaded) and on the bike (choices of the incident's ride are loaded on Edit).
function IncidentRows({
  incidents,
  choices,
  bikeName,
  showRide,
  showBike,
  onChanged,
}: {
  incidents: RideIncident[];
  choices?: Choices;
  bikeName: string | null;
  showRide?: boolean;
  showBike?: boolean;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const [editing, setEditing] = useState<{
    group: string;
    choices: Choices;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      setEditing(null);
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  async function edit(r: RideIncident) {
    setErr(null);
    try {
      const c =
        choices ??
        (
          await api.get<{ choices: Choices }>(
            `/rides/${r.ride_id}/incidents`,
          )
        ).choices;
      setEditing({ group: r.group, choices: c });
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  async function save(r: RideIncident, f: IncidentForm) {
    await api.patch(`/incidents/${r.group}`, {
      incident_type: f.incident_type,
      affected: f.affected,
      text: f.text || null,
      resolved_on: f.fixed ? (r.resolved_on ?? today()) : null,
    });
    setEditing(null);
    onChanged();
  }
  const where = showRide ? "" : " from this ride";
  const live = incidents.filter((r) => !r.removed);
  const removed = incidents.filter((r) => r.removed);
  return (
    <>
      <FormError error={err} />
      {live.length > 0 && (
        <ul className="incident-list">
          {live.map((r) =>
            editing?.group === r.group ? (
              <li key={r.group}>
                <IncidentEditor
                  bikeName={bikeName}
                  choices={editing.choices}
                  initial={{
                    incident_type: r.incident_type,
                    affected: r.affected.map((a) => a.key),
                    text: r.text ?? "",
                    fixed: !r.open,
                  }}
                  submitLabel="Save changes"
                  onSubmit={(f) => save(r, f)}
                  onCancel={() => setEditing(null)}
                />
              </li>
            ) : (
              <li key={r.group} className="incident-row">
                <div className="incident-type">
                  <Tag tone="bad">{r.label.toLowerCase()}</Tag>
                  <div className="small muted">{when(r.on)}</div>
                </div>
                <div className="incident-what">
                  <div>
                    {r.affected.map((a, i) => (
                      <span key={a.key}>
                        {i > 0 && " + "}
                        {a.component_id ? (
                          <Link to={`/inventory/${a.component_id}`}>{a.label}</Link>
                        ) : (
                          a.label
                        )}
                      </span>
                    ))}
                  </div>
                  {r.text && <div className="small">{r.text}</div>}
                  {showRide && r.ride_id && (
                    <div className="small muted">
                      {showBike && r.bike ? `${r.bike} · ` : ""}
                      <Link to={`/rides?open=${r.ride_id}`}>{r.ride_label}</Link>
                      {r.ride_conditions === "WET" && (
                        <>
                          {" "}
                          <Tag tone="info">wet</Tag>
                        </>
                      )}
                    </div>
                  )}
                </div>
                <div className="incident-status">
                  {r.open ? (
                    <Tag tone="warn">open</Tag>
                  ) : (
                    <Tag tone="good">solved {when(r.resolved_on)}</Tag>
                  )}
                </div>
                <div className="incident-actions">
                  {r.open ? (
                    <>
                      <button
                        className="btn btn-small btn-primary"
                        onClick={() =>
                          run(() =>
                            api.patch(`/incidents/${r.group}`, {
                              resolved_on: today(),
                            }),
                          )
                        }
                      >
                        Solved
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="btn btn-small"
                        onClick={() =>
                          run(() =>
                            api.patch(`/incidents/${r.group}`, {
                              resolved_on: null,
                            }),
                          )
                        }
                      >
                        Re-open
                      </button>
                    </>
                  )}
                  {r.ride_id && (
                    <button className="btn btn-small" onClick={() => edit(r)}>
                      Edit
                    </button>
                  )}
                  <button
                    className="btn btn-small"
                    onClick={() =>
                      run(async () => {
                        await api.post(`/incidents/${r.group}/remove`, {});
                        toast(
                          `${r.label} removed${where}. It is kept and can be restored.`,
                        );
                      })
                    }
                  >
                    Remove
                  </button>
                </div>
              </li>
            ),
          )}
        </ul>
      )}
      {removed.length > 0 && (
        <details className="small">
          <summary>Removed incidents ({removed.length})</summary>
          <ul className="incident-list">
            {removed.map((r) => (
              <li key={r.group} className="incident-removed muted">
                <span>
                  {r.label}: {r.affected.map((a) => a.label).join(", ")}
                  {showRide && r.ride_label ? ` · ${r.ride_label}` : ""}
                </span>
                <button
                  className="btn btn-small"
                  onClick={() =>
                    run(async () => {
                      await api.post(`/incidents/${r.group}/restore`, {});
                      toast(`${r.label} restored.`);
                    })
                  }
                >
                  Restore
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

export function RideIncidents({
  ride,
  onChanged,
}: {
  ride: RideDetail;
  onChanged: () => void;
}) {
  const { data, error, reload } = useApi<{
    incidents: RideIncident[];
    choices: Choices;
  }>(`/rides/${ride.id}/incidents`);
  const [adding, setAdding] = useState(false);
  const [opId, setOpId] = useState(newOpId);
  function changed() {
    setAdding(false);
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
  const live = data?.incidents.filter((r) => !r.removed) ?? [];
  return (
    <section className="ride-section incidents" aria-label="Incidents">
      <div className="ride-section-head">
        <h3>Incidents</h3>
        {!adding && data && (
          <button className="btn btn-small" onClick={() => setAdding(true)}>
            Add incident
          </button>
        )}
      </div>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && live.length === 0 && !adding && (
        <p className="small muted">None logged.</p>
      )}
      {data && (
        <IncidentRows
          incidents={data.incidents}
          choices={data.choices}
          bikeName={ride.bike}
          onChanged={changed}
        />
      )}
      {adding && data && (
        <IncidentEditor
          bikeName={ride.bike}
          choices={data.choices}
          initial={{ incident_type: "FLAT", affected: [], text: "", fixed: false }}
          submitLabel="Add incident"
          onSubmit={add}
          onCancel={() => setAdding(false)}
        />
      )}
    </section>
  );
}

// Every incident on a bike (bike page → Incidents), with the same Solved / Re-open, Edit and Remove.
export function BikeIncidents({
  incidents,
  error,
  loading,
  reload,
  bikeName,
}: {
  incidents: RideIncident[] | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  bikeName: string;
}) {
  if (loading && !incidents) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!incidents?.length)
    return (
      <Empty title="No incidents on this bike">
        Log a flat, a shifting problem or anything else on the ride it
        happened (Rides → open the ride → Add incident).
      </Empty>
    );
  return (
    <IncidentRows
      incidents={incidents}
      bikeName={bikeName}
      showRide
      onChanged={reload}
    />
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
  const { data, error, loading, reload } = useApi<RideIncident[]>(
    `/incidents?${q.toString()}`,
  );
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
          Open a ride and use "Add incident" for a flat, a shifting problem, an empty battery or anything else that happened.
        </Empty>
      )}
      {data && data.length > 0 && (
        <IncidentRows
          incidents={data}
          bikeName={null}
          showRide
          showBike
          onChanged={reload}
        />
      )}
    </>
  );
}
