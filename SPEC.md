# Account Hub: how it works

This is the Performance tab. Activations (emails, audiences) come later and work from the gaps list it writes.

## The questions it answers

1. Where are my target accounts in the funnel, and what is the pipeline worth?
2. Was each account reached, and was its buying committee covered?
3. Did that reach and coverage move accounts to the next stage, and what is that worth?

## Definitions

| Term | Meaning |
| --- | --- |
| Account | A company in your CRM. Only target accounts are analyzed. |
| Segment | A company field such as SMB, Mid-market, Enterprise. Comparisons are made within a segment. |
| Stages | Non-hand-raiser lead → Hand-raiser → SQL → Opportunity → Closed won. A non-hand-raiser lead can skip straight to SQL; skipping a stage counts as advancing. |
| Stage date | The first date the account reached the stage. Opportunity is the first deal's created date; Closed won is the first won deal's close date. |
| Touch | One interaction with a contact: ad click, email click or reply, web visit, form fill, meeting, event attendance. Email opens don't count (mostly mail scanners). |
| Reach depth | Per account, per step: Not reached (no touch), Reached (sent or shown, no action), Engaged (a contact clicked, replied, visited, met or attended). |
| Buying committee roles | Your list (for example Exec, Champion, Finance, IT, Security, Procurement). Each contact has one role. |
| Key roles per step | The roles that matter at each step. Defaults: Champion through SQL; Champion and Exec at SQL → Opportunity; Exec and Finance (plus Security for Enterprise) at Opportunity → Closed won. The tool suggests changes from your own history. |
| Committee coverage | How many key roles engaged: None, 1 role, 2+ roles. |
| Window | Touches count from the stage date, for the days within which 80% of past advancing accounts advanced, and only before the account advanced. An account advances only if it does so within the window. Fallbacks: your sales cycle, then the whole time at the stage. |
| Cohort | The month an account entered a stage. An account counts toward a step only once its window has passed, and comparisons hold the cohort fixed. |
| Value per stage | Pipeline $: the share of accounts at the stage that become an Opportunity, times the average Opportunity. Won $ and win rate are shown alongside. |

## Three views of marketing's pipeline

| On screen | Industry term | Rule |
| --- | --- | --- |
| Started by marketing | Sourced | The account's original source is a marketing channel. The smallest number and the strongest claim. |
| Touched by marketing | Influenced | Each advance gives equal credit to every engaged marketing touch in its window. Credit, not proof. |
| Caused by marketing | Incremental | With a holdout list (target accounts set aside, no ABM), the program is tested against it with an exact stratified test. Each channel and role is also tested with the others, the segment and the cohort held fixed (logistic regression), labeled "estimated". |

Lift is in points. Extra advances = lift × exposed accounts; value = extra advances × value of the stage reached; cost per extra advance = channel cost ÷ extra advances.

One Holm correction covers every test in the report. There is no fixed minimum sample: a sample-size check on your own advance rate decides between "no lift found" and "not enough data yet, about N more accounts needed".

## Screens

1. **Funnel**: one row per stage with accounts, advance rate, value, pipeline $ (started, touched and caused by marketing) and won $.
2. **Step grid**: reach depth by committee coverage for one step, each cell an advance rate and account count, with the three views, and filters by channel and segment.
3. **Accounts**: every number opens the accounts behind it, with their reach, roles engaged and missing key roles.

## Data

Four tables (see `template/`): accounts, contacts, deals, touches. HubSpot is read into the same shape; touches HubSpot doesn't hold (web visits, ad clicks) can be added from a touches file, matched by email or domain.

## Gaps

Every target account still in play (not holdout, not won, not lost) gets the key roles for its next step that haven't engaged since it reached its current stage. Accounts past twice the usual time at a stage are flagged as stalled.

## Not in this version

Activations, retention (Closed won → Renewed), Salesforce connector, AI-written commentary.
