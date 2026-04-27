# Eval diff — `baseline_3seed_remote` vs `baseline_v1_3seed_remote`

- runs: 3 vs 3
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Consistency（主信号）

- 🟢 all_agree: 9 → 26 (+17)
- 🟢 majority_agree: 28 → 37 (+9)
- 🔴 answer_entropy: 0.1318 → 0.2686 (+0.1368)（lower better）

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟢 micro: 0.3756 → 0.5845 (+0.2089)
- 🟢 macro: 0.3268 → 0.4362 (+0.1094)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.4278 | 0.6585 | +0.2307 | 4 / 6 | 8 / 2 |
| extreme | 0.1666 | 0.0000 | -0.1666 | 0 / 1 | 0 / 2 |
| hard | 0.3361 | 0.4333 | +0.0972 | 2 / 4 | 3 / 4 |
| medium | 0.3768 | 0.6528 | +0.2760 | 1 / 10 | 11 / 4 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.1157 | 0.2778 | +0.1621 |
| db | 1.0000 | 0.6667 | -0.3333 |
| json | 0.4375 | 0.4792 | +0.0417 |
| mixed | 0.4035 | 0.6572 | +0.2537 |

## Distribution（副作用监测）

- 🟢 step_per_task p95: 16 → 11.33
  - mean: 11.05 → 5.43, p50: 11.0 → 4.67, max: 16 → 17
- 🟢 approx_tokens p95: 3258.67 → 2439.67
  - mean: 1392.26 → 931.87, p99: 3932.33 → 3398.67
- submit_attempts: once 31 → 45 (+14) | multiple 0 → 0 (+0) | zero 19 → 5 (-14)
  - 🟢 未提交题数减少 -14

## Submission

- 🟢 submitted: 40 → 47 (+7) (rate 80.00% → 94.00%)
- perfect: 7 → 22 (+15)
- zero: 21 → 12 (-9) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🟢 other | 7 | 1 | -6 |
| 🟢 step_budget_exhausted | 16 | 0 | -16 |
| 🔴 timeout | 2 | 11 | +9 |

## Per-task highlights

### 🔴 Top regressions (top 5)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_196 | medium | 0.6667 | 0.0000 | -0.6667 |
| task_303 | medium | 0.6667 | 0.3333 | -0.3334 |
| task_408 | hard | 1.0000 | 0.6667 | -0.3333 |
| task_420 | extreme | 0.3333 | 0.0000 | -0.3333 |
| task_243 | medium | 0.6667 | 0.5417 | -0.1250 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_305 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_269 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_218 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_86 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_200 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_22 | easy | 0.3333 | 1.0000 | +0.6667 |
| task_349 | hard | 0.3333 | 1.0000 | +0.6667 |
| task_259 | medium | 0.0000 | 0.3889 | +0.3889 |
| task_38 | easy | 0.0000 | 0.3778 | +0.3778 |
| task_145 | medium | 0.3333 | 0.6667 | +0.3334 |
