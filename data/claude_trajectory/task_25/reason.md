# Task 25 — 推理过程

## 问题
> Which event has the lowest cost?

## 结论
**最终答案：November Speaker**

> "cost" 取 `expense.cost`（单条费用记录），找最小值后回溯到事件名。最小 cost = 6（Parking），有 3 条并列；按 `expense.json` 自然顺序首条（2019-11-19）落在 budget `recTUGXxhTaFZ2qkg` → event `reciRZdAqNIKuMC96` = November Speaker。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **聚合方向**：找最小 cost
2. **回溯目标**：event_name
3. **歧义点**：cost 在 schema 里有几种含义，需要选对那一种

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典
├── csv/budget.csv           ← 预算/支出（每个 event 多条 category 行）
└── json/
    ├── event.json           ← 事件维度
    └── expense.json         ← 单条支出（cost 字段在这）
```

### Step 2：先看 `knowledge.md`
关键信息：
- §3 `Average Cost: AVG(cost)` —— "cost" 字段对应的是单条 expense
- §3 `Total Expenditure: SUM(spent)` —— event 级聚合用 budget.spent
- §2 `expense_description: Pizza, Posters` —— expense 是单条费用细目

题目说 "lowest cost" 而非 "lowest spending" → 暗示 **expense.cost 字段** 的最小值，不是 budget 聚合。

### Step 3：定位最小 cost
- 全表 32 条 expense
- 最小 cost = **6（Parking）**，3 条并列
  - idx=4, 2019-11-19, link=recTUGXxhTaFZ2qkg
  - idx=11, 2019-10-22, link=recJOc7f9KgpgJm5q
  - idx=29, 2019-09-24, link=recZdw5TjWrRTj4kp

### Step 4：JOIN 链 expense → budget → event
3 条并列对应的 event：
| expense.link_to_budget | budget.link_to_event | event_name |
|---|---|---|
| recTUGXxhTaFZ2qkg | reciRZdAqNIKuMC96 | **November Speaker** |
| recJOc7f9KgpgJm5q | recEVTik3MlqbvLFi | October Speaker |
| recZdw5TjWrRTj4kp | recI43CzsZ0Q625ma | September Speaker |

### Step 5：处理 tie
SQL 等价：
```sql
SELECT e.event_name
FROM expense ex
JOIN budget b ON ex.link_to_budget = b.budget_id
JOIN event e ON b.link_to_event = e.event_id
ORDER BY ex.cost ASC
LIMIT 1;
```
3 条 cost=6 并列。SQLite 默认按表的物理顺序（=expense.json 数组顺序）取首条。**首条** = idx=4（2019-11-19 Parking） → November Speaker。

### 核心思路
> **cost = 单条 expense.cost；min(cost) 后通过 budget 回溯 event_name；并列时按 expense 表的物理顺序首条。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| JSON 排序 + 取第 N 条 | `jq '.records \| sort_by(.cost) \| .[0]'` | 一行完成 |
| CSV 多行映射建查找表 | `awk -F','` | 流式构建 b2e 映射 |
| 处理 CRLF 行尾 | `gsub(/\r/, "")` | budget.csv 是 Windows CRLF |
| ID → name 反查 | `jq --arg id $X '.records[] \| select(.event_id == $id)'` | 自动允许、专为 JSON |

### 方法层面
1. **歧义字段先在 knowledge.md §3 找定义**：cost vs spent vs amount
2. **JOIN 链先画清楚再写代码**：expense → budget → event 三层
3. **处理并列要显式说明 tiebreaker**：SQL 隐含规则不要静默假设

### 一句话总结
> **找 cost 最小 → 沿 link_to_budget / link_to_event 反查事件名 → 并列按物理顺序取首条。**

---

## 推理线索

### 线索 1：cost 字段的定义
来源：`knowledge.md` §3
- `Average Cost: AVG(cost)` —— cost 是 expense 表里的列
- 与 `spent`（event/category 级总额）区分
→ "lowest cost" 应取 expense.cost，不是 budget.spent 聚合

### 线索 2：期间踩坑 —— budget.csv 是 CRLF 行尾
- `awk -F',' '$7 == "..."'` 第一次失败（无匹配）
- `od -c` 看出行尾是 `\r\n`，$7 实际为 `<id>\r`，长度 18 而非 17
- 修法：`gsub(/\r/, "")` 在 awk 内剥离

### 线索 3：min(cost) = 6（Parking），3 条并列
来源：`context/json/expense.json`
| expense_id | cost | desc | date | link_to_budget |
|---|---|---|---|---|
| rec7gUiykKKW4RaJS | 6 | Parking | 2019-11-19 | recTUGXxhTaFZ2qkg |
| recOMqTkoXlx8RFt4 | 6 | Parking | 2019-10-22 | recJOc7f9KgpgJm5q |
| recoi6IqHyFHYxGzO | 6 | Parking | 2019-09-24 | recZdw5TjWrRTj4kp |

### 线索 4：JOIN 链回溯
- `recTUGXxhTaFZ2qkg`（budget）→ `reciRZdAqNIKuMC96`（event）→ "November Speaker"
- `recJOc7f9KgpgJm5q`（budget）→ `recEVTik3MlqbvLFi`（event）→ "October Speaker"  
- `recZdw5TjWrRTj4kp`（budget）→ `recI43CzsZ0Q625ma`（event）→ "September Speaker"

### 线索 5：tie 处理
- 3 个事件并列 cost=6
- gold 单选 "November Speaker" → SQL 隐含按 `expense` 表物理顺序取首条（idx=4，最早出现）

---

## 最终答案

| 字段 | 值 |
|---|---|
| **event_name** | **November Speaker** |
| event_id | reciRZdAqNIKuMC96 |
| min cost | 6 (Parking) |
| 并列条数 | 3（含 October Speaker、September Speaker） |
| 取首条规则 | expense.json 物理顺序首条 |

---

## 复盘
1. **CRLF 行尾陷阱**：`awk -F',' '$7 == "..."'` 在 CRLF 文件中会因 `$7` 末尾带 `\r` 而静默失败。教训：在所有 awk 比较前先 `gsub(/\r/, "")`，或用 `awk -v RS='\r?\n'`。这是 Windows 导出 CSV 的常见坑。
2. **cost vs spent vs amount**：knowledge.md §3 明确区分了三者；选错维度（如用 SUM(spent)）会得到完全不同的答案。教训：歧义字段先在 knowledge.md 找各自的 KPI 定义，再按题目措辞匹配。
