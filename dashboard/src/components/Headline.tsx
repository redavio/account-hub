import type { Results } from "../types";
import N from "./N";
import { CREDIT, money, pct, ui, type Show } from "./ui";

/** Pipeline, the three marketing credits, and won. */
export default function Headline({ res, show }: { res: Results; show: Show }) {
  const h = res.headline;
  const c = h.caused_by_marketing;
  const cards: [string, string, string, string[], string][] = [
    ["Pipeline", money(h.pipeline_total), `${h.opportunities} opportunities`, h.opportunity_ids, "All opportunities"],
    [CREDIT.started, money(h.started_by_marketing.pipeline), "sourced", h.started_by_marketing.account_ids, "Started by marketing"],
    [CREDIT.touched, money(h.touched_by_marketing.pipeline), "influenced", h.touched_by_marketing.account_ids, "Touched by marketing"],
    [CREDIT.caused, c.status === "lift" ? money(c.pipeline) : c.status, `incremental, ${c.label}`, c.account_ids, "Caused by marketing"],
    ["Won", money(h.won_total), `win rate ${pct(h.win_rate)}`, h.won_ids, "Closed won"],
  ];
  return (
    <section className="my-5 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
      {cards.map(([label, value, sub, ids, title]) => (
        <div key={label} className="rounded-xl border border-zinc-200 p-3.5 dark:border-zinc-700">
          <div className={`text-xs ${ui.muted}`}>{label}</div>
          <div className="my-1 text-2xl font-semibold"><N ids={ids} title={title} show={show}>{value}</N></div>
          <div className={`text-xs ${ui.muted}`}>{sub}</div>
        </div>
      ))}
    </section>
  );
}
