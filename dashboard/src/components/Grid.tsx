import { useMemo, useState } from "react";
import type { Results, Step, StepAccount } from "../types";
import N from "./N";
import { COVERAGE, CREDIT, DEPTHS, depthFor, money, pct, statusText, TERMS, ui, type Credit, type Show } from "./ui";

/** How reach and buying-group coverage change each step's advance rate, and what marketing gets credit for. */
export default function Grid({ res, show }: { res: Results; show: Show }) {
  const [stepKey, setStepKey] = useState(res.steps[0]?.step);
  const [view, setView] = useState<Credit>("caused");
  const [channel, setChannel] = useState("");
  const [segment, setSegment] = useState("");
  const step = res.steps.find((s) => s.step === stepKey) as Step;
  const channels = useMemo(() => [...new Set(step.accounts.flatMap((a) => [...a.channels_engaged, ...a.channels_reached_only]))].sort(), [step]);
  const segments = useMemo(() => [...new Set(step.accounts.map((a) => a.segment))].sort(), [step]);
  const rows = step.accounts.filter((a) => !segment || a.segment === segment);
  const ids = (xs: StepAccount[]) => xs.map((a) => a.account_id);
  const rate = (xs: StepAccount[]) => (xs.length ? `${pct(xs.filter((a) => a.advanced).length / xs.length)} (${xs.length})` : "–");
  const sourced = res.sourced_by_channel;
  const head = (hs: string[]) => <thead><tr>{hs.map((h) => <th key={h} className={ui.th}>{h}</th>)}</tr></thead>;

  return (
    <section className="overflow-x-auto" data-shot="2">
      <div className="my-3 flex flex-wrap items-center gap-2 text-sm">
        <select className={ui.field} value={stepKey} onChange={(e) => setStepKey(e.target.value)} aria-label="Step">
          {res.steps.map((s) => <option key={s.step} value={s.step}>{s.label}</option>)}
        </select>
        <select className={ui.field} value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="Channel">
          <option value="">All channels</option>
          {channels.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select className={ui.field} value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Segment">
          <option value="">All segments</option>
          {segments.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <p className={ui.help}>
        Advance rate (accounts). Reach{channel ? ` by ${channel}` : ""} counts from the day an account reached the stage, for{" "}
        {step.window_days ? `${step.window_days} days (${step.window_source})` : step.window_source}, and only before it advanced.
      </p>
      <table className={ui.table}>
        {head(["Reach ↓ / Committee coverage →", ...COVERAGE, "All"])}
        <tbody>
          {DEPTHS.map((d) => {
            const all = rows.filter((a) => depthFor(a, channel) === d);
            return (
              <tr key={d}>
                <td className={`${ui.td} font-medium`}>{d}</td>
                {COVERAGE.map((c) => {
                  const xs = all.filter((a) => a.coverage === c);
                  return <td key={c} className={ui.td}><N ids={ids(xs)} title={`${step.label}: ${d}, ${c}`} show={show} step={step.step}>{rate(xs)}</N></td>;
                })}
                <td className={ui.td}><N ids={ids(all)} title={`${step.label}: ${d}`} show={show} step={step.step}>{rate(all)}</N></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mb-2 mt-4 flex flex-wrap gap-1.5">
        {(Object.keys(CREDIT) as Credit[]).map((k) => (
          <button key={k} type="button" className={ui.pill(view === k)} onClick={() => setView(k)} title={TERMS[k]}>{CREDIT[k]}</button>
        ))}
      </div>
      <p className={ui.help}>{TERMS[view]}</p>

      {view === "caused" && (
        <>
          {step.incremental.program && (
            <p className={ui.note}>
              Program vs holdout (tested): {statusText(step.incremental.program)}, {step.incremental.program.n_exposed} program and {step.incremental.program.n_control} holdout accounts.
            </p>
          )}
          <table className={ui.table}>
            {head(["Channel or role", "Exposure", "Result (estimated)", "Advance rate with / without", "Extra advances", "Pipeline $", "Cost per extra advance"])}
            <tbody>
              {[...step.incremental.channels, ...step.incremental.roles]
                .sort((a, b) => Number(b.status === "lift") - Number(a.status === "lift") || a.p_adjusted - b.p_adjusted)
                .map((t) => {
                  const name = t.channel || `${t.role} (role)`;
                  const td = `${ui.td} ${t.status === "lift" ? "bg-brand/10" : ""}`;
                  const title = `${step.label}: ${name}, ${t.exposure}`;
                  return (
                    <tr key={name + t.exposure}>
                      <td className={td}><N ids={t.exposed_ids} title={title} show={show} step={step.step}>{name}</N></td>
                      <td className={td}>{t.exposure}</td>
                      <td className={td}>{statusText(t)}</td>
                      <td className={td}>{pct(t.rate_exposed)} / {pct(t.rate_control)}</td>
                      <td className={td}>{t.extra_advances ? <N ids={t.exposed_ids} title={title} show={show} step={step.step}>{t.extra_advances.toFixed(1)}</N> : "–"}</td>
                      <td className={td}>{t.value ? <N ids={t.exposed_ids} title={title} show={show} step={step.step}>{money(t.value)}</N> : "–"}</td>
                      <td className={td}>{t.cost_per_extra_advance ? money(t.cost_per_extra_advance) : t.status === "lift" && t.channel ? "no cost entered" : "–"}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
          {step.suggested_key_roles.length > 0 && (
            <p className={ui.note}>Suggested key roles for this step, from your history: {step.suggested_key_roles.join(", ")}.</p>
          )}
        </>
      )}
      {view === "touched" && (
        <table className={ui.table}>
          {head(["Channel or role", "Credited advances", "Pipeline $", "Won $"])}
          <tbody>
            {[...step.influenced.channels.map((c) => ({ ...c, name: c.channel })), ...step.influenced.roles.map((r) => ({ ...r, name: `${r.role} (role)` }))].map((c) => (
              <tr key={c.name}>
                <td className={ui.td}><N ids={c.account_ids} title={`${step.label}: touched by ${c.name}`} show={show} step={step.step}>{c.name}</N></td>
                {[c.credited_advances.toFixed(1), money(c.pipeline), money(c.won)].map((v, i) => (
                  <td key={i} className={ui.td}><N ids={c.account_ids} title={`${step.label}: touched by ${c.name}`} show={show} step={step.step}>{v}</N></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {view === "started" && (
        <table className={ui.table}>
          {head(["Original source", "Accounts", "Opportunities", "Pipeline $", "Won $"])}
          <tbody>
            {sourced.map((c) => (
              <tr key={c.channel}>
                <td className={ui.td}>{c.channel}</td>
                <td className={ui.td}><N ids={c.account_ids} title={`Started by ${c.channel}`} show={show}>{c.accounts}</N></td>
                <td className={ui.td}><N ids={c.opportunity_ids || []} title={`Started by ${c.channel}: opportunities`} show={show}>{c.opportunities}</N></td>
                <td className={ui.td}><N ids={c.opportunity_ids || []} title={`Started by ${c.channel}: opportunities`} show={show}>{money(c.pipeline)}</N></td>
                <td className={ui.td}>{money(c.won)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
