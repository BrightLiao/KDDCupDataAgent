# Eval diff — `baseline_v2` vs `v0_v3_full`

- runs: 1 vs 1
- n_tasks: 50 vs 50
- lam: 0.5 / 0.5

## Accuracy（辅助；50 条噪声 ±8% 视为噪声）

- 🟢 micro: 0.4000 → 0.5716 (+0.1716)
- 🟢 macro: 0.3087 → 0.4060 (+0.0973)

### by_difficulty

| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |
| --- | ---: | ---: | ---: | --- | --- |
| easy | 0.4000 | 0.6089 | +0.2089 | 6 / 9 | 8 / 4 |
| extreme | 0.0000 | 0.0000 | +0.0000 | 0 / 2 | 0 / 2 |
| hard | 0.4000 | 0.3000 | -0.1000 | 4 / 6 | 3 / 7 |
| medium | 0.4348 | 0.7151 | +0.2803 | 10 / 13 | 15 / 5 |

### by_data_kind

| kind | base mean | ch mean | Δ |
| --- | ---: | ---: | ---: |
| ? | 0.0000 | 0.0000 | +0.0000 |
| csv | 0.1667 | 0.3333 | +0.1666 |
| db | 1.0000 | 0.0000 | -1.0000 |
| json | 0.5000 | 0.3958 | -0.1042 |
| mixed | 0.4211 | 0.6578 | +0.2367 |

## Distribution（副作用监测）

- 🟢 step_per_task p95: 16 → 13
  - mean: 11.2 → 4.48, p50: 11.0 → 3.5, max: 16 → 17
- 🟢 approx_tokens p95: 3034 → 1927
  - mean: 1506.04 → 731.42, p99: 4544 → 4047
- submit_attempts: once 36 → 42 (+6) | multiple 0 → 0 (+0) | zero 14 → 8 (-6)
  - 🟢 未提交题数减少 -6

## Submission

- 🟢 submitted: 36 → 42 (+6) (rate 72.00% → 84.00%)
- perfect: 20 → 26 (+6)
- zero: 30 → 18 (-12) (lower better)

## Failure clusters

| cluster | base | ch | Δ |
| --- | ---: | ---: | ---: |
| 🟢 other | 8 | 0 | -8 |
| 🔴 parse_error | 0 | 1 | +1 |
| 🔴 schema_misunderstanding | 0 | 8 | +8 |
| 🟢 sql_syntax | 3 | 0 | -3 |
| 🟢 step_budget_exhausted | 13 | 0 | -13 |
| 🔴 timeout | 0 | 9 | +9 |

- 🔴 新出现失败模式：parse_error, schema_misunderstanding, timeout

## Per-task highlights

### 🔴 Top regressions (top 4)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_408 | hard | 1.0000 | 0.0000 | -1.0000 |
| task_415 | hard | 1.0000 | 0.0000 | -1.0000 |
| task_11 | easy | 1.0000 | 0.5000 | -0.5000 |
| task_243 | medium | 1.0000 | 0.6250 | -0.3750 |

### 🟢 Top improvements (top 10)

| task | difficulty | base | ch | Δ |
| --- | --- | ---: | ---: | ---: |
| task_173 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_261 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_86 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_180 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_64 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_22 | easy | 0.0000 | 1.0000 | +1.0000 |
| task_214 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_349 | hard | 0.0000 | 1.0000 | +1.0000 |
| task_305 | medium | 0.0000 | 1.0000 | +1.0000 |
| task_250 | medium | 0.0000 | 1.0000 | +1.0000 |
