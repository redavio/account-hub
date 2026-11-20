import type { StepAccount, Test } from "../types";

// Display helpers, labels and shared Tailwind classes for every view.
export const money = (n: number) =>
  n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`;
export const pct = (n: number | null | undefined) => (n === null || n === undefined ? "–" : `${Math.round(n * 100)}%`);
export const DEPTHS = ["Not reached", "Reached", "Engaged"] as const;
export const COVERAGE = ["None", "1 role", "2+ roles"] as const;
export const CREDIT = {
  started: "Started by marketing",
  touched: "Touched by marketing",
  caused: "Caused by marketing",
} as const;
export type Credit = keyof typeof CREDIT;
export const TERMS: Record<Credit, string> = {
  started: "Sourced: accounts whose original source was a marketing channel.",
  touched: "Influenced: each advance credited equally to the engaged marketing touches in its window. Credit, not proof.",
  caused: "Incremental: extra advances, testing each channel and role with the others, segment and cohort held fixed.",
};

export const statusText = (t: Test) =>
  t.status === "lift" ? `+${Math.round(t.lift * 100)} pts` :
  t.status === "negative" ? `${Math.round(t.lift * 100)} pts` :
  t.status === "not enough data yet" ? `not enough data yet (~${t.more_accounts_needed.toLocaleString()} more accounts)` : "no lift found";

/** Reach depth for one channel, when the channel filter is on. */
export const depthFor = (a: StepAccount, channel: string) =>
  !channel ? a.depth : a.channels_engaged.includes(channel) ? "Engaged" : a.channels_reached_only.includes(channel) ? "Reached" : "Not reached";

/** Opens the Accounts view on a list of accounts (and the step they were picked from, if any). */
export type Show = (title: string, ids: string[], step?: string) => void;

export const ui = {
  muted: "text-zinc-500 dark:text-zinc-400",
  help: "my-3 text-sm text-zinc-500 dark:text-zinc-400",
  note: "my-3 rounded-lg bg-brand/10 px-3 py-2.5 text-sm",
  table: "mb-4 mt-2 w-full border-collapse text-sm",
  th: "border-b border-zinc-200 px-2 py-2 text-left align-bottom font-medium text-zinc-500 dark:border-zinc-700 dark:text-zinc-400",
  td: "whitespace-nowrap border-b border-zinc-200 px-2 py-2 dark:border-zinc-700",
  field: "rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900",
  tag: "ml-1.5 whitespace-nowrap rounded-full border border-zinc-200 px-1.5 py-px text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400",
  pill: (on: boolean) =>
    `rounded-full border px-3.5 py-1.5 text-sm ${
      on ? "border-brand bg-brand text-white" : "border-zinc-200 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
    }`,
};
