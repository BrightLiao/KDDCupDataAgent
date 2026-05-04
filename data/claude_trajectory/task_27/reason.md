# Task 27 — 推理过程

## 问题
> List out the full name and total cost that member id "rec4BLdZHS2Blfp4v" incurred?

## 结论
**最终答案：Sacha Harrison，总 cost = 866.25**

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：member_id = "rec4BLdZHS2Blfp4v"
2. **聚合**：SUM(cost)
3. **待求**：full name + total cost

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典
└── json/
    ├── member.json          ← 成员维度（含 first_name, last_name）
    └── expense.json         ← 支出事实（cost + link_to_member）
```

### Step 2：先看 `knowledge.md`
- §2 Members: full name = first_name + last_name
- §3 Average Cost: AVG(cost) → cost 是 expense 字段
- 没有特别陷阱

### Step 3：取成员姓名 + SUM 其支出
```sh
# 名字
jq '.records[] | select(.member_id=="rec4BLdZHS2Blfp4v") | {first_name, last_name}' \
   context/json/member.json
# → Sacha Harrison

# SUM(cost) where link_to_member = 该 ID
jq '[.records[] | select(.link_to_member=="rec4BLdZHS2Blfp4v") | .cost] | add' \
   context/json/expense.json
# → 866.25 (12 笔支出累加)
```

### 核心思路
> **member.json 取姓名 + expense.json 按 link_to_member 过滤后 SUM(cost)。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 工具 |
|---|---|
| JSON 单条查找 | `jq 'select(.member_id == X)'` |
| JSON 求和 | `jq '[... .cost] \| add'` |

### 方法层面
直接 join 两张 JSON。

---

## 推理线索

### 线索 1：member rec4BLdZHS2Blfp4v 姓名
来源：`context/json/member.json`
- first_name: Sacha
- last_name: Harrison

### 线索 2：12 笔支出明细
来源：`context/json/expense.json`，过滤 `link_to_member == "rec4BLdZHS2Blfp4v"`：
122.06, 67.81, 50.13, 74.59, 59.73, 124.12, 61.52, 13.45, 16.28, 67.81, 13.45, 195.3
- SUM = **866.25**

### 线索 3：等价 SQL
```sql
SELECT m.first_name, m.last_name, SUM(e.cost)
FROM expense e JOIN member m ON e.link_to_member = m.member_id
WHERE m.member_id = 'rec4BLdZHS2Blfp4v'
GROUP BY m.member_id;
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **first_name** | Sacha |
| **last_name** | Harrison |
| **SUM(cost)** | **866.25** |
| 支出条数 | 12 |
