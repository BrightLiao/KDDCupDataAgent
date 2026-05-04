# Task 64 — 推理过程

## 问题
> Please list all the superpowers of 3-D Man.

## 结论
**最终答案：4 项 superpower**

| power_name |
|---|
| Agility |
| Super Strength |
| Stamina |
| Super Speed |

---

## 整体思考过程（Meta-Reasoning）

### Step 0：约束
1. 实体：superhero "3-D Man"
2. 待求：他的所有 superpower 名

### Step 1：盘点
```
context/
├── knowledge.md
├── csv/hero_power.csv      ← M:N 关联表（hero_id ↔ power_id）
├── csv/superpower.csv      ← 维度（power_id → power_name）
└── json/superhero.json     ← 维度（id → superhero_name）
```

### Step 2-4：三表 join
1. `superhero.json` 找 "3-D Man" → id=1
2. `hero_power.csv` 取所有 hero_id=1 的 power_id
3. `superpower.csv` 反查 power_id → power_name

```sh
awk -F',' -v hid=1 'NR==FNR{gsub(/\r/,""); if($1==hid) p[$2]=1; next}
                    FNR==1{next}
                    {gsub(/\r/,""); if($1 in p) print $2}' \
   context/csv/hero_power.csv context/csv/superpower.csv
```
→ Agility / Super Strength / Stamina / Super Speed

### 核心思路
> **superhero name → id → M:N 关联表 → power name 反查。**

---

## 阅读文档的方法与工具

| 场景 | 工具 |
|---|---|
| JSON 实体反查 | `jq 'select(.superhero_name == ...)'` |
| 双 CSV hash join | `awk` 双文件模式 |
| CRLF 处理 | `gsub(/\r/, "")` |

---

## 推理线索

### 线索 1：3-D Man 的 hero_id
来源：`superhero.json`
```json
{ "id": 1, "superhero_name": "3-D Man" }
```

### 线索 2：M:N 关联
来源：`hero_power.csv` —— `hero_id, power_id`，hero_id=1 共 4 行

### 线索 3：power 名字反查
来源：`superpower.csv` —— `id, power_name`

### 线索 4：等价 SQL
```sql
SELECT sp.power_name
FROM hero_power hp
JOIN superhero sh ON hp.hero_id = sh.id
JOIN superpower sp ON hp.power_id = sp.id
WHERE sh.superhero_name = '3-D Man';
```

---

## 最终答案

| power_name |
|---|
| Agility |
| Super Strength |
| Stamina |
| Super Speed |

> 共 **4 项**。
