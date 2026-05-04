# Task 26 — 推理过程

## 问题
> How many members of the Student_Club have major in 'Physics Teaching'?

## 结论
**最终答案：1 位成员**

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **筛选**：major_name == "Physics Teaching"
2. **聚合**：COUNT(member)

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典
└── json/
    ├── major.json           ← 专业维度（major_id ↔ major_name）
    └── member.json          ← 成员事实（含 link_to_major）
```

### Step 2：先看 `knowledge.md`
- §2 Members 含 `major_name`，"linked through the `major` table" → 通过 `link_to_major → major_id` 关联
- 没有专门的 KPI/Use Case 但模式与其他题目一致

### Step 3：major name → major_id 映射
```sh
jq '.records[] | select(.major_name == "Physics Teaching")' context/json/major.json
```
→ major_id = `recVYIFAwjT91pnv7`

### Step 4：在 member.json 计数
```sh
jq --arg m recVYIFAwjT91pnv7 '[.records[] | select(.link_to_major == $m)] | length' context/json/member.json
```
→ 1

### 核心思路
> **major_name → major_id（维度反查），member.link_to_major 计数。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| 看维度 + 计数 | `jq '.records[] \| select(...)'` | 自动允许，专为 JSON |

### 方法层面
1. 先在维度表把 name 翻译成 ID
2. 在事实表按 ID 计数

### 一句话总结
> **name → ID → count，标准的两表 join。**

---

## 推理线索

### 线索 1：major_name → major_id
来源：`context/json/major.json`
```
{ major_id: "recVYIFAwjT91pnv7", major_name: "Physics Teaching", department: "Physics Department" }
```

### 线索 2：member.link_to_major 计数
来源：`context/json/member.json`，过滤 link_to_major == "recVYIFAwjT91pnv7" → 1 条

### 线索 3：等价 SQL
```sql
SELECT COUNT(m.member_id)
FROM member m JOIN major mj ON m.link_to_major = mj.major_id
WHERE mj.major_name = 'Physics Teaching';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **count** | **1** |
| major_id | recVYIFAwjT91pnv7 |
| department | Physics Department |
