# Eval diff — `baseline_3seed` vs `v0_3seed`

- runs: 3 vs 3
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Consistency（主信号）

- 🟢 all_agree: 13 → 22 (+9)
- 🟢 majority_agree: 26 → 36 (+10)
- 🔴 answer_entropy: 0.2118 → 0.2853 (+0.0735)（lower better）

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟢 micro: 0.3723 → 0.5283 (+0.1560)
- 🟢 macro: 0.2891 → 0.3714 (+0.0823)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.3930 | 0.5987 | +0.2057 | 3 / 5 | 7 / 3 |
| extreme | 0.0000 | 0.0000 | +0.0000 | 0 / 2 | 0 / 2 |
| hard | 0.3722 | 0.2278 | -0.1444 | 3 / 5 | 0 / 5 |
| medium | 0.3913 | 0.6589 | +0.2676 | 4 / 9 | 10 / 4 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.1759 | 0.2130 | +0.0371 |
| db | 1.0000 | 0.0000 | -1.0000 |
| json | 0.4236 | 0.4375 | +0.0139 |
| mixed | 0.3912 | 0.6154 | +0.2242 |

## Distribution（副作用监测）

- 🟢 step_per_task p95: 16 → 11
  - mean: 11.51 → 5.01, p50: 11.84 → 4.33, max: 16 → 14
- 🟢 approx_tokens p95: 2638 → 1954.33
  - mean: 1442.32 → 842.86, p99: 3181.33 → 3341.33
- submit_attempts: once 32 → 42 (+10) | multiple 0 → 0 (+0) | zero 18 → 8 (-10)
  - 🟢 未提交题数减少 -10

## Submission

- 🟢 submitted: 43 → 48 (+5) (rate 86.00% → 96.00%)
- perfect: 10 → 17 (+7)
- zero: 21 → 14 (-7) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🟢 other | 9 | 2 | -7 |
| 🔴 schema_misunderstanding | 0 | 7 | +7 |
| 🟢 step_budget_exhausted | 17 | 0 | -17 |
| 🔴 timeout | 0 | 5 | +5 |

- 🔴 新出现失败模式：schema_misunderstanding, timeout

## Per-task highlights

### 🔴 Top regressions (top 7)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_408 | hard | 1.0000 | 0.0000 | -1.0000 |
| task_415 | hard | 1.0000 | 0.3333 | -0.6667 |
| task_283 | medium | 1.0000 | 0.3333 | -0.6667 |
| task_330 | hard | 1.0000 | 0.5833 | -0.4167 |
| task_11 | easy | 1.0000 | 0.6667 | -0.3333 |
| task_218 | medium | 1.0000 | 0.6667 | -0.3333 |
| task_355 | hard | 0.0556 | 0.0278 | -0.0278 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_250 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_287 | medium | 0.3333 | 1.0000 | +0.6667 |
| task_305 | medium | 0.3333 | 1.0000 | +0.6667 |
| task_22 | easy | 0.3333 | 1.0000 | +0.6667 |
| task_64 | easy | 0.3333 | 1.0000 | +0.6667 |
| task_214 | medium | 0.3333 | 1.0000 | +0.6667 |
| task_349 | hard | 0.0000 | 0.6667 | +0.6667 |
| task_173 | medium | 0.0000 | 0.6667 | +0.6667 |
| task_259 | medium | 0.0000 | 0.5714 | +0.5714 |
| task_257 | medium | 0.0000 | 0.5000 | +0.5000 |
