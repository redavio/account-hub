import { useEffect, useMemo, useState } from "react";
import type { Results, Step, StepAccount, Test } from "./types";

const money = (n: number) =>
  n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`;
const pct = (n: number | null | undefined) => (n === null || n === undefined ? "–" : `${Math.round(n * 100)}%`);
const DEPTHS = ["Not reached", "Reached", "Engaged"] as const;
const COVERAGE = ["None", "1 role", "2+ roles"] as const;
const VIEWS = {
  started: "Started by marketing",
  touched: "Touched by marketing",
  caused: "Caused by marketing",
} as const;
const TERMS: Record<keyof typeof VIEWS, string> = {
  started: "Sourced: accounts whose first touch was marketing.",
  touched: "Influenced: advances credited equally to every engaged marketing touch in the window. Credit, not proof.",
  caused: "Incremental: the extra advances marketing caused, testing each channel and role with the others held fixed.",
};

type Tab = "funnel" | "grid" | "accounts";
type Pick = { title: string; ids: string[] } | null;

export default function App() {
  const [res, setRes] = useState<Results | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("funnel");
  const [pick, setPick] = useState<Pick>(null);

  useEffect(() => {
    const src = new URLSearchParams(location.search).get("src") || "results.json";
    fetch(src)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Couldn't load ${src}`))))
      .then(setRes)
      .catch((e) => setError(e.message));
  }, []);

  const open = (file: File) =>
    file.text().then((t) => {
      try {
        setRes(JSON.parse(t));
        setError("");
      } catch {
        setError("That file isn't an Account Hub results file.");
      }
    });

  const show = (title: string, ids: string[]) => {
    setPick({ title, ids });
    setTab("accounts");
  };

  return (
    <div className="page">
      <header>
        <div>
          <h1>Account Hub <span className="muted">· Performance</span></h1>
          {res && <p className="muted">Data through {res.as_of}. Touches since {res.touch_history_start}.</p>}
        </div>
        <label className="file">
          Open results file
          <input type="file" accept=".json" onChange={(e) => e.target.files?.[0] && open(e.target.files[0])} />
        </label>
      </header>
      {error && <p className="note">{error} Run the engine, then open results.json here.</p>}
      {res && (
        <>
          <Headline res={res} />
          <nav>
            {(["funnel", "grid", "accounts"] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
                {t === "funnel" ? "Funnel" : t === "grid" ? "Step grid" : "Accounts"}
              </button>
            ))}
          </nav>
          {tab === "funnel" && <Funnel res={res} show={show} />}
          {tab === "grid" && <Grid res={res} show={show} />}
          {tab === "accounts" && <Accounts res={res} pick={pick} clear={() => setPick(null)} />}
        </>
      )}
    </div>
  );
}

function Headline({ res }: { res: Results }) {
  const h = res.headline;
  const caused = h.caused_by_marketing;
  const cards: [string, string, string][] = [
    ["Pipeline", money(h.pipeline_total), `${h.opportunities} opportunities`],
    [VIEWS.started, money(h.started_by_marketing.pipeline), "sourced"],
    [VIEWS.touched, money(h.touched_by_marketing.pipeline), "influenced"],
    [VIEWS.caused, caused.status === "lift" ? money(caused.pipeline) : caused.status, `incremental, ${caused.label}`],
    ["Won", money(h.won_total), `win rate ${pct(h.win_rate)}`],
  ];
  return (
    <section className="cards">
      {cards.map(([label, value, sub]) => (
        <div key={label} className="card">
          <div className="muted small">{label}</div>
          <div className="big">{value}</div>
          <div className="muted small">{sub}</div>
        </div>
      ))}
    </section>
  );
}

function Funnel({ res, show }: { res: Results; show: (t: string, ids: string[]) => void }) {
  return (
    <section>
      <p className="help">Value per stage is pipeline $: the share of accounts at the stage that become an Opportunity, times the average Opportunity.</p>
      <table>
        <thead>
          <tr><th>Stage</th><th>Accounts</th><th>Advance rate to next stage</th><th>Value per account (pipeline $)</th></tr>
        </thead>
        <tbody>
          {res.funnel.map((f) => (
            <tr key={f.stage}>
              <td>{f.label}</td>
              <td><button className="num" onClick={() => show(f.label, f.account_ids)}>{f.accounts}</button></td>
              <td>{pct(f.advance_rate)}</td>
              <td>{money(f.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const statusText = (t: Test) =>
  t.status === "lift" ? `+${Math.round(t.lift * 100)} pts` :
  t.status === "negative" ? `${Math.round(t.lift * 100)} pts` :
  t.status === "not enough data yet" ? `not enough data yet (~${t.more_accounts_needed.toLocaleString()} more accounts)` : "no lift found";

function Grid({ res, show }: { res: Results; show: (t: string, ids: string[]) => void }) {
  const [stepKey, setStepKey] = useState(res.steps[0]?.step);
  const [view, setView] = useState<keyof typeof VIEWS>("caused");
  const [channel, setChannel] = useState("");
  const [segment, setSegment] = useState("");
  const step = res.steps.find((s) => s.step === stepKey) as Step;
  const channels = useMemo(() => [...new Set(step.accounts.flatMap((a) => [...a.channels_engaged, ...a.channels_reached_only]))].sort(), [step]);
  const segments = useMemo(() => [...new Set(step.accounts.map((a) => a.segment))].sort(), [step]);
  const rows = step.accounts.filter(
    (a) => (!segment || a.segment === segment) && (!channel || a.channels_engaged.includes(channel) || a.channels_reached_only.includes(channel)),
  );
  const cell = (d: string, c: string) => rows.filter((a) => a.depth === d && a.coverage === c);
  const ids = (xs: StepAccount[]) => xs.map((a) => a.account_id);

  return (
    <section>
      <div className="controls">
        <select value={stepKey} onChange={(e) => setStepKey(e.target.value)}>
          {res.steps.map((s) => <option key={s.step} value={s.step}>{s.label}</option>)}
        </select>
        <select value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {channels.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={segment} onChange={(e) => setSegment(e.target.value)}>
          <option value="">All segments</option>
          {segments.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <p className="help">
        Each cell: advance rate (accounts). Touches count from the day an account reached the stage, for{" "}
        {step.window_days ? `${step.window_days} days (${step.window_source})` : step.window_source}, and only before it advanced.
      </p>
      <table className="grid">
        <thead>
          <tr><th>Reach ↓ / Committee coverage →</th>{COVERAGE.map((c) => <th key={c}>{c}</th>)}<th>All</th></tr>
        </thead>
        <tbody>
          {DEPTHS.map((d) => {
            const all = rows.filter((a) => a.depth === d);
            return (
              <tr key={d}>
                <td>{d}</td>
                {COVERAGE.map((c) => {
                  const xs = cell(d, c);
                  const adv = xs.filter((a) => a.advanced).length;
                  return (
                    <td key={c}>
                      {xs.length ? <button className="num" onClick={() => show(`${step.label}: ${d}, ${c}`, ids(xs))}>{pct(adv / xs.length)} ({xs.length})</button> : "–"}
                    </td>
                  );
                })}
                <td>{all.length ? <button className="num" onClick={() => show(`${step.label}: ${d}`, ids(all))}>{pct(all.filter((a) => a.advanced).length / all.length)} ({all.length})</button> : "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="toggle">
        {(Object.keys(VIEWS) as (keyof typeof VIEWS)[]).map((k) => (
          <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)} title={TERMS[k]}>{VIEWS[k]}</button>
        ))}
      </div>
      <p className="help">{TERMS[view]}</p>

      {view === "caused" && (
        <>
          {step.incremental.program && (
            <p className="note">
              Program vs holdout (tested): {statusText(step.incremental.program)}, {step.incremental.program.n_exposed} program vs {step.incremental.program.n_control} holdout accounts.
            </p>
          )}
          <table>
            <thead><tr><th>Channel or role</th><th>Exposure</th><th>Result (estimated)</th><th>Advance rate with / without</th><th>Extra advances</th><th>Pipeline $</th><th>Cost per extra advance</th></tr></thead>
            <tbody>
              {[...step.incremental.channels, ...step.incremental.roles]
                .sort((a, b) => Number(b.status === "lift") - Number(a.status === "lift") || a.p_adjusted - b.p_adjusted)
                .map((t) => (
                  <tr key={(t.channel || t.role) + t.exposure} className={t.status === "lift" ? "win" : ""}>
                    <td>{t.channel || `${t.role} (role)`}</td>
                    <td>{t.exposure}</td>
                    <td>{statusText(t)}</td>
                    <td>{pct(t.rate_exposed)} / {pct(t.rate_control)}</td>
                    <td>{t.extra_advances ? t.extra_advances.toFixed(1) : "–"}</td>
                    <td>{t.value ? money(t.value) : "–"}</td>
                    <td>{t.cost_per_extra_advance ? money(t.cost_per_extra_advance) : t.status === "lift" ? "no cost entered" : "–"}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          {step.suggested_key_roles.length > 0 && <p className="note">Suggested key roles for this step, from your history: {step.suggested_key_roles.join(", ")}.</p>}
        </>
      )}
      {view === "touched" && (
        <table>
          <thead><tr><th>Channel</th><th>Credited advances</th><th>Pipeline $</th></tr></thead>
          <tbody>
            {step.influenced.channels.map((c) => (
              <tr key={c.channel}><td>{c.channel}</td><td>{c.credited_advances.toFixed(1)}</td><td>{money(c.pipeline)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {view === "started" && (
        <table>
          <thead><tr><th>Original source</th><th>Accounts</th><th>Opportunities</th><th>Pipeline $</th><th>Won $</th></tr></thead>
          <tbody>
            {res.sourced_by_channel.map((c) => (
              <tr key={c.channel}><td>{c.channel}</td><td>{c.accounts}</td><td>{c.opportunities}</td><td>{money(c.pipeline)}</td><td>{money(c.won)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Accounts({ res, pick, clear }: { res: Results; pick: Pick; clear: () => void }) {
  const [q, setQ] = useState("");
  const [gapsOnly, setGapsOnly] = useState(false);
  const gaps = useMemo(() => {
    const m: Record<string, string[]> = {};
    res.gaps.forEach((g) => (m[g.account_id] ||= []).push(g.missing_role));
    return m;
  }, [res]);
  const set = pick ? new Set(pick.ids) : null;
  const rows = res.accounts.filter(
    (a) => (!set || set.has(a.account_id)) && (!gapsOnly || gaps[a.account_id]) && a.name.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <section>
      <div className="controls">
        <input placeholder="Search accounts" value={q} onChange={(e) => setQ(e.target.value)} />
        <label><input type="checkbox" checked={gapsOnly} onChange={(e) => setGapsOnly(e.target.checked)} /> Missing key roles only</label>
        {pick && <button onClick={clear}>Showing: {pick.title} ✕</button>}
      </div>
      <p className="help">{rows.length} accounts. Missing key roles are the list the Activations tab will work from.</p>
      <table>
        <thead><tr><th>Account</th><th>Segment</th><th>Stage</th><th>Original source</th><th>Pipeline $</th><th>Missing key roles</th></tr></thead>
        <tbody>
          {rows.slice(0, 500).map((a) => (
            <tr key={a.account_id}>
              <td>{a.name}{a.holdout ? <span className="tag">holdout</span> : null}</td>
              <td>{a.segment}</td>
              <td>{a.stage}</td>
              <td>{a.original_source}</td>
              <td>{a.pipeline ? money(a.pipeline) : "–"}</td>
              <td>{(gaps[a.account_id] || []).join(", ") || "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 500 && <p className="help">Showing the first 500. Search to narrow.</p>}
    </section>
  );
}
