# Decisions, limitations and roadmap

[Back to the README](../README.md)

## Why it exists

Most F1 tools are viewers: they show the timing screen. This project asks a narrower question: *how well can the numbers on that screen be reconstructed and used for strategy decisions, and how do we know?* Every derived number here comes with a test against something independent (official sector timing, official classification, real pit stops), and the limits are written down.

## Decisions and dead ends

- **A per-circuit tyre-trend offset, shrunk toward the global line, was tested and not adopted.** Holding out one race at a time and learning the offset from that circuit's other races, the mean absolute error of the predicted trend fell from 0.0079 to 0.0071 s per lap (116 races with a same-circuit history). That gain is 0.0008 s per lap with a 95% interval of -0.0003 to +0.0023 (resampling circuits), and the shrunk model was closer than the plain line for only about half the races. For Jeddah, Las Vegas and Marina Bay the held-out bias fell to about -0.007, -0.005 and +0.004 s per lap, but those circuits were picked because the line already missed them. With about four races per circuit the offsets are poorly determined (between-circuit spread 0.0090 against race-to-race noise 0.0087 s per lap), so the model keeps the global line and the known biases stay documented (`experiments/trend_circuit.py`).
- **Files instead of a warehouse.** The earlier version used a warehouse trial that expired. This one has nothing to expire. dbt runs on DuckDB for the same reason.
- **Reconciliation metric.** Exact finishing-position match flagged 52 to 64 races, mostly for reasons that were not real problems: post-race penalties change the official order, and retirements are not ranked on the same scale. Comparing classified finishers pairwise, plus lap counts, cut it to four races that deserve a look.
- **Direction-aware map matching made things worse** (Miami exact order fell from 93% to 87%), so it was dropped. A stricter lap-length check helped (93% to 96%).
- **Circuit-specific pit loss needs enough data.** On 2025-2026 alone it did not beat one global figure; over nine seasons on the canonical circuit key it did, by 0.57 s of mean error.
- **A live-gap rejoin model was no better** than lap-end times.
- **One tyre trend constant was biased by lap length.** Short circuits looked worse and long ones better than they are. A lap-length line fixed most of it out of sample; three circuits still carry a bias as large as the effect.
- **Degradation did not help predict undercuts.** Tyre advantage and car pace added nothing measurable to the gap alone (95% intervals across races include zero), and the time gained is mostly noise. No undercut model was built.
- **Streamlit first, then a static web app.** All the logic is in Python and dbt, so the site only draws precomputed JSON and needs no server. It came after the gold tables were stable, so a page never has its own version of a number.
- **The pit-stop predictor is scored on races it was not fitted on.** Its circuit pit-loss figure came from the same races it was scored on, which could have flattered it. Leaving each race out of its own estimate changed the exact-place rate by about 0.1 point, so the in-sample scores stand.
- **Live timing was dropped:** live car positions need an F1 TV subscription.

## Limitations

- New sessions cannot be ingested at the moment. Since about 15 October 2026 F1's timing archive (`livetiming.formula1.com/static`) answers HTTP 401 to unauthenticated requests (FastF1 issue #978, open, no fix posted when I checked). The lake is complete through round 17 of 2026 (Singapore); later sessions cannot be loaded until access changes. On 2 November 2026 I tried the United States and Mexico City weekends (nine sessions): FastF1 3.8.3 could not load any of them, and all nine are recorded as failed in the ingest log. FastF1 3.9.0 adds a sign-in with an F1TV account for this, and says an F1TV Access subscription or higher is needed; loading the United States race with it went straight to a sign-in prompt. I did not sign in, did not upgrade the project's environment, and have not checked whether the F1TV terms allow automated use. Everything downstream (dbt, the app, the analyses) works on the existing lake.
- GPS position is already snapped to a common line, so cars cannot be shown side by side.
- The simulated safety car is placed about 500 m ahead of the leader (no safety car GPS exists). The web replay does not draw one; it shows the safety car as a pulsing track edge and a label.
- Red-flag periods end at the next pit-exit-open, safety car, track-clear or race-start message; no message states the end.
- Wind speed is assumed to be in m/s, and the DRS open codes are an interpretation of the FastF1 documentation. The track status code meanings are confirmed by the feed's own labels (1 AllClear, 2 Yellow, 4 SCDeployed, 5 Red, 6 VSCDeployed, 7 VSCEnding).
- Gaps are lap-timing based at the lines and GPS based in between; the running order is validated against official sector timing on 135 sessions (four of them in detail), the time gaps on those four only.
- Safety car, VSC and red-flag periods are a model (`fct_race_control_period`, reconciled to the Python), but the Race scrubber in the Streamlit app still uses `app/racecontrol.py`, which stays as the reference.
- The reconciliation is against my own ingest of the public feed, so it shows internal consistency and agreement with the official classification, not that the feed itself is right.
- Tyre degradation is measured from the timing data alone and has not been validated against any outside source (an attempt to test it against undercut outcomes was inconclusive); three circuits are known to be biased (see Strategy models).

- The web app's JSON is a snapshot of the gold tables at export time. Nothing refreshes it automatically: the Airflow DAG does not run the exporters.
- The repository includes derived JSON for the web app (lap and sector times, season results, pit-stop scores, predictor scores), and I have found nothing that expressly allows publishing F1 timing data (see Data terms). If a rights holder objects, it is removed. The telemetry trace and replay data are not committed.
- The pit-stop predictor does not model other cars pitting around the stop, traffic after it, or safety cars; held-out scoring covers green-flag stops only (see Web app).
- Trace distances are derived from positions, and sector colours are computed here, not taken from the feed (see Web app).

## Roadmap

- Fix the second-sector-line failures at Baku and Suzuka in the race-state engine (a heading constraint fixes them but worsens about two dozen other sessions, and a hybrid did not help; next idea: apply the constraint only where the samples around a point are reliable)
- Run the Airflow DAG through a live race weekend (telemetry ingest, memory use). Blocked for now: see the first Limitations bullet. Failure alerts are done.
- Make the API the single access path for the app and anything built on top; for now the Streamlit app does not use it
- Switch the Race scrubber to the SQL race-control periods
- Deploy the static site on a free host (Cloudflare Pages is the candidate) once the data-terms question is settled. The trace and replay data are large and git-ignored, so how they are built and hosted needs deciding first
- Find out why the circuit data does not line up in the four weekends listed under Replay, and add a formation-lap marker to the replay
- An S3-compatible object store (MinIO) for the lake, set up with Terraform and run locally
