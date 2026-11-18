# Account Hub

Account Hub shows which touches and which buying-committee coverage move your target accounts to the next funnel stage, and what that is worth in pipeline. It reads HubSpot (or a Google Sheet for any other CRM), runs the math in plain Python, and writes one results file. That file feeds a React dashboard, a Claude artifact and a Google Sheet, so all three always show the same numbers.

This is the **Performance** tab. An **Activations** tab (emails, LinkedIn audiences) comes next and works from the gaps list this one writes.

## What it answers

1. Where are my target accounts in the funnel, and what is the pipeline worth?
2. Was each account reached, and was its buying committee covered?
3. Did that reach and coverage move accounts to the next stage, and what is that worth?

Funnel: Non-hand-raiser lead → Hand-raiser → SQL → Opportunity → Closed won. A non-hand-raiser lead can skip straight to SQL; skipping a stage counts as advancing.

## Three views of marketing's pipeline

| On screen | Industry term | What it means |
| --- | --- | --- |
| Started by marketing | Sourced | The account's original source was a marketing channel. The smallest number and the strongest claim. |
| Touched by marketing | Influenced | Every engaged marketing touch before an advance gets an equal share of the credit. Credit, not proof. |
| Caused by marketing | Incremental | The extra advances marketing caused. With a holdout list, the program is tested against it. Each channel and role is tested while holding the others fixed (logistic regression), labeled "estimated". |

Value is pipeline $: a stage is worth the share of its accounts that become an Opportunity, times the average Opportunity. Won $ and win rate are shown alongside.

The math, in short:
- **Window.** Touches count from the day an account reaches a stage, for the number of days within which 80% of past advancing accounts advanced, and only before it advances. Too little history: the sales cycle in settings; none: the whole time at the stage.
- **Cohorts.** An account counts toward a step only once its window has passed, so recent accounts aren't read as failures.
- **No fixed minimum sample.** A sample-size check based on your own advance rate decides between "no lift found" and "not enough data yet, about N more accounts needed".
- **One correction** (Holm) covers every test in the report, so a false "lift" anywhere stays unlikely.

## Run it

### 1. In Claude (lowest setup)

Turn on HubSpot's Claude connector and the Redavio connector (`https://www.redavio.com/mcp`), then say "run Account Hub". Claude pulls the data, the Redavio server runs this engine, and Claude builds the dashboard as an artifact. Needs a paid Claude plan; a HubSpot Super Admin must allow the connector to read engagements. Best for hundreds of accounts. For more, use the repo.

### 2. From this repo, with HubSpot

```bash
python3 -m accounthub connect                     # sign in to HubSpot and click Allow
python3 -m accounthub run --hubspot --csv results/
cd dashboard && npm install && cp ../results.json public/ && npm run dev
```

`connect` needs no API key: HubSpot sends a one-time code to redavio.com, which swaps it for a token and hands it back to your computer (the swap needs the app's secret, which can't live in an open repo). Redavio doesn't store the token. If your IT blocks installing apps, a HubSpot admin can create a private app with read access to companies, contacts, deals, emails and marketing events, and you set `HUBSPOT_TOKEN` instead.

To share the dashboard with your team, deploy the `dashboard` folder to Vercel (or any static host) with your `results.json` in `public/`. Anyone can also open a results file with the "Open results file" button.

### 3. From the Google Sheet template (any CRM)

Make a copy of the [Account Hub template](https://docs.google.com/spreadsheets/d/1UnjCWzuaxbb-K9xZ0u9t4n58TpRjp1krkYgR9sfasUY/copy), fill the four tabs, download each as CSV into one folder, then:

```bash
python3 -m accounthub run --folder my-data/ --csv results/
```

`--csv` writes the results tabs (summary, funnel, step grid, caused / touched / started by marketing, gaps, accounts) to import back into the Sheet.

### Extra touches

HubSpot's API doesn't expose web visits, ad clicks or marketing email sends per contact. Add them, or anything else HubSpot doesn't hold (LinkedIn ad clicks, direct mail), from the template's touches tab: `--extra touches.csv` with columns `date, contact_email, company_domain, channel, kind (engaged|reached), detail`. Rows match an account by email, then by domain.

## Data shape

| Table | Columns |
| --- | --- |
| accounts | account_id, name, domain, segment, target, holdout, original_source, nhr_lead_date, hand_raiser_date, sql_date |
| contacts | contact_id, account_id, name, email, role |
| deals | deal_id, account_id, amount, created_date, status (open, won, lost), close_date |
| touches | touch_id, account_id, contact_id, date, channel, kind (engaged or reached), detail |

Opportunity date is the first deal's created date; Closed won is the first won deal's close date.

## Settings

Copy `settings.example.json` and pass `--settings`. You can set key roles per step (plus extra roles for Enterprise), the sales cycle fallback, which channels don't count as marketing, cost per channel (for cost per extra advance), and the HubSpot property names for target list, holdout, segment, role and stage dates.

## Demo data and tests

`seed/generate.py` makes about 1,000 fictional companies with planted effects (paid social ad clicks, event attendance and an engaged Finance contact truly help; web visits and unopened emails don't). The tests check the engine finds the real ones and invents none. `seed/hubspot_seed.py` writes the same data into a HubSpot **test** account and refuses to run on any other.

```bash
python3 -m unittest discover tests
```

MIT licensed. Part of the [Redavio Library](https://www.redavio.com).
