---
name: account-hub
description: Account Hub (ABM performance). Shows which touches and buying-committee coverage move target accounts from lead to hand-raiser, SQL, opportunity and closed won, and what that is worth in pipeline, as started by marketing (sourced), touched by marketing (influenced) and caused by marketing (incremental). Use when someone asks how their ABM or account-based program is performing, which channels or roles move accounts, what marketing caused in pipeline, or which target accounts are missing key buying-committee roles.
license: MIT
compatibility: Python 3.9 or later, standard library only. Reads HubSpot (connect or HUBSPOT_TOKEN) or four CSVs. The dashboard needs Node 18+.
---

# Account Hub

Never do the funnel, window, lift or significance math yourself. Run the engine and report what it returns.

1. Get the data, in this order of preference:
   - HubSpot: `python3 -m accounthub run --hubspot --csv results/` (run `python3 -m accounthub connect` first if not connected).
   - Any other CRM: four CSVs in one folder (accounts, contacts, deals, touches; columns in README.md), then `python3 -m accounthub run --folder <folder> --csv results/`.
   - Touches HubSpot doesn't hold (web visits, ad clicks): add `--extra <csv>`.
   - Settings (key roles per step, costs, property names): `--settings settings.json`, from settings.example.json.
2. Read `results.json`. Lead with the headline: pipeline, then started by / touched by / caused by marketing, with their industry terms in brackets (sourced, influenced, incremental), then won and win rate.
3. For each funnel step, name the channels and roles with status "lift" (points, extra advances, pipeline $). Say "not enough data yet" with the number of accounts needed where that's the status. Never call an "estimated" result proven; only the holdout test is.
4. List the accounts missing key roles (`gaps`): that's the to-do list for activations.
5. Offer the dashboard: `cd dashboard && npm install && cp ../results.json public/ && npm run dev`.
