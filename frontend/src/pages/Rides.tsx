import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, newOpId } from "../api";
import { IncidentList, RideIncidents } from "../components/Incidents";
import {
  Card,
  ChangeNotice,
  Empty,
  ErrorBox,
  Field,
  FormError,
  Loading,
  Sheet,
  Tag,
} from "../components/ui";
import { useApp } from "../context";
import { duration, km, slotName, today, when } from "../format";
import { useApi } from "../hooks";
import type {
  Bike,
  Change,
  ComponentSummary,
  OpResult,
  RideDetail,
  RideRow,
} from "../types";

interface FormState {
  bike_id: string;
  date: string;
  time: string;
  distance: string;
  unit: "km" | "mi";
  minutes: string;
  name: string;
  sport_type: string;
  usage_profile_code: string;
  assignment_uncertain: boolean;
  uncertainty_note: string;
}

const empty = (bikeId?: number | null): FormState => ({
  bike_id: bikeId ? String(bikeId) : "",
  date: today(),
  time: "",
  distance: "",
  unit: "km",
  minutes: "",
  name: "",
  sport_type: "Ride",
  usage_profile_code: "",
  assignment_uncertain: false,
  uncertainty_note: "",
});

function fromRide(r: RideRow): FormState {
  let time = "";
  if (r.start_time_utc) {
    const d = new Date(r.start_time_utc);
    time = d.toTimeString().slice(0, 5);
  }
  return {
    bike_id: r.bike_id ? String(r.bike_id) : "",
    date: r.ride_date,
    time,
    distance:
      r.distance_km !== null
        ? String(Math.round(r.distance_km * 1000) / 1000)
        : "",
    unit: "km",
    minutes: r.duration_s ? String(Math.round(r.duration_s / 60)) : "",
    name: r.name ?? "",
    sport_type: r.sport_type,
    usage_profile_code: r.usage_profile ?? "",
    assignment_uncertain: r.assignment_uncertain,
    uncertainty_note: r.uncertainty_note ?? "",
  };
}

/** Add or edit a ride. Bike + date + distance is enough. Entries survive a failed save. */
export function RideForm({
  ride,
  onSaved,
}: {
  ride?: RideRow;
  onSaved: (c: Change) => void;
}) {
  const { meta } = useApp();
  const bikes = useApi<Bike[]>("/bikes");
  const [f, setF] = useState<FormState>(() =>
    ride ? fromRide(ride) : empty(),
  );
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Change | null>(null);
  const [busy, setBusy] = useState(false);
  const [opId] = useState(newOpId);
  useEffect(() => {
    if (!ride && !f.bike_id && bikes.data?.length)
      setF((x) => ({
        ...x,
        bike_id: String(
          bikes.data!.find((b) => b.status === "ACTIVE")?.id ?? "",
        ),
      }));
  }, [bikes.data, ride, f.bike_id]);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setF({ ...f, [k]: v });

  function body(): Record<string, unknown> {
    const whenValue = f.time ? `${f.date}T${f.time}` : f.date;
    const dist =
      f.distance.trim() === "" ? null : Number(f.distance.replace(",", "."));
    const common = {
      bike_id: f.bike_id ? Number(f.bike_id) : null,
      when: whenValue,
      duration_s: f.minutes ? Math.round(Number(f.minutes) * 60) : null,
      name: f.name || null,
      sport_type: f.sport_type,
      usage_profile_code: f.usage_profile_code || null,
      assignment_uncertain: f.assignment_uncertain,
      uncertainty_note: f.uncertainty_note || null,
    };
    return ride
      ? { ...common, distance_km: dist, unit: f.unit }
      : { ...common, distance: dist, unit: f.unit };
  }
  async function save(dry: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = ride
        ? await api.patch<OpResult<RideRow>>(
            `/rides/${ride.id}${dry ? "?dry_run=true" : ""}`,
            body(),
            dry ? undefined : opId,
          )
        : await api.post<OpResult<RideRow>>("/rides", body(), opId);
      if (dry) setPreview(r.change);
      else onSaved(r.change);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="form">
      <Field label="Bike">
        <select
          value={f.bike_id}
          onChange={(e) => set("bike_id", e.target.value)}
        >
          <option value="">Unknown bike</option>
          {bikes.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="row">
        <Field label="Date">
          <input
            type="date"
            value={f.date}
            onChange={(e) => set("date", e.target.value)}
          />
        </Field>
        <Field
          label="Start time (optional)"
          hint="Leave empty if you don't know it."
        >
          <input
            type="time"
            value={f.time}
            onChange={(e) => set("time", e.target.value)}
          />
        </Field>
      </div>
      <div className="row">
        <Field label="Distance" hint="Empty = unknown (not zero).">
          <input
            inputMode="decimal"
            value={f.distance}
            onChange={(e) => set("distance", e.target.value)}
            placeholder="42"
          />
        </Field>
        <Field label="Unit">
          <select
            value={f.unit}
            onChange={(e) => set("unit", e.target.value as "km" | "mi")}
          >
            <option value="km">km</option>
            <option value="mi">mi</option>
          </select>
        </Field>
        <Field label="Minutes (optional)">
          <input
            inputMode="numeric"
            value={f.minutes}
            onChange={(e) => set("minutes", e.target.value)}
          />
        </Field>
      </div>
      <Field label="Name (optional)">
        <input value={f.name} onChange={(e) => set("name", e.target.value)} />
      </Field>
      <div className="row">
        <Field label="Type">
          <select
            value={f.sport_type}
            onChange={(e) => set("sport_type", e.target.value)}
          >
            <option value="Ride">Outdoor ride</option>
            <option value="VirtualRide">Indoor / Zwift</option>
            <option value="GravelRide">Gravel</option>
          </select>
        </Field>
        <Field
          label="Setup"
          hint="A trainer setup leaves removed parts (wheels, tires, pads) out."
        >
          <select
            value={f.usage_profile_code}
            onChange={(e) => set("usage_profile_code", e.target.value)}
          >
            <option value="">
              {f.sport_type === "VirtualRide" && !ride
                ? "Default trainer setup"
                : "Normal (outdoor)"}
            </option>
            {meta.profiles
              .filter((p) => p.kind === "TRAINER")
              .map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                </option>
              ))}
          </select>
        </Field>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={f.assignment_uncertain}
          onChange={(e) => set("assignment_uncertain", e.target.checked)}
        />{" "}
        I'm not sure about the bike or equipment
      </label>
      {f.assignment_uncertain && (
        <Field label="What is uncertain?">
          <input
            value={f.uncertainty_note}
            onChange={(e) => set("uncertainty_note", e.target.value)}
            placeholder="BMC or TIME?"
          />
        </Field>
      )}
      <ChangeNotice change={preview} />
      <FormError error={error} />
      <div className="form-actions">
        {ride && (
          <button className="btn" disabled={busy} onClick={() => save(true)}>
            Preview mileage impact
          </button>
        )}
        <button
          className="btn btn-primary"
          disabled={busy}
          onClick={() => save(false)}
        >
          {busy ? "Saving…" : ride ? "Save changes" : "Add ride"}
        </button>
      </div>
    </div>
  );
}

