# Eval diff — `v0_3seed_remote` vs `v0_v5_F1F2tuned_3seed`

- runs: 3 vs 3
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Consistency（主信号）

- 🔴 all_agree: 31 → 25 (-6)
- 🔴 majority_agree: 40 → 37 (-3)
- 🔴 answer_entropy: 0.2469 → 0.3069 (+0.0600)（lower better）

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟡 micro: 0.5852 → 0.6267 (+0.0415)
- 🟡 macro: 0.4334 → 0.4603 (+0.0269)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.5818 | 0.6594 | +0.0776 | 7 / 4 | 9 / 4 |
| extreme | 0.0000 | 0.0000 | +0.0000 | 0 / 2 | 0 / 2 |
| hard | 0.4583 | 0.4417 | -0.0166 | 3 / 3 | 2 / 4 |
| medium | 0.6935 | 0.7403 | +0.0468 | 12 / 5 | 12 / 2 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.3750 | 0.4445 | +0.0695 |
| db | 0.3333 | 0.6667 | +0.3334 |
| json | 0.3958 | 0.5833 | +0.1875 |
| mixed | 0.6604 | 0.6755 | +0.0151 |

## Distribution（副作用监测）

- 🟡 step_per_task p95: 13 → 11.33
  - mean: 6.17 → 5.53, p50: 5.67 → 5.33, max: 17 → 14
- 🟡 approx_tokens p95: 2529.67 → 2529
  - mean: 985.44 → 901.96, p99: 2938 → 2840.67
- submit_attempts: once 46 → 46 (+0) | multiple 0 → 0 (+0) | zero 4 → 4 (+0)

## Submission

- 🟡 submitted: 47 → 47 (+0) (rate 94.00% → 94.00%)
- perfect: 22 → 23 (+1)
- zero: 14 → 12 (-2) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🔴 api_error | 1 | 2 | +1 |
| 🟡 other | 1 | 1 | +0 |
| 🟢 timeout | 9 | 8 | -1 |

## Per-task highlights

### 🔴 Top regressions (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_261 | medium | 1.0000 | 0.3333 | -0.6667 |
| task_86 | easy | 0.5833 | 0.0000 | -0.5833 |
| task_415 | hard | 1.0000 | 0.4167 | -0.5833 |
| task_180 | medium | 0.6667 | 0.3333 | -0.3334 |
| task_350 | hard | 1.0000 | 0.6667 | -0.3333 |
| task_379 | hard | 0.2500 | 0.0000 | -0.2500 |
| task_11 | easy | 0.5000 | 0.3333 | -0.1667 |
| task_287 | medium | 1.0000 | 0.9167 | -0.0833 |
| task_303 | medium | 1.0000 | 0.9167 | -0.0833 |
| task_257 | medium | 0.7500 | 0.6667 | -0.0833 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_19 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_283 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_27 | easy | 0.0833 | 1.0000 | +0.9167 |
| task_355 | hard | 0.0833 | 0.6667 | +0.5834 |
| task_243 | medium | 0.6250 | 1.0000 | +0.3750 |
| task_408 | hard | 0.3333 | 0.6667 | +0.3334 |
| task_269 | medium | 0.6667 | 1.0000 | +0.3333 |
| task_199 | medium | 0.0000 | 0.3333 | +0.3333 |
| task_173 | medium | 0.0000 | 0.3333 | +0.3333 |
| task_330 | hard | 0.9167 | 1.0000 | +0.0833 |
