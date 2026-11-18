"""
A/B Test Statistical Evaluation & Guardrail Engine
Validates traffic split integrity (SRM), conversion lift, revenue impact,
and latency guardrails before full feature rollout.
"""

import numpy as np
import pandas as pd
from scipy import stats


def simulate_experiment_logs(n_users: int = 40000) -> pd.DataFrame:
    """Generates user-level experiment logs for a 50/50 checkout test."""
    rng = np.random.default_rng(42)

    variants = rng.choice(["control", "treatment"], size=n_users, p=[0.50, 0.50])
    is_treatment = (variants == "treatment")

    # Baseline conversion: 6.2% in control, ~6.85% in treatment (+10.5% relative lift)
    conv_probs = np.where(is_treatment, 0.0685, 0.0620)
    converted = rng.binomial(1, conv_probs)

    # Order value for converted users (log-normal distribution)
    order_values = np.where(
        converted == 1,
        np.round(rng.lognormal(mean=4.1, sigma=0.45, size=n_users), 2),
        0.0
    )

    # Guardrail: Checkout page load time in milliseconds
    latency_ms = np.where(
        is_treatment,
        rng.normal(loc=435, scale=65, size=n_users),
        rng.normal(loc=420, scale=60, size=n_users)
    ).clip(150, 2500)

    return pd.DataFrame({
        "user_id": np.arange(100000, 100000 + n_users),
        "variant": variants,
        "converted": converted,
        "revenue_usd": order_values,
        "latency_ms": np.round(latency_ms, 1)
    })


def check_srm(n_control: int, n_treatment: int, expected_ratio: float = 0.50) -> float:
    """Runs Chi-Square goodness-of-fit test to detect Sample Ratio Mismatch."""
    total = n_control + n_treatment
    observed = [n_control, n_treatment]
    expected = [total * expected_ratio, total * (1 - expected_ratio)]
    _, p_val = stats.chisquare(f_obs=observed, f_exp=expected)
    return float(p_val)


def two_proportion_ztest(conv_c: int, n_c: int, conv_t: int, n_t: int):
    """Calculates relative lift, 95% confidence interval, and two-sided p-value."""
    p_c = conv_c / n_c
    p_t = conv_t / n_t
    diff = p_t - p_c
    rel_lift = (diff / p_c) * 100

    p_pool = (conv_c + conv_t) / (n_c + n_t)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z_stat = diff / se_pool
    p_val = 2 * (1 - stats.norm.cdf(abs(z_stat)))

    # Unpooled standard error for 95% CI
    se_unpooled = np.sqrt((p_c * (1 - p_c) / n_c) + (p_t * (1 - p_t) / n_t))
    ci_low = (diff - 1.96 * se_unpooled) * 100
    ci_high = (diff + 1.96 * se_unpooled) * 100

    return p_c * 100, p_t * 100, rel_lift, (ci_low, ci_high), float(p_val)


def evaluate_experiment(df: pd.DataFrame):
    ctrl = df[df["variant"] == "control"]
    trt = df[df["variant"] == "treatment"]

    n_c, n_t = len(ctrl), len(trt)
    conv_c, conv_t = int(ctrl["converted"].sum()), int(trt["converted"].sum())

    print("\n--- Experiment Readout: EXP_2026_CHECKOUT_FLOW ---")
    print(f"Sample Size   -> Control: {n_c:,} | Treatment: {n_t:,}")

    # Step 1: Data Integrity Check (SRM)
    srm_p = check_srm(n_c, n_t)
    print(f"SRM Check     -> p-value: {srm_p:.4f} ({'PASS' if srm_p > 0.01 else 'FAIL - Traffic Split Bug'})")

    if srm_p <= 0.01:
        print("\nDecision: HOLD ROLLOUT. Fix logging/bucketing mismatch before reading metrics.")
        return

    # Step 2: Primary Metric (Conversion Rate)
    cr_c, cr_t, lift, (ci_lo, ci_hi), p_val = two_proportion_ztest(conv_c, n_c, conv_t, n_t)
    print(f"\nPrimary Metric (Checkout Conversion):")
    print(f"  Control Rate   : {cr_c:.2f}%")
    print(f"  Treatment Rate : {cr_t:.2f}%")
    print(f"  Relative Lift  : {lift:+.2f}% (95% CI: [{ci_lo:+.2f}%, {ci_hi:+.2f}%] abs)")
    print(f"  p-value        : {p_val:.5f}")

    # Step 3: Secondary Metric (Revenue Per User via Welch's t-test)
    _, rev_pval = stats.ttest_ind(trt["revenue_usd"], ctrl["revenue_usd"], equal_var=False)
    rpu_c, rpu_t = ctrl["revenue_usd"].mean(), trt["revenue_usd"].mean()
    print(f"\nSecondary Metric (Revenue Per User):")
    print(f"  Control RPU    : ${rpu_c:.2f} | Treatment RPU: ${rpu_t:.2f} (p={rev_pval:.4f})")

    # Step 4: Guardrail Metric (P95 Latency)
    p95_c = np.percentile(ctrl["latency_ms"], 95)
    p95_t = np.percentile(trt["latency_ms"], 95)
    latency_delta = p95_t - p95_c
    print(f"\nGuardrail Metric (P95 Page Latency):")
    print(f"  Control P95    : {p95_c:.1f} ms | Treatment P95: {p95_t:.1f} ms (Delta: {latency_delta:+.1f} ms)")

    # Final Rollout Recommendation
    stat_sig = p_val < 0.05 and lift > 0
    guardrail_ok = latency_delta < 50.0  # Max 50ms latency budget

    print("\n--------------------------------------------------")
    if stat_sig and guardrail_ok:
        print("RECOMMENDATION: SHIP TO 100% TRAFFIC")
    elif stat_sig and not guardrail_ok:
        print("RECOMMENDATION: HOLD - Statistically significant lift, but latency guardrail breached.")
    else:
        print("RECOMMENDATION: DO NOT SHIP - No statistically significant conversion gain.")
    print("--------------------------------------------------\n")


if __name__ == "__main__":
    logs = simulate_experiment_logs(40000)
    evaluate_experiment(logs)