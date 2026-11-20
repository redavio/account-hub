import { useMemo, useState } from "react";
import type { Results } from "../types";
import { money, ui } from "./ui";

/** What the Accounts view shows: a list of accounts, and the step they were picked from, if any. */
export type Pick = { title: string; ids: string[]; step?: string } | null;

/** The accounts behind any number, with their buying group. */
export default function Accounts({ res, pick, clear }: { res: Results; pick: Pick; clear: () => void }) {
  const [q, setQ] = useState("");
  const [gapsOnly, setGapsOnly] = useState(false);
  const gaps = useMemo(() => {
    const m: Record<string, string[]> = {};
    res.gaps.forEach((g) => (m[g.account_id] ||= []).push(g.missing_role));
    return m;
  }, [res]);
  const stalled = useMemo(() => new Set(res.gaps.filter((g) => g.stalled).map((g) => g.account_id)), [res]);
  const step = pick?.step ? res.steps.find((s) => s.step === pick.step) : undefined;
  const stepRows = useMemo(() => Object.fromEntries((step?.accounts || []).map((a) => [a.account_id, a])), [step]);
  const set = pick ? new Set(pick.ids) : null;
  const rows = res.accounts.filter(
    (a) => (!set || set.has(a.account_id)) && (!gapsOnly || gaps[a.account_id]) && a.name.toLowerCase().includes(q.toLowerCase()),
  );
  const heads = ["Account", "Segment", "Stage now", "Original source", "Pipeline $",
    ...(step ? ["Reach", "Roles engaged", "Key roles missing", "Advanced"] : ["Key roles missing now"])];
  return (
    <section className="overflow-x-auto" data-shot="3">
      <div className="my-3 flex flex-wrap items-center gap-2 text-sm">
        <input className={ui.field} placeholder="Search accounts" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search accounts" />
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={gapsOnly} onChange={(e) => setGapsOnly(e.target.checked)} /> Missing key roles now
        </label>
        {pick && <button type="button" className={ui.pill(false)} onClick={clear}>Showing: {pick.title} ✕</button>}
      </div>
      <p className={ui.help}>
        {rows.length} accounts.{" "}
        {step ? `Reach and roles are for ${step.label}.` : "Missing key roles are for each account's next step: the list the Activations tab will work from."}
      </p>
      <table className={ui.table}>
        <thead>
          <tr>{heads.map((h) => <th key={h} className={ui.th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 500).map((a) => {
            const s = stepRows[a.account_id];
            return (
              <tr key={a.account_id}>
                <td className={ui.td}>
                  {a.name}
                  {a.holdout ? <span className={ui.tag}>holdout</span> : null}
                  {stalled.has(a.account_id) ? <span className={ui.tag} title="More than twice the usual time at this stage">stalled</span> : null}
                </td>
                <td className={ui.td}>{a.segment}</td>
                <td className={ui.td}>{a.stage}</td>
                <td className={ui.td}>{a.original_source}</td>
                <td className={ui.td}>{a.pipeline ? money(a.pipeline) : "–"}</td>
                {step ? (
                  <>
                    <td className={ui.td}>{s?.depth ?? "–"}</td>
                    <td className={ui.td}>{s?.roles_engaged.join(", ") || "–"}</td>
                    <td className={ui.td}>{s?.missing_roles.join(", ") || "–"}</td>
                    <td className={ui.td}>{s ? (s.advanced ? "yes" : "no") : "–"}</td>
                  </>
                ) : (
                  <td className={ui.td}>{(gaps[a.account_id] || []).join(", ") || "–"}</td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length > 500 && <p className={ui.help}>Showing the first 500. Search to narrow.</p>}
    </section>
  );
}
