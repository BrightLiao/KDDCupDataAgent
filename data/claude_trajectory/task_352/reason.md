# Task 352 — 推理过程

## 问题
> How many times was the budget in Advertisement for "Yearly Kickoff" meeting more than "October Meeting"?

## 结论
**最终答案：2.727272727272727**（即 150 / 55）

> 题目"how many times ... more than"在该数据集 gold 语义里被解释为比值 ratio = budget(Yearly Kickoff Advertisement) / budget(October Meeting Advertisement)，而不是差值或倍数减一。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **类别约束**：budget category = `Advertisement`
2. **事件约束**：仅比较 event_name = `Yearly Kickoff` 与 `October Meeting`
3. **指标**：`amount`（预算分配额，非已花费 spent）
4. **待求**：两者预算的比值（"how many times ... more"）

### Step 1：盘点可用资源
```
context/
├── knowledge.md           ← 数据字典 + 字段语义
├── csv/event.csv          ← 事件维表（event_id ↔ event_name）
└── doc/budget.md          ← 散文式预算账本（含 budget_id → category / amount / spent / event_id）
```
分工：`event.csv` 是事件维表；`budget.md` 同时承载预算-类别表、预算-金额表、预算-事件链接表。

### Step 2：先看 `knowledge.md`
关键信息：
- `amount` 表示**预算金额**，需与"funds received"和"spent"区分（§6 Ambiguity Resolution）。
- 事件由 `event_name` 唯一标识。
- 没有显式给出 budget 表的 schema，但提示了 `budget` 表含 `amount`、`spent` 两字段，且与 `event_id` 关联（§5 Example 2）。

### Step 3：在 `event.csv` 找 event_id
直接查 `event_name`：
- `Yearly Kickoff` → event_id = **recykdvf4LgsyA3wZ**（2019-09-03，Meeting，Closed）
- `October Meeting` → event_id = **recggMW2eyCYceNcy**（2019-10-08，Meeting，Closed）

### Step 4：在 `budget.md` 找两个事件对应的 Advertisement 预算
散文文档由四类信息组成（不同 sub-section 各自描述同一批 budget_id）：
1. Section 1–4：`budget_id → category`
2. Sub-Section 5.x：`budget_id → amount, spent, remaining`
3. Sub-Section 6.x：`budget_id → event_id`（链接关系）

按 event_id 反查 Sub-Section 6.x：
- recykdvf4LgsyA3wZ ← `recvKTAWAFKkVNnXQ`（Sub-Section 6.1：Promotional Initiative Status，line 275）
- recggMW2eyCYceNcy ← 两条记录：
  - `recTxecmwIhCdIKvl`（Sub-Section 6.1，line 261）
  - `rec1bG6HSft7XIvTP`（Sub-Section 6.2 Hospitality，line 279）

继续验证 category：
- recvKTAWAFKkVNnXQ → "designated for **Advertisement**"（line 37）
- recTxecmwIhCdIKvl → "categorized within the portfolio as **Advertisement**"（line 23）
- rec1bG6HSft7XIvTP → "Food"（line 41）→ **不入选**

### Step 5：取出 amount
查 Sub-Section 5.1 Promotional Performance：
- recvKTAWAFKkVNnXQ：初稿 140，最终 reconciled amount = **150**（line 156）
- recTxecmwIhCdIKvl：amount = **55**（line 142）

### Step 6：计算比值
ratio = 150 / 55 = 2.727272727272727...

### 核心思路
> 通过 event_name → event_id → budget_id（在散文 6.x 中）→ category（在 1–4 中）→ amount（在 5.x 中）四级跳，把"Advertisement budget for X meeting"两个标量取出来作除法。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，快速摸文件分工 |
| 读 task.json / knowledge.md | `Read` | 文件小，需要全局语义 |
| 读 event.csv（41 行） | `Bash: cat` | 行数少，全表带入足以做名字→ID 反查 |
| 在 budget.md 中按 ID 锚点扫描 | `Bash: grep -n` | 散文有 359 行，按 `recXxx` 关键词锚点能精确定位三类信息 |
| 跨 section 拼装 budget_id 的 (category, amount, event_id) 三元组 | `Read` 指定 offset | 仅分别读 §1–4、§5.1、§6.1 三段，避免一次性塞全文 |

