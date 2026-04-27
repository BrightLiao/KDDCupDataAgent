# Eval diff — `baseline` vs `v0_v2`

- runs: 1 vs 1
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟡 micro: 0.5153 → 0.5743 (+0.0590)
- 🟡 macro: 0.4022 → 0.4340 (+0.0318)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.5789 | 0.5756 | -0.0033 | 8 / 5 | 8 / 5 |
| extreme | 0.0000 | 0.0000 | +0.0000 | 0 / 2 | 0 / 2 |
| hard | 0.5083 | 0.5083 | +0.0000 | 5 / 4 | 5 / 4 |
| medium | 0.5217 | 0.6522 | +0.1305 | 12 / 11 | 15 / 8 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.3472 | 0.3472 | +0.0000 |
| db | 1.0000 | 1.0000 | +0.0000 |
| json | 0.5208 | 0.2708 | -0.2500 |
| mixed | 0.5421 | 0.6461 | +0.1040 |

## Distribution（副作用监测）

- 🟢 step_per_task p95: 30 → 17
  - mean: 9.66 → 6.56, p50: 8.0 → 6.0, max: 30 → 17
- 🟢 approx_tokens p95: 4756 → 3491
  - mean: 1316.68 → 1142.88, p99: 7132 → 5149
- submit_attempts: once 40 → 46 (+6) | multiple 0 → 0 (+0) | zero 10 → 4 (-6)
  - 🟢 未提交题数减少 -6

## Submission

- 🟢 submitted: 40 → 46 (+6) (rate 80.00% → 92.00%)
- perfect: 25 → 28 (+3)
- zero: 22 → 19 (-3) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🟢 other | 10 | 1 | -9 |
| 🟢 sql_syntax | 1 | 0 | -1 |
| 🟢 step_budget_exhausted | 3 | 0 | -3 |
| 🔴 timeout | 7 | 18 | +11 |

## Per-task highlights

### 🔴 Top regressions (top 3)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_283 | medium | 1.0000 | 0.0000 | -1.0000 |
| task_11 | easy | 1.0000 | 0.0000 | -1.0000 |
| task_38 | easy | 0.6000 | 0.5500 | -0.0500 |

### 🟢 Top improvements (top 5)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_250 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_257 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_269 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_86 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_200 | medium | 0.0000 | 1.0000 | +1.0000 |
