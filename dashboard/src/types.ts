// Shape of results.json, written by the engine (accounthub/engine.py).

export type Status = "lift" | "negative" | "no lift found" | "not enough data yet";

export interface Test {
  channel?: string;
  role?: string;
  exposure: "engaged" | "reached only";
  lift: number;
  p_adjusted: number;
  n_exposed: number;
  n_control: number;
  rate_exposed: number;
  rate_control: number;
  status: Status;
  more_accounts_needed: number;
  extra_advances: number;
  value: number;
  cost: number | null;
  cost_per_extra_advance: number | null;
  exposed_ids: string[];
}

export interface StepAccount {
  account_id: string;
  cohort: string;
  name: string;
  segment: string;
  holdout: boolean;
  advanced: boolean;
  depth: "Not reached" | "Reached" | "Engaged";
  coverage: "None" | "1 role" | "2+ roles";
  channels_engaged: string[];
  channels_reached_only: string[];
  roles_engaged: string[];
  key_roles: string[];
  missing_roles: string[];
}

export interface Step {
  from: string;
  to: string;
  step: string;
  label: string;
  window_days: number | null;
  window_source: string;
  eligible: number;
  advanced: number;
  rate: number | null;
  influenced: {
    channels: { channel: string; credited_advances: number; pipeline: number; won: number; account_ids: string[] }[];
    roles: { role: string; credited_advances: number; pipeline: number; won: number; account_ids: string[] }[];
    influenced_advances: number;
    account_ids: string[];
  };
  incremental: {
    program: (Test & { label: string }) | null;
    channels: Test[];
    roles: Test[];
  };
  suggested_key_roles: string[];
  accounts: StepAccount[];
}

export interface Account {
  account_id: string;
  name: string;
  segment: string;
  holdout: boolean;
  original_source: string;
  stage: string;
  pipeline: number;
  won: number;
}

export interface Results {
  tool: string;
  as_of: string;
  touch_history_start: string;
  headline: {
    pipeline_total: number;
    won_total: number;
    opportunities: number;
    closed_won: number;
    win_rate: number | null;
    opportunity_ids: string[];
    won_ids: string[];
    started_by_marketing: { opportunities: number; pipeline: number; won: number; account_ids: string[] };
    touched_by_marketing: { opportunities: number; pipeline: number; won: number; account_ids: string[] };
    caused_by_marketing: { pipeline: number; label: string; status: Status; account_ids: string[] };
  };
  funnel: {
    stage: string; label: string; accounts: number; advance_rate: number | null; judged: number | null; value: number;
    pipeline: number; started_by_marketing: number; touched_by_marketing: number; caused_by_marketing: number; won: number;
    account_ids: string[]; judged_ids: string[];
  }[];
  steps: Step[];
  sourced_by_channel: { channel: string; accounts: number; opportunities: number; pipeline: number; won: number; account_ids: string[] }[];
  gaps: { account_id: string; name: string; segment: string; stage: string; step: string; missing_role: string; days_at_stage: number }[];
  accounts: Account[];
}
