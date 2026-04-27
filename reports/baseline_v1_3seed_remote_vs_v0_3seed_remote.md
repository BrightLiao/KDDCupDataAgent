# Eval diff — `baseline_v1_3seed_remote` vs `v0_3seed_remote`

- runs: 3 vs 3
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Consistency（主信号）

- 🟢 all_agree: 26 → 31 (+5)
- 🟢 majority_agree: 37 → 40 (+3)
- 🟢 answer_entropy: 0.2686 → 0.2469 (-0.0217)（lower better）

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟡 micro: 0.5845 → 0.5852 (+0.0007)
- 🟡 macro: 0.4362 → 0.4334 (-0.0028)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.6585 | 0.5818 | -0.0767 | 8 / 2 | 7 / 4 |
| extreme | 0.0000 | 0.0000 | +0.0000 | 0 / 2 | 0 / 2 |
| hard | 0.4333 | 0.4583 | +0.0250 | 3 / 4 | 3 / 3 |
| medium | 0.6528 | 0.6935 | +0.0407 | 11 / 4 | 12 / 5 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.2778 | 0.3750 | +0.0972 |
| db | 0.6667 | 0.3333 | -0.3334 |
| json | 0.4792 | 0.3958 | -0.0834 |
| mixed | 0.6572 | 0.6604 | +0.0032 |

## Distribution（副作用监测）

- 🟡 step_per_task p95: 11.33 → 13
  - mean: 5.43 → 6.17, p50: 4.67 → 5.67, max: 17 → 17
- 🟡 approx_tokens p95: 2439.67 → 2529.67
  - mean: 931.87 → 985.44, p99: 3398.67 → 2938
- submit_attempts: once 45 → 46 (+1) | multiple 0 → 0 (+0) | zero 5 → 4 (-1)
  - 🟢 未提交题数减少 -1

## Submission

- 🟡 submitted: 47 → 47 (+0) (rate 94.00% → 94.00%)
- perfect: 22 → 22 (+0)
- zero: 12 → 14 (+2) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🔴 api_error | 0 | 1 | +1 |
| 🟡 other | 1 | 1 | +0 |
| 🟢 timeout | 11 | 9 | -2 |

- 🔴 新出现失败模式：api_error

## Per-task highlights

### 🔴 Top regressions (top 9)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_283 | medium | 1.0000 | 0.0000 | -1.0000 |
| task_86 | easy | 1.0000 | 0.5833 | -0.4167 |
| task_408 | hard | 0.6667 | 0.3333 | -0.3334 |
| task_11 | easy | 0.8333 | 0.5000 | -0.3333 |
| task_269 | medium | 1.0000 | 0.6667 | -0.3333 |
| task_199 | medium | 0.3333 | 0.0000 | -0.3333 |
| task_173 | medium | 0.3333 | 0.0000 | -0.3333 |
| task_89 | easy | 0.3333 | 0.0000 | -0.3333 |
| task_25 | easy | 0.2500 | 0.0000 | -0.2500 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_303 | medium | 0.3333 | 1.0000 | +0.6667 |
| task_196 | medium | 0.0000 | 0.6667 | +0.6667 |
| task_180 | medium | 0.0000 | 0.6667 | +0.6667 |
| task_330 | hard | 0.5833 | 0.9167 | +0.3334 |
| task_250 | medium | 0.6667 | 1.0000 | +0.3333 |
| task_145 | medium | 0.6667 | 1.0000 | +0.3333 |
| task_379 | hard | 0.0000 | 0.2500 | +0.2500 |
| task_259 | medium | 0.3889 | 0.5754 | +0.1865 |
| task_38 | easy | 0.3778 | 0.5611 | +0.1833 |
| task_243 | medium | 0.5417 | 0.6250 | +0.0833 |