function RideDetailView({
  id,
  onChanged,
}: {
  id: number;
  onChanged: (c: Change | null) => void;
}) {
  const { meta } = useApp();
  const { data, error, loading, reload } = useApi<RideDetail>(`/rides/${id}`);
  const comps = useApi<ComponentSummary[]>("/components");
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [equip, setEquip] = useState({ slot: "CHAIN", component_id: "" });
  if (loading && !data) return <Loading />;
  if (error || !data)
    return <ErrorBox error={error ?? "not found"} onRetry={reload} />;
  if (editing)
    return (
      <RideForm
        ride={data}
        onSaved={(c) => {
          setEditing(false);
          reload();
          onChanged(c);
        }}
      />
    );
  async function act(
    path: string,
    body?: unknown,
    method: "post" | "put" | "del" = "post",
  ) {
    setErr(null);
    try {
      const r =
        method === "put"
          ? await api.put<OpResult<unknown>>(path, body)
          : method === "del"
            ? await api.del<OpResult<unknown>>(path)
            : await api.post<OpResult<unknown>>(path, body);
      reload();
      onChanged(r.change);
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  async function setConditions(conditions: RideRow["conditions"]) {
    setErr(null);
    try {
      await api.patch(`/rides/${id}`, { conditions });
      reload();
      onChanged(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  const slots = [
    ...new Set(
      data.equipment
        .map((e) => e.slot)
        .concat(["CHAIN", "REAR_WHEEL", "FRONT_WHEEL"]),
    ),
  ];
  return (
    <div className="form">
      <p>
        <strong>{data.name || "Ride"}</strong> ·{" "}
        {when(data.start_time_utc ?? data.ride_date)}
        {data.date_only && (
          <Tag title="No start time recorded">date only</Tag>
        )}{" "}
        · {km(data.distance_km)} · {duration(data.duration_s)} ·{" "}
        {data.bike ?? <Tag tone="warn">no bike</Tag>}
      </p>
      <p className="small muted">
        Source: {data.source_kind.toLowerCase()}
        {data.overridden_fields.length > 0 &&
          ` · locally corrected: ${data.overridden_fields.join(", ")}`}
        {data.usage_profile_name && ` · setup: ${data.usage_profile_name}`}
      </p>
      {data.inclusion === "EXCLUDED" && (
        <div className="notice">
          Removed ({data.exclusion_reason}). It counts no km and is never
          imported again from Strava or CSV. Restore it to count it again.
        </div>
      )}
      {data.flags.map((f, i) => (
        <div key={i} className="flag">
          <Tag tone="warn">{f.code.replace(/_/g, " ").toLowerCase()}</Tag>{" "}
          {f.detail}
        </div>
      ))}
      <div className="row conditions" role="group" aria-label="Conditions">
        <span className="small">Conditions:</span>
        {[{ code: null, label: "not set" }, ...meta.ride_conditions].map(
          (c) => (
            <button
              key={c.code ?? "none"}
              className={`btn btn-small ${data.conditions === c.code ? "btn-primary" : ""}`}
              aria-pressed={data.conditions === c.code}
              onClick={() => setConditions(c.code as RideRow["conditions"])}
            >
              {c.label}
            </button>
          ),
        )}
      </div>
      <RideIncidents
        ride={data}
        onChanged={() => {
          reload();
          onChanged(null);
        }}
      />
      <h3>Mileage given to parts</h3>
      {data.counting_note && <p className="notice">{data.counting_note}</p>}
      {data.equipment.length === 0 ? (
        <p className="muted">No parts received mileage from this ride.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Part</th>
              <th>Slot</th>
              <th>km</th>
              <th>Basis</th>
            </tr>
          </thead>
          <tbody>
            {data.equipment.map((e) => (
              <tr key={e.component_id}>
                <td>
                  <Link to={`/inventory/${e.component_id}`}>{e.label}</Link>
                </td>
                <td>{slotName(e.slot)}</td>
                <td>
                  {e.state === "COUNTED" ? (
                    km(e.km)
                  ) : (
                    <span className="muted">inside starting value</span>
                  )}
                </td>
                <td>
                  {e.basis === "EXPLICIT"
                    ? "confirmed"
                    : "installation history"}
                  {!e.certain && <Tag tone="warn">uncertain</Tag>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details>
        <summary>Confirm which part was used</summary>
        <div className="row">
          <Field label="Slot">
            <select
              value={equip.slot}
              onChange={(e) => setEquip({ ...equip, slot: e.target.value })}
            >
              {slots.map((s) => (
                <option key={s} value={s}>
                  {slotName(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Part">
            <select
              value={equip.component_id}
              onChange={(e) =>
                setEquip({ ...equip, component_id: e.target.value })
              }
            >
              <option value="">None used</option>
              {comps.data
                ?.filter((c) => c.status === "ACTIVE")
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} ({c.type_name})
                  </option>
                ))}
            </select>
          </Field>
        </div>
        <div className="form-actions">
          <button
            className="btn"
            onClick={() =>
              act(
                `/rides/${id}/equipment/${equip.slot}`,
                {
                  component_id: equip.component_id
                    ? Number(equip.component_id)
                    : null,
                },
                "put",
              )
            }
          >
            Confirm
          </button>
          {data.explicit_equipment.map((e) => (
            <button
              key={e.slot}
              className="btn btn-small"
              onClick={() =>
                act(`/rides/${id}/equipment/${e.slot}`, undefined, "del")
              }
            >
              Back to history for {slotName(e.slot)}
            </button>
          ))}
        </div>
      </details>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn" onClick={() => setEditing(true)}>
          Edit
        </button>
        {data.inclusion === "INCLUDED" ? (
          <button
            className="btn btn-danger"
            title="Moves it to Removed rides: it counts no km and is never imported again. You can restore it."
            onClick={() =>
              act(`/rides/${id}/exclude`, { reason: "removed by user" })
            }
          >
            Remove ride
          </button>
        ) : (
          <button className="btn" onClick={() => act(`/rides/${id}/restore`)}>
            Restore
          </button>
        )}
      </div>
    </div>
  );
}

const RIDE_TABS: [string, string][] = [
  ["active", "Rides"],
  ["unassigned", "No bike"],
  ["removed", "Removed rides"],
  ["incidents", "Incidents"],
];

function BikeSelect({
  value,
  bikes,
  onChange,
  label,
}: {
  value: number | null;
  bikes: Bike[];
  onChange: (id: number | null) => void;
  label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value ?? ""}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">— no bike —</option>
      {bikes.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name}
          {b.status === "RETIRED" ? " (retired)" : ""}
        </option>
      ))}
    </select>
  );
}

export default function RidesPage() {
  const { toast } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "active";
  const [bike, setBike] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBike, setBulkBike] = useState<number | null>(null);
  const bikes = useApi<Bike[]>("/bikes");
  const query = `/rides?limit=300&view=${tab === "removed" ? "removed" : "active"}${tab === "unassigned" ? "&unassigned=true" : ""}${bike && tab !== "unassigned" ? `&bike_id=${bike}` : ""}${flagged ? "&flagged=true" : ""}`;
  const { data, error, loading, reload } = useApi<RideRow[]>(query);
  const [adding, setAdding] = useState(false);
  const open = params.get("open");
  const go = (next: Record<string, string>) =>
    setParams({ ...(tab !== "active" ? { tab } : {}), ...next });
  const close = () => go({});
  const changed = (c: Change | null) => {
    if (c?.notice) toast(c.notice);
    reload();
  };
  useEffect(() => setSelected(new Set()), [query]);

  async function assign(ids: number[], bikeId: number | null) {
    try {
      const r = await api.post<OpResult<{ changed: number }>>(
        "/rides/assign-bike",
        { ride_ids: ids, bike_id: bikeId },
        newOpId(),
      );
      const name = bikeId
        ? bikes.data?.find((b) => b.id === bikeId)?.name
        : null;
      toast(
        `${r.result.changed} ride${r.result.changed === 1 ? "" : "s"} ${name ? `assigned to ${name}` : "now without a bike"}. ${r.change?.notice ?? ""}`,
      );
      setSelected(new Set());
      reload();
    } catch (e) {
      toast((e as Error).message);
    }
  }
  async function restore(id: number) {
    try {
      const r = await api.post<OpResult<unknown>>(`/rides/${id}/restore`, {});
      toast(r.change?.notice ?? "Restored.");
      reload();
    } catch (e) {
      toast((e as Error).message);
    }
  }
  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const allBikes = bikes.data ?? [];
  return (
    <Card
      title="Rides"
      actions={
        <button className="btn btn-primary" onClick={() => setAdding(true)}>
          Add ride
        </button>
      }
    >
      <div className="tabs" role="tablist">
        {RIDE_TABS.map(([k, l]) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            className={`tab ${tab === k ? "tab-on" : ""}`}
            onClick={() => setParams(k === "active" ? {} : { tab: k })}
          >
            {l}
          </button>
        ))}
      </div>
      {tab === "removed" && (
        <p className="small muted">
          Removed rides count no kilometres and are never imported again from
          Strava or a CSV file. Restore one to count it again.
        </p>
      )}
      {tab === "unassigned" && (
        <p className="small muted">
          Rides without a bike count for no part. Pick the bike for each ride,
          or tick several and assign them together.
        </p>
      )}
      {tab === "incidents" && <IncidentList bikes={allBikes} />}
      {tab !== "incidents" && (
        <>
          <div className="filters">
            {tab !== "unassigned" && (
              <select
                value={bike}
                onChange={(e) => setBike(e.target.value)}
                aria-label="Filter by bike"
              >
                <option value="">All bikes</option>
                {allBikes.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={flagged}
                onChange={(e) => setFlagged(e.target.checked)}
              />{" "}
              Only rides to review
            </label>
          </div>
          {tab !== "removed" && selected.size > 0 && (
            <div className="bulk-bar">
              <span>{selected.size} selected</span>
              <BikeSelect
                label="Bike for selected rides"
                value={bulkBike}
                bikes={allBikes.filter((b) => b.status === "ACTIVE")}
                onChange={setBulkBike}
              />
              <button
                className="btn btn-primary btn-small"
                onClick={() => assign([...selected], bulkBike)}
              >
                {bulkBike ? "Assign bike" : "Remove bike"}
              </button>
              <button
                className="btn btn-small"
                onClick={() => setSelected(new Set())}
              >
                Clear
              </button>
            </div>
          )}
          {loading && !data && <Loading what="Loading rides" />}
          {error && <ErrorBox error={error} onRetry={reload} />}
          {data && data.length === 0 && (
            <Empty
              title={
                tab === "removed"
                  ? "No removed rides"
                  : tab === "unassigned"
                    ? "Every ride has a bike"
                    : flagged
                      ? "No rides need review"
                      : "No rides yet"
              }
            >
              {tab === "active" &&
                !flagged &&
                "Add a ride (bike, date and distance are enough), import a CSV or connect Strava under Settings."}
            </Empty>
          )}
          {data && data.length > 0 && (
            <table className="table rides">
              <thead>
                <tr>
                  {tab !== "removed" && (
                    <th>
                      <input
                        type="checkbox"
                        aria-label="Select all rides"
                        checked={selected.size === data.length}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? new Set(data.map((r) => r.id))
                              : new Set(),
                          )
                        }
                      />
                    </th>
                  )}
                  <th>Date</th>
                  <th>Name</th>
                  <th>Bike</th>
                  <th className="num">Distance</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr
                    key={r.id}
                    className={r.removed ? "excluded" : ""}
                    onClick={() => go({ open: String(r.id) })}
                  >
                    {tab !== "removed" && (
                      <td onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.name || "ride"} ${r.ride_date}`}
                          checked={selected.has(r.id)}
                          onChange={() => toggle(r.id)}
                        />
                      </td>
                    )}
                    <td>{when(r.start_time_utc ?? r.ride_date)}</td>
                    <td>
                      <button className="linklike">{r.name || "Ride"}</button>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {r.removed ? (
                        (r.bike ?? "—")
                      ) : (
                        <BikeSelect
                          label={`Bike for ${r.name || "ride"} ${r.ride_date}`}
                          value={r.bike_id}
                          bikes={allBikes}
                          onChange={(id) => assign([r.id], id)}
                        />
                      )}
                      {r.bike_overridden && (
                        <span
                          className="small muted"
                          title="Your choice is kept when Strava or a CSV import is read again."
                        >
                          {" "}
                          changed by you · {r.source_kind.toLowerCase()}:{" "}
                          {r.source_bike ?? "no bike"}
                        </span>
                      )}
                      {!r.bike_id && !r.bike_overridden && r.uncertainty_note && (
                        <span className="small muted"> {r.uncertainty_note}</span>
                      )}
                    </td>
                    <td className="num">{km(r.distance_km)}</td>
                    <td>
                      {r.removed && (
                        <Tag>
                          {r.status === "SOURCE_DELETED"
                            ? "deleted at source"
                            : "removed"}
                        </Tag>
                      )}
                      {r.removed && r.inclusion === "EXCLUDED" && (
                        <button
                          className="btn btn-small"
                          onClick={(e) => {
                            e.stopPropagation();
                            restore(r.id);
                          }}
                        >
                          Restore
                        </button>
                      )}
                      {r.sport_type === "VirtualRide" && (
                        <Tag tone="info">indoor</Tag>
                      )}
                      {r.conditions === "WET" && <Tag tone="info">wet</Tag>}
                      {r.incidents > 0 && (
                        <Tag tone="bad">
                          {r.incidents === 1
                            ? "1 incident"
                            : `${r.incidents} incidents`}
                        </Tag>
                      )}
                      {r.source_kind !== "MANUAL" && (
                        <Tag>{r.source_kind.toLowerCase()}</Tag>
                      )}
                      {r.flags.map((f, i) => (
                        <Tag key={i} tone="warn" title={f.detail}>
                          {f.code.replace(/_/g, " ").toLowerCase()}
                        </Tag>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {adding && (
        <Sheet title="Add ride" onClose={() => setAdding(false)}>
          <RideForm
            onSaved={(c) => {
              setAdding(false);
              changed(c);
            }}
          />
        </Sheet>
      )}
      {open && (
        <Sheet title="Ride" onClose={close}>
          <RideDetailView id={Number(open)} onChanged={changed} />
        </Sheet>
      )}
    </Card>
  );
}
