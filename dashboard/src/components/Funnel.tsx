import type { Results } from "../types";
import N from "./N";
import { money, pct, TERMS, ui, type Show } from "./ui";

/** Every funnel stage with its accounts, advance rate and pipeline. */
export default function Funnel({ res, show }: { res: Results; show: Show }) {
  const heads: [string, string?][] = [
    ["Stage"], ["Accounts"], ["Advance rate (accounts judged)", "Of the accounts whose window has passed"], ["Value per account"], ["Pipeline $"],
    ["Started by marketing", TERMS.started], ["Touched by marketing", TERMS.touched], ["Caused by marketing", TERMS.caused], ["Won $"],
  ];
  return (
    <section className="overflow-x-auto" data-shot="1">
      <p className={ui.help}>
        Value per account is pipeline $: the share at the stage that become an Opportunity, times the average Opportunity. "Caused by marketing" here is estimated per channel; the headline card uses the holdout test when you have one.
      </p>
      <table className={ui.table}>
        <thead>
          <tr>{heads.map(([h, tip]) => <th key={h} className={ui.th} title={tip}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {res.funnel.map((f) => (
            <tr key={f.stage}>
              <td className={ui.td}>{f.label}</td>
              <td className={ui.td}><N ids={f.account_ids} title={f.label} show={show}>{f.accounts}</N></td>
              <td className={ui.td}>
                {f.advance_rate === null ? "–" : (
                  <N ids={f.judged_ids} title={`${f.label}: accounts judged`} show={show} step={res.steps.find((s) => s.from === f.stage)?.step}>
                    {pct(f.advance_rate)} ({f.judged})
                  </N>
                )}
              </td>
              <td className={ui.td}><N ids={f.account_ids} title={f.label} show={show}>{money(f.value)}{f.stage === "closed_won" ? " avg won" : ""}</N></td>
              <td className={ui.td}><N ids={f.pipeline_ids} title={`${f.label}: with pipeline`} show={show}>{money(f.pipeline)}</N></td>
              <td className={ui.td}><N ids={f.started_ids} title={`${f.label}: started by marketing`} show={show}>{money(f.started_by_marketing)}</N></td>
              <td className={ui.td}><N ids={f.touched_ids} title={`${f.label}: touched by marketing`} show={show}>{money(f.touched_by_marketing)}</N></td>
              <td className={ui.td}>
                {f.caused_by_marketing ? (
                  <N ids={f.caused_ids} title={`${f.label}: exposed to channels with a lift`} show={show}>{money(f.caused_by_marketing)} (estimated)</N>
                ) : "–"}
              </td>
              <td className={ui.td}><N ids={f.won_ids} title={`${f.label}: won`} show={show}>{money(f.won)}</N></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
