import { useState } from "react";
import type { Results } from "../types";
import Accounts, { type Pick } from "./Accounts";
import Funnel from "./Funnel";
import Grid from "./Grid";
import Headline from "./Headline";
import { ui, type Show } from "./ui";

export const VIEWS = { funnel: "Funnel", grid: "Step grid", accounts: "Accounts" } as const;
export type View = keyof typeof VIEWS;

/**
 * The whole Account Hub screen for one results.json: a one-line summary, the headline numbers,
 * then Funnel / Step grid / Accounts. Every number opens the accounts behind it. Takes the result
 * as props and loads nothing itself, so any app can render it (this repo's dashboard reads
 * results.json; a hosted app can pass the same object from its own API).
 */
export default function AccountHub({ res, initialView = "funnel" }: { res: Results; initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
  const [pick, setPick] = useState<Pick>(null);
  const show: Show = (title, ids, step) => {
    setPick({ title, ids, step });
    setView("accounts");
  };
  return (
    <div>
      <p className={`text-sm ${ui.muted}`}>Data through {res.as_of}. Touches since {res.touch_history_start}.</p>
      <Headline res={res} show={show} />
      <nav className="mb-2 mt-4 flex flex-wrap gap-1.5">
        {(Object.keys(VIEWS) as View[]).map((v) => (
          <button key={v} type="button" className={ui.pill(view === v)} onClick={() => setView(v)}>{VIEWS[v]}</button>
        ))}
      </nav>
      {view === "funnel" && <Funnel res={res} show={show} />}
      {view === "grid" && <Grid res={res} show={show} />}
      {view === "accounts" && <Accounts res={res} pick={pick} clear={() => setPick(null)} />}
    </div>
  );
}
