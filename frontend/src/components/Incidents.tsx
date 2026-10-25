import { useState } from "react";
import { Link } from "react-router-dom";
import { api, newOpId } from "../api";
import { useApp } from "../context";
import { today, when } from "../format";
import { useApi } from "../hooks";
import type { Bike, JournalRow, RideDetail } from "../types";
import { Empty, ErrorBox, Field, FormError, Loading, Tag } from "./ui";

// Incidents (flat, crash, defect) are journal issues linked to the ride and to the affected part, so they
// also appear in the journal of the bike and of that part.
export function RideIncidents({
  ride,
  onChanged,
}: {
  ride: RideDetail;
  onChanged: () => void;
}) {
  const { meta } = useApp();
  const { data, error, reload } = useApi<JournalRow[]>(
    `/journal?ride_id=${ride.id}`,
  );
  const [f, setF] = useState({
    incident_type: "FLAT",
    component_id: "",
    text: "",
    fixed: false,
  });
  const [opId, setOpId] = useState(newOpId);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // the parts this ride counted on are the ones that can have been affected
  const parts = ride.equipment.filter(
    (e, i, all) =>
      all.findIndex((x) => x.component_id === e.component_id) === i,
  );
  async function add() {
    setBusy(true);
    setErr(null);
    try {
      await api.post(
        "/journal",
        {
          ride_id: ride.id,
          incident_type: f.incident_type,
          component_id: f.component_id ? Number(f.component_id) : null,
          text: f.text || null,
          resolved_on: f.fixed ? ride.ride_date : null,
        },
        opId,
      );
      setF({ ...f, component_id: "", text: "", fixed: false });
      setOpId(newOpId());
      reload();
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="incidents">
      <h3>Incidents on this ride</h3>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && data.length === 0 && <p className="small muted">None logged.</p>}
      {data && data.length > 0 && (
        <ul className="list">
          {data.map((r) => (
            <li key={r.id}>
              <Tag tone="bad">{(r.incident_label ?? r.kind).toLowerCase()}</Tag>
              <span>
                {r.component_id ? (
                  <Link to={`/inventory/${r.component_id}`}>
                    {r.component_label}
                  </Link>
                ) : (
                  r.bike
                )}
                : {r.text}
              </span>
              {r.open_issue ? (
                <Tag tone="warn">open</Tag>
              ) : (
                <Tag tone="good">fixed {when(r.resolved_on)}</Tag>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="row">
        <Field label="What happened">
          <select
            aria-label="Incident type"
            value={f.incident_type}
            onChange={(e) => setF({ ...f, incident_type: e.target.value })}
          >
            {meta.incident_types.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Affected part"
          hint="Parts this ride counted on. Leave empty for the whole bike."
        >
          <select
            aria-label="Affected part"
            value={f.component_id}
            onChange={(e) => setF({ ...f, component_id: e.target.value })}
          >
            <option value="">{ride.bike ?? "the bike"}</option>
            {parts.map((p) => (
              <option key={p.component_id} value={p.component_id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Details (optional)">
        <input
          aria-label="Incident details"
          value={f.text}
          onChange={(e) => setF({ ...f, text: e.target.value })}
          placeholder="e.g. glass shard, front tire, plugged and continued"
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
        <button className="btn" disabled={busy} onClick={add}>
          {busy ? "Saving…" : "Log incident"}
        </button>
      </div>
    </div>
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
  async function resolve(id: number) {
    await api.patch(`/journal/${id}`, { resolved_on: today() });
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
          Open a ride and use "Log incident" for a flat, a crash or a defect.
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
                    r.bike
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
                      onClick={() => resolve(r.id)}
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
