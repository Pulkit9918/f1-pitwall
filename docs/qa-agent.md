# Question-answering agent

[Back to the README](../README.md)

## Question-answering agent

`qa_agent/` answers questions about the data by writing SQL against the gold tables. It uses a local model through Ollama, so it costs nothing and nothing leaves the machine. The agent is small: it picks the tables a question needs, writes one read-only SELECT with the dbt column descriptions as context, and retries twice if the query fails. The evaluation is the part to read. It has 44 questions with reference answers the model never sees: 34 the data can answer, and 10 it cannot (future events, things the data never records, and near misses such as asking for the time a car stood still when only the time in the pit lane is recorded). An answer counts as correct if running the agent's SQL gives the same result table as a hand-written reference query. An unanswerable question counts as handled if the agent declines or its query finds nothing.

| Model | Correct on answerable questions | Declined the unanswerable correctly | Declined an answerable question | Seconds per question |
|---|---|---|---|---|
| qwen2.5-coder 14B | 26 of 34 (76%) | 8 of 10 | 1 | 10 |
| qwen2.5-coder 7B | 15 of 34 (44%) | 9 of 10 | 1 | 6 |

Every question and failure is in [`qa_agent/results/RESULTS.md`](../qa_agent/results/RESULTS.md).

**What the first run taught me.** On the first run, the 14B model got 13 of 34 and the 7B 9 of 34. Most failures were my harness, not the models: the prompt never said what day it was or what years the data covers, so the models declined questions about 2025 as being "in the future". I fixed three prompt problems (the date and coverage, a placeholder word the models copied as their reason to decline, and always showing the table that names each session) and changed the scoring so repeated identical rows count once. The questions and reference answers did not change, and both runs are kept in the results.

**What still goes wrong** (14B). It counted Hamilton's wins from 2007 to 2024 as 43 (the reference gives 105). It returned no grid position for the São Paulo race (a NULL, not 17). It counted safety car periods where the question asked for races (10, not 8). It answered "how many laps was the Singapore race" with 1.28. The two unanswerable questions it answered were near misses: it treated the time in the pit lane as stationary time, and the first sector time as the time through Turn 1. It declined the clear cases (future events, salaries, tyre pressures).

**A second question set.** To check that I had not just tuned the prompts to those 44 questions, I froze the prompts, wrote 36 new questions (28 answerable, 8 not) with different drivers, races and years, and ran each model once.

| Model | Correct on answerable questions | Declined the unanswerable correctly | Declined an answerable question |
|---|---|---|---|
| qwen2.5-coder 14B | 25 of 28 (89%) | 8 of 8 | 1 |
| qwen2.5-coder 7B | 14 of 28 (50%) | 8 of 8 | 2 |

The scores held up, so the prompt changes did not only fit the first set. The same two failures came back. Asked how many laps long a race was, both models returned a meaningless number (2.6 and 110,450 instead of 57), and both gave 17 for the number of 2025 races with a safety car where the reference gives 12. I wrote the second set knowing about those failures, so it includes questions of the same shape. The 14B model also declined a Senna question it could answer, and the 7B model answered it with 0.

**How far to trust this.** The sets are small: on the second one a single question is 3.6 points, and 25 of 28 is consistent with roughly 73% to 96% on other questions. I wrote both sets and every reference query. Only the second set was kept apart from the prompt changes, so the first set's numbers are the ones to discount. Both models also declined every unanswerable question in the second set, but the first set shows they will sometimes answer a question that merely looks close to something in the data, so 8 of 8 is not a promise.
