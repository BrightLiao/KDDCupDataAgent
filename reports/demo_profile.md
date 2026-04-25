# Phase 1 Demo Profile

- Total tasks: **50**
- Task ID range: `task_11` .. `task_420` (non-contiguous)
- Total input bytes: 2G

## Difficulty distribution

| Difficulty | Count |
| --- | --- |
| easy | 15 |
| medium | 23 |
| hard | 10 |
| extreme | 2 |

## Context modality presence (by difficulty)

| Difficulty | csv | db | json | doc | knowledge.md | n |
| --- | --- | --- | --- | --- | --- | --- |
| easy | 12 | 0 | 15 | 0 | 15 | 15 |
| medium | 17 | 23 | 13 | 0 | 23 | 23 |
| hard | 7 | 3 | 2 | 10 | 10 | 10 |
| extreme | 1 | 1 | 0 | 2 | 2 | 2 |

## Input size per difficulty (MB)

| Difficulty | min | median | mean | max |
| --- | --- | --- | --- | --- |
| easy | 0.0 | 0.3 | 4.7 | 58.3 |
| medium | 0.0 | 1.4 | 59.5 | 440.8 |
| hard | 0.0 | 0.2 | 27.1 | 266.5 |
| extreme | 0.4 | 42.0 | 42.0 | 83.7 |

## doc/ size among hard/extreme tasks

| task_id | difficulty | doc/ size |
| --- | --- | --- |
| task_330 | hard | 12K |
| task_355 | hard | 32K |
| task_379 | hard | 36K |
| task_344 | hard | 54K |
| task_352 | hard | 61K |
| task_349 | hard | 73K |
| task_408 | hard | 84K |
| task_415 | hard | 90K |
| task_350 | hard | 116K |
| task_396 | hard | 174K |
| task_418 | extreme | 363K |
| task_420 | extreme | 1M |

## gold.csv shape

| task_id | difficulty | rows | cols | columns |
| --- | --- | --- | --- | --- |
| task_11 | easy | 3 | 3 | `ID`, `SEX`, `Diagnosis` |
| task_19 | easy | 3 | 2 | `first_name`, `last_name` |
| task_22 | easy | 2 | 1 | `date_received` |
| task_24 | easy | 1 | 1 | `COUNT(T2.link_to_member)` |
| task_25 | easy | 1 | 1 | `event_name` |
| task_26 | easy | 1 | 1 | `COUNT(T2.member_id)` |
| task_27 | easy | 1 | 3 | `first_name`, `last_name`, `SUM(T2.cost)` |
| task_38 | easy | 140 | 1 | `trans_id` |
| task_64 | easy | 4 | 1 | `power_name` |
| task_67 | easy | 1 | 1 | `AVG(T1.weight_kg)` |

- gold rows: min=1 median=1 max=140
- gold cols: min=1 median=1 max=3

- columns containing SQL keywords (COUNT/SUM/CAST/...): **26 / 63**
  → evidence that demo is reformatted from BIRD-like benchmarks.

- knowledge.md present in 50/50 tasks, chars min=4795 median=5540 max=6616
