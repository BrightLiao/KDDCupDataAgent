# Task 74 — 推理过程

## 问题
> Provide the eye colour of the superhero who has Karen Beecher-Duncan as their full name.

## 结论
**最终答案：Brown**

> 超级英雄 Bumblebee（id=146, full_name="Karen Beecher-Duncan"），eye_colour_id=9 → colour.json id=9 → "Brown"。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：约束
- full_name == "Karen Beecher-Duncan"
- 待求：eye colour

### Step 1：盘点
```
context/
├── knowledge.md
├── csv/superhero.csv      ← 含 full_name 与 eye_colour_id
└── json/colour.json       ← 颜色维度（id ↔ colour 名）
```

### Step 2-3：两步反查
1. superhero.csv: `full_name=="Karen Beecher-Duncan"` → `eye_colour_id=9`
2. colour.json: `id=9` → `colour="Brown"`

### 核心思路
> **superhero name → eye_colour_id → colour 名 反查。**

---

## 阅读文档的方法与工具

| 场景 | 工具 |
|---|---|
| CSV 单条过滤 | `awk -F',' 'NR>1 && $3 == X'` |
| JSON 单条反查 | `jq --arg id $X 'select(.id == ($id\|tonumber))'` |
| CRLF 处理 | `gsub(/\r/, "")` |

---

## 推理线索

### 线索 1：full_name 命中行
来源：`superhero.csv`
```
146,Bumblebee,Karen Beecher-Duncan,2,9,4,1,24,4,1,170,59
```
表头列序：id, superhero_name, full_name, gender_id, **eye_colour_id**, hair_colour_id, …

### 线索 2：eye_colour_id=9 → "Brown"
来源：`colour.json` → `{id: 9, colour: "Brown"}`

### 线索 3：等价 SQL
```sql
SELECT c.colour
FROM superhero s JOIN colour c ON s.eye_colour_id = c.id
WHERE s.full_name = 'Karen Beecher-Duncan';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **eye colour** | **Brown** |
| superhero_name | Bumblebee |
| eye_colour_id | 9 |
