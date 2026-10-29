# Question-answering agent

A small agent that answers questions about the F1 data by writing SQL against the gold tables, and an evaluation that
says how often it is right. The agent is the least interesting part. The evaluation is the point: 44 questions with
reference answers that the model never sees, 10 of them about things the data cannot answer.

## How it works

1. **Route.** The model sees one line per table (from the dbt descriptions) and names the tables a question needs, or
   none when the data cannot answer it.
2. **Write.** It sees the full column descriptions of only those tables and writes one SELECT, or says it cannot answer.
3. **Repair.** If the query is rejected or fails, the error goes back to the model, up to twice.

The agent can only run read-only SELECTs. A gate rejects anything else (`sqlguard.py`), and the database is opened
read-only with file access switched off, so a query that slipped past the gate still could not write or read files.
The per-sample telemetry tables are hidden: they are views over the whole lake and far too big to query here.
The model runs locally through Ollama, so nothing leaves the machine and nothing costs money.

## How it is scored

- **Answerable questions (34).** The agent's SQL is run and its result table is compared with a reference query's result
  (execution accuracy). Column names and extra columns do not matter, row order matters only when the question asks for
  it, decimals match within a stated tolerance. The reference answers are computed from hand-written SQL at run time,
  so they stay right when the data is refreshed.
- **Unanswerable questions (10).** Future events, things the data never records (tyre pressures, salaries, engine
  modes), and near misses (the time in the pit lane is recorded, the time the car stood still is not). The agent is
  right only if it declines.
- **Also reported:** whether the right tables were chosen, how often the first query worked, how often it declined a
  question it could have answered, and the failures, one by one.

`questions.py` is the whole question set. One race (the 2018 Italian GP) has results but no laps; a question about its
winner checks that the agent does not refuse just because laps are missing.

## Run it

```
python -m qa_agent.check_reference               # run every reference query and look at the answers first
ollama pull qwen2.5-coder:7b
python -m qa_agent.run_eval --model qwen2.5-coder:7b
python -m qa_agent.report                        # writes qa_agent/results/RESULTS.md
```

Other options: `--only id1,id2`, `--limit 5`, `--num-ctx 16384`. Any model Ollama serves can be named with `--model`.
`pytest tests/test_qa_agent.py` tests the gate, the scoring, the question set and the agent loop with a scripted model.

## Prompt changes after the first run

The first run (qwen2.5-coder 7b and 14b, results kept in `qa_agent/results/baseline/`) showed that many failures were
the harness's fault, not the models': they declined answerable questions because they believed 2025 was in the future
(the prompt never said what day it was or what years the data covers), gave up when the table they had chosen had no
`event` column, and copied a placeholder word from the prompt as their reason for declining. I fixed those three
things, made `dim_session` (the table that names every session) always visible to the model that writes the SQL, and
changed the scoring in two ways: identical repeated rows count once, and an unanswerable question counts as handled if
the query finds nothing (empty or all NULL). The questions and reference answers did not change. Both runs are in the
results so the effect of the change is visible. The failures that remain, such as counting qualifying and practice
sessions as races, are the models'.

## Limits

- 44 questions is a small sample: one question is 2.3 points, so differences of a few points between models are noise.
- I wrote both the questions and the reference queries, and the wording of a question can favour one reading. The
  reference answers were checked by eye against the data before any model was scored.
- Scoring compares result tables, so a correct answer given with different columns passes, and a query that happens to
  return the right rows for a wrong reason would also pass.
- Results depend on the model version, the quantisation Ollama ships, and the seed; the run records the model name and
  date, not the exact weights.
