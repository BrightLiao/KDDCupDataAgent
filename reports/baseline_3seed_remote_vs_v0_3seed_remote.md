# Eval diff — `baseline_3seed_remote` vs `v0_3seed_remote`

- runs: 3 vs 3
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Consistency（主信号）

- 🟢 all_agree: 9 → 31 (+22)
- 🟢 majority_agree: 28 → 40 (+12)
- 🔴 answer_entropy: 0.1318 → 0.2469 (+0.1151)（lower better）

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟢 micro: 0.3756 → 0.5852 (+0.2096)
- 🟢 macro: 0.3268 → 0.4334 (+0.1066)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.4278 | 0.5818 | +0.1540 | 4 / 6 | 7 / 4 |
| extreme | 0.1666 | 0.0000 | -0.1666 | 0 / 1 | 0 / 2 |
| hard | 0.3361 | 0.4583 | +0.1222 | 2 / 4 | 3 / 3 |
| medium | 0.3768 | 0.6935 | +0.3167 | 1 / 10 | 12 / 5 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.1157 | 0.3750 | +0.2593 |
| db | 1.0000 | 0.3333 | -0.6667 |
| json | 0.4375 | 0.3958 | -0.0417 |
| mixed | 0.4035 | 0.6604 | +0.2569 |

## Distribution（副作用监测）

- 🟢 step_per_task p95: 16 → 13
  - mean: 11.05 → 6.17, p50: 11.0 → 5.67, max: 16 → 17
- 🟢 approx_tokens p95: 3258.67 → 2529.67
  - mean: 1392.26 → 985.44, p99: 3932.33 → 2938
- submit_attempts: once 31 → 46 (+15) | multiple 0 → 0 (+0) | zero 19 → 4 (-15)
  - 🟢 未提交题数减少 -15

## Submission

- 🟢 submitted: 40 → 47 (+7) (rate 80.00% → 94.00%)
- perfect: 7 → 22 (+15)
- zero: 21 → 14 (-7) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🔴 api_error | 0 | 1 | +1 |
| 🟢 other | 7 | 1 | -6 |
| 🟢 step_budget_exhausted | 16 | 0 | -16 |
| 🔴 timeout | 2 | 9 | +7 |

- 🔴 新出现失败模式：api_error

## Per-task highlights

### 🔴 Top regressions (top 5)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_408 | hard | 1.0000 | 0.3333 | -0.6667 |
| task_283 | medium | 0.6667 | 0.0000 | -0.6667 |
| task_420 | extreme | 0.3333 | 0.0000 | -0.3333 |
| task_11 | easy | 0.6667 | 0.5000 | -0.1667 |
| task_243 | medium | 0.6667 | 0.6250 | -0.0417 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_305 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_200 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_218 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_145 | medium | 0.3333 | 1.0000 | +0.6667 |
| task_349 | hard | 0.3333 | 1.0000 | +0.6667 |
| task_22 | easy | 0.3333 | 1.0000 | +0.6667 |
| task_180 | medium | 0.0000 | 0.6667 | +0.6667 |
| task_269 | medium | 0.0000 | 0.6667 | +0.6667 |
| task_330 | hard | 0.3333 | 0.9167 | +0.5834 |
| task_86 | easy | 0.0000 | 0.5833 | +0.5833 |
