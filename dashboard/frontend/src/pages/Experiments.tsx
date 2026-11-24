import { useMemo, useState } from "react";
import { usePoll } from "../hooks/usePoll";
import type { ExperimentDetailSchema, RoundSchema } from "../api/types";
import { formatDateTime, formatNumber } from "../lib/format";
import { Badge, Empty, Panel, Stat, StatusBadge } from "../components/primitives";

export function ExperimentsPage() {
  const poll = usePoll<ExperimentDetailSchema[]>("/api/v1/experiments", 10000);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);

  const rounds = usePoll<RoundSchema[]>(
    selected ? `/api/v1/experiments/${encodeURIComponent(selected)}/rounds?limit=100` : null,
    0,
  );

  const experiments = poll.data ?? [];
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return experiments.filter((experiment) => {
      const matchesStatus = status === "all" || experiment.status === status;
      const matchesSearch =
        !needle ||
        experiment.name.toLowerCase().includes(needle) ||
        experiment.id.toLowerCase().includes(needle) ||
        experiment.model_name.toLowerCase().includes(needle);
      return matchesStatus && matchesSearch;
    });
  }, [experiments, search, status]);

  const counts = {
    total: experiments.length,
    running: experiments.filter((experiment) => experiment.status === "running").length,
    completed: experiments.filter((experiment) => experiment.status === "completed").length,
    failed: experiments.filter((experiment) => experiment.status === "failed").length,
  };
  const selectedExperiment = experiments.find((experiment) => experiment.id === selected) ?? null;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Experiments</h1>
          <p className="page-sub">
            Experiment records stored by the backend. A status is whatever the database reports; this
            page does not infer completion.
          </p>
        </div>
        <div className="toolbar">
          <input
            className="input"
            style={{ width: 220 }}
            type="search"
            placeholder="Search name, id, model…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select className="select" style={{ width: 140 }} value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <button className="btn btn-sm" type="button" onClick={poll.refresh}>
            Refresh
          </button>
        </div>
      </div>

      {poll.error && <div className="notice notice-bad">Experiments API: {poll.error}</div>}

      <div className="stat-grid">
        <Stat label="Total experiments" value={counts.total} sub="all records" />
        <Stat label="Running" value={counts.running} sub="reported by the database" />
        <Stat label="Completed" value={counts.completed} sub="reported by the database" />
        <Stat label="Failed" value={counts.failed} sub="reported by the database" />
      </div>

      <Panel
        title="Experiment records"
        subtitle={`${filtered.length} of ${experiments.length} shown`}
        bodyTight
        actions={selected ? <button className="btn btn-sm" type="button" onClick={() => setSelected(null)}>Clear selection</button> : null}
      >
        {filtered.length === 0 ? (
          <Empty
            title={experiments.length === 0 ? "No experiments recorded" : "No matches"}
            hint={
              experiments.length === 0
                ? "Experiments are created through the REST API. Nothing is fabricated here."
                : "Adjust the search or status filter."
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th className="right">Epochs</th>
                  <th className="right">LR</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((experiment) => (
                  <tr
                    key={experiment.id}
                    onClick={() => setSelected(experiment.id)}
                    style={{ cursor: "pointer", background: selected === experiment.id ? "var(--surface-2)" : undefined }}
                  >
                    <td className="primary">{experiment.name}</td>
                    <td className="mono">{experiment.id}</td>
                    <td>{experiment.experiment_type}</td>
                    <td><StatusBadge status={experiment.status} /></td>
                    <td className="mono">{experiment.model_name}</td>
                    <td className="num">{experiment.epochs}</td>
                    <td className="num">{experiment.learning_rate}</td>
                    <td className="mono small">{formatDateTime(experiment.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {selectedExperiment && (
        <div className="cols-2">
          <Panel title={`Experiment ${selectedExperiment.id}`} subtitle={selectedExperiment.name} bodyTight>
            <dl className="kv" style={{ padding: "4px 16px 12px" }}>
              <div><dt>Type</dt><dd className="mono">{selectedExperiment.experiment_type}</dd></div>
              <div><dt>Status</dt><dd><StatusBadge status={selectedExperiment.status} /></dd></div>
              <div><dt>Model</dt><dd className="mono">{selectedExperiment.model_name} {selectedExperiment.model_version}</dd></div>
              <div><dt>Seed</dt><dd className="mono">{selectedExperiment.seed}</dd></div>
              <div><dt>Epochs</dt><dd className="mono">{selectedExperiment.epochs}</dd></div>
              <div><dt>Batch size</dt><dd className="mono">{selectedExperiment.batch_size}</dd></div>
              <div><dt>Learning rate</dt><dd className="mono">{selectedExperiment.learning_rate}</dd></div>
              <div><dt>Created</dt><dd className="mono">{formatDateTime(selectedExperiment.created_at)}</dd></div>
              <div><dt>Started</dt><dd className="mono">{formatDateTime(selectedExperiment.started_at)}</dd></div>
              <div><dt>Completed</dt><dd className="mono">{formatDateTime(selectedExperiment.completed_at)}</dd></div>
            </dl>
          </Panel>

          <Panel
            title="Rounds"
            subtitle="Round rows from the experiment database"
            actions={<Badge tone={rounds.data?.length ? "accent" : "neutral"}>{rounds.data?.length ?? 0} rows</Badge>}
            bodyTight
          >
            {rounds.error ? (
              <div className="notice notice-bad" style={{ margin: 16 }}>{rounds.error}</div>
            ) : (rounds.data?.length ?? 0) === 0 ? (
              <Empty title="No round rows" hint="This experiment has no submitted rounds yet." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Round</th>
                      <th>Status</th>
                      <th className="right">Selected</th>
                      <th className="right">Received</th>
                      <th className="right">Val loss</th>
                      <th>Version</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rounds.data?.map((row) => (
                      <tr key={row.round_number}>
                        <td className="primary mono">{row.round_number}</td>
                        <td>{row.status}</td>
                        <td className="num">{row.selected_count}</td>
                        <td className="num">{row.received_count}</td>
                        <td className="num">{formatNumber(row.weighted_val_loss, 4)}</td>
                        <td className="mono">{row.model_version || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
