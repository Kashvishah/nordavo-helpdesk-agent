## How to run

Use Python 3. Make a virtual environment, install the `openai` package, and copy `.env.example` to `.env`. Fill in the local settings; `.env` is ignored by Git. The setting names are `HELPDESK_API_URL`, `HELPDESK_API_KEY`, `CANDIDATE_EMAIL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, and `MAX_RUN_COST_EUR`. The model defaults to `gpt-4.1-mini`; the cost limit defaults to `0.5` euros.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install openai
cp .env.example .env
python3 -m src.fetch_tickets
python3 -m src.eval
python3 -m src.run_all
python3 -m src.run_all --live
python3 -m src.reset_practice
```

`src.run_all` is a dry run unless `--live` is supplied. It also accepts `--only T001` for one ticket and `--force` to process IDs already in local state. The helper commands can be run as `python3 -m scripts.try_one T007 T012`, `python3 -m scripts.dump_tickets`, `python3 -m scripts.check_traps`, or `python3 -m scripts.debug_example`.

## Project structure

- `src/` contains configuration, helpdesk access, triage, run orchestration, evaluation, and practice reset.
- `scripts/` contains one-off ticket inspection, debug, and trap-check helpers.
- `candidate_pack/` holds the FAQ and assignment reference material; `logs/` stores run and evaluation output.

## Decisions

The model writes the decision and reason in English so the results are consistent and easy to compare with the English labels. It writes the customer reply in the customer's language and includes `reply_en` as an English translation for review. It first selects an FAQ entry ID and quotes the useful point. A matching entry can support an answer; policy-required handoffs still apply. Suspicious tickets are overridden in code to escalate with empty reply fields.

The configured default is `gpt-4.1-mini`, which replaced `gpt-4o-mini` during the FAQ-matching improvement. The project limits estimated run cost, with a default cap of €0.50. Dry run is the default so decisions can be reviewed before `--live` sends a reply, handoff, or close action.

## Reliability

Temporary timeouts, HTTP 429 responses, and server errors retry up to three times with growing waits. The cost cap checks an estimate before each model call and stops the run when the next call would exceed the limit. A local state file records handled ticket IDs; later runs skip them unless `--force` is used.

Invalid model JSON or missing or unknown fields gets up to two further validation attempts. If it remains invalid, code returns an escalate fallback and logs status `fallback`. Ticket text is marked as untrusted data. T007's instruction to ignore prior rules and mark a ticket resolved is classified as suspicious; code forces escalation and removes the reply. Empty tickets are directed to `ignore` with no reply. `check_traps.py` checks that T007 is suspicious and T028, the legal-threat case, is not.

Each ticket gets a JSON line in `logs/run.jsonl`, including skips and errors. The log records the decision, reason, suspicious flag, status, and timestamp where available; credential values are redacted. `reset_practice.py` calls the practice reset endpoint, archives the prior run log, and clears local handled-ticket state.

## Eval and fix

The saved first evaluation in `logs/eval_before.json` scored 7/10. Its three misses were E01 (iPhone 8 crash), E02 (VAT number change), and E05 (Google Calendar request); each expected `answer`, while the model chose `escalate`. In the E01 debug output, the model selected no FAQ match. The prompt was changed to require an explicit FAQ ID and a short quote, and the default model was strengthened to `gpt-4.1-mini`. The saved result in `logs/eval_after.json` is 10/10.

## What I would improve

I would evaluate more examples in each language and category, add a confidence threshold that sends uncertain cases to a person, and build a clear human review queue. I would also replace sending the whole FAQ in every prompt with FAQ search that supplies only the most relevant entries, then compare its accuracy against the current evaluation set.