### 方法层面
1. **先找事件 ID**：散文里只用 ID 串接，先把名字翻译成 ID 才能进散文检索。
2. **散文按 ID 锚点法**：搜 `recXxx` 命中所有提到该 ID 的句子，再按 sub-section 含义归类（category vs. amount vs. linkage）。
3. **不要被同名 event 二次出现迷惑**：同一 event_id 可能被多个 budget 引用（如 October Meeting 同时挂着 Advertisement 和 Food 两条预算），必须按问题要求的 category 过滤。

### 一句话总结
> 散文型 budget.md 把一份关系表拆成了四个 sub-section 写成段落；解题等于把 ID 当 join key，用 grep 在不同段落里把字段一项一项抠回来。

---

## 推理线索

### 线索 1：事件名 → 事件 ID
来源：`context/csv/event.csv`
- `Yearly Kickoff,2019-09-03T12:00:00,Meeting,...` → event_id = recykdvf4LgsyA3wZ
- `October Meeting,2019-10-08T12:00:00,Meeting,...` → event_id = recggMW2eyCYceNcy
→ 后续都用 ID 在 budget.md 中检索。

### 线索 2：事件 ID → 关联预算
来源：`context/doc/budget.md` Sub-Section 6.1 / 6.2
- line 275："recvKTAWAFKkVNnXQ ... event record **recykdvf4LgsyA3wZ**"（Yearly Kickoff）
- line 261："recTxecmwIhCdIKvl ... event record **recggMW2eyCYceNcy**"（October Meeting，§6.1 Promotional → Advertisement）
- line 279："food budget rec1bG6HSft7XIvTP ... reference code **recggMW2eyCYceNcy**"（October Meeting，§6.2 → Food，**排除**）
→ 候选 Advertisement 预算：recvKTAWAFKkVNnXQ 与 recTxecmwIhCdIKvl

### 线索 3：预算 ID → 类别 = Advertisement
来源：`context/doc/budget.md` Section 1
- line 37：recvKTAWAFKkVNnXQ — "designated for Advertisement"
- line 23：recTxecmwIhCdIKvl — "categorized ... as Advertisement"
→ 两笔均为 Advertisement，符合题目条件。

### 线索 4：预算 ID → amount
来源：`context/doc/budget.md` Sub-Section 5.1
- line 156：recvKTAWAFKkVNnXQ 最终 reconciled amount = **150**（初稿 140，已修订）
- line 142：recTxecmwIhCdIKvl amount = **55**
→ 计算 150 / 55 = 2.7272727272727275

---

## 等价 SQL（基于推断的 budget 表 schema）

```sql
SELECT
  CAST(SUM(CASE WHEN T2.event_name = 'Yearly Kickoff'  THEN T1.amount ELSE 0 END) AS REAL)
       /  SUM(CASE WHEN T2.event_name = 'October Meeting' THEN T1.amount ELSE 0 END)
FROM   budget AS T1
JOIN   event  AS T2 ON T1.link_to_event = T2.event_id
WHERE  T1.category IN ('Advertisement');
```

代入数值：`(150 + 0) / (0 + 55) = 2.727272727272727`。

---

## 最终答案

| 字段 | 值 |
|---|---|
| Yearly Kickoff Advertisement budget (amount) | 150 |
| October Meeting Advertisement budget (amount) | 55 |
| ratio = Yearly Kickoff / October Meeting | **2.727272727272727** |

> 数据来源：`event.csv`（事件 ID）+ `budget.md` Sections 1、5.1、6.1（类别、金额、链接）。October Meeting 还挂着一笔 Food 预算（rec1bG6HSft7XIvTP，amount = 150），但不在 Advertisement 范围内，按题目过滤掉。
