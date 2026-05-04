# Task 24 — 推理过程

## 问题
> How many members attended the "Women's Soccer" event?

## 结论
**最终答案：17 位成员**

> 直接套用 knowledge.md §5 Example 1 的 Event Attendance KPI：`COUNT(link_to_event) FROM attendance WHERE event_id = X`。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：Women's Soccer event
2. **聚合**：COUNT(members)
3. **待求**：人数

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典（student_club）
├── csv/attendance.csv       ← 出勤事实表（326 行 + 表头）
└── json/event.json          ← 事件维度
```

### Step 2：先看 `knowledge.md`
关键信息：
- §3 Event Attendance KPI: `COUNT(link_to_event)` 即出勤人数
- §5 Example 1 SQL: `SELECT COUNT(link_to_event) FROM attendance WHERE event_id = X`
- → 题目是 §5 Example 1 的直接实例

### Step 3：找 Women's Soccer 的 event_id
```sh
jq '.records[] | select(.event_name | test("Women.s Soccer"; "i"))' context/json/event.json
```
→ event_id = `rec2N69DMcrqN9PJC`，event_date 2019-10-05，type Game

### Step 4：在 attendance.csv 中按 link_to_event 计数
```sh
awk -F',' '$1 == "rec2N69DMcrqN9PJC" {c++; m[$2]=1}
           END {print "rows="c, "distinct_members="(length m)}' context/csv/attendance.csv
```
→ 17 行，17 个 distinct member（每位成员只出现一次）

### 核心思路
> **knowledge.md §5 Example 1 已给模板，把 X 替换为 Women's Soccer 的 event_id 即可。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| 看 JSON 按字段查 | `jq '.records[] \| select(...)'` | 自动允许，专为 JSON |
| CSV 按字段过滤计数 | `awk -F',' '$1 == ...'` | 流式、即用即抛 |

### 方法层面
1. **先用 §5 Example 找到题目模板**：本题与 Example 1 同形
2. **维度表反查 ID 再过滤事实表**：经典做法

### 一句话总结
> **题目 = Example 1 + Women's Soccer 的 event_id → awk 计数。**

---

## 推理线索

### 线索 1：Event Attendance 模板
来源：`knowledge.md` §3 + §5 Example 1
- KPI: `COUNT(link_to_event)`
- SQL 模板: `SELECT COUNT(link_to_event) FROM attendance WHERE event_id = X`

### 线索 2：Women's Soccer 的 event_id
来源：`context/json/event.json`
```json
{
  "event_id": "rec2N69DMcrqN9PJC",
  "event_name": "Women's Soccer",
  "event_date": "2019-10-05T12:00:00",
  "type": "Game"
}
```

### 线索 3：attendance.csv 命中行数 = distinct member 数
- 17 行 link_to_event 匹配 `rec2N69DMcrqN9PJC`
- 17 个不同的 link_to_member（无重复出席）

### 线索 4：等价 SQL
```sql
SELECT COUNT(link_to_member)
FROM attendance
WHERE link_to_event = (
  SELECT event_id FROM event WHERE event_name = "Women's Soccer"
);
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **出勤人数** | **17** |
| event_name | Women's Soccer |
| event_id | rec2N69DMcrqN9PJC |
| event_date | 2019-10-05 |
