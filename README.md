# A/B Experimentation & Feature Rollout Engine

A statistical evaluation framework for online controlled experiments. Automates traffic split validation, primary conversion hypothesis testing, and latency guardrail checks before ramping new product features to 100% of users.

## Problem Context
Product teams often ship or kill features based on early noisy conversion numbers without checking whether traffic bucketing worked properly or whether the new UI slowed down page load times. This repository standardizes experiment readouts across SQL data extraction and Python statistical testing.

## Files
- `ab_experiment_funnel.sql`: Deduplicates user assignments on first exposure, joins 48-hour post-exposure completed orders, and computes p95 latency guardrails.
- `experiment_eval.py`: Runs Sample Ratio Mismatch (SRM) checks, two-proportion Z-tests, Welch's t-tests for revenue per user, and outputs a rollout decision.
- `requirements.txt`: Python dependencies.

## Evaluation Workflow
1. **First-Exposure Deduplication:** Uses `ROW_NUMBER()` partitioned by user to isolate the initial variant assignment and prevent cross-contamination.
2. **Sample Ratio Mismatch (SRM):** Runs a Chi-Square goodness-of-fit test (`p < 0.01` threshold) to catch telemetry drops or bucketing bugs before trusting conversion metrics.
3. **Hypothesis & Revenue Testing:** Computes two-sided Z-test p-values and 95% confidence intervals on checkout conversion, alongside Welch's t-test on revenue per user.
4. **Guardrail Enforcement:** Verifies that P95 page latency stays within a +50ms budget so conversion gains do not come at the cost of site reliability.

## How to Run

```bash
git clone https://github.com/puneetgoswami1/ab-testing-experimentation-engine.git
cd ab-testing-experimentation-engine

pip install -r requirements.txt
python experiment_eval.py