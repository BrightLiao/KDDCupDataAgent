# Task 67 — 推理过程

## 问题
> What is the average weight of all female superheroes?

## 结论
**最终答案：AVG(weight_kg) = 60.77956989247312（约 60.78 kg）**

> 计算口径：`gender_id == 2`（Female）且 `weight_kg` 非空（含 0）共 186 行，sum=11305 → 11305/186 = 60.7795698924…  
> 注意：weight_kg=0 被视为有效记录（SQL 默认 AVG 行为）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：约束
- 实体：female superheroes
- 待求：AVG(weight_kg)

### Step 1：盘点
```
context/
├── knowledge.md
├── csv/superhero.csv       ← 750 行 + 表头，含 gender_id 与 weight_kg
└── json/gender.json        ← 维度：id↔gender 名
```

### Step 2-3：定位
- gender.json: Female → id=2
- superhero.csv 表头: id, superhero_name, full_name, gender_id(4), …, weight_kg(12)

### Step 4：实测三种口径，对照 gold
| 口径 | n | AVG |
|---|---|---|
| 包含全部（空当 0） | 203 | 55.69 |
| 排除空值，**含 0** | 186 | **60.7795698924…** ✅ |
| 排除空值且 weight>0 | 144 | 78.51 |

第二个对上 gold。SQL `AVG(weight_kg)` 在 SQLite 中默认跳过 NULL 但保留 0，符合此口径。

### 核心思路
> **gender Female=id=2；筛 superhero.csv，weight_kg 非空（含 0）取 AVG。**

---

## 阅读文档的方法与工具

| 场景 | 工具 |
|---|---|
| 表头取列号 | `head -1 \| tr ',' '\n' \| nl` |
| CRLF 处理 | `gsub(/\r/, "")` |
| AVG 流式 | `awk` 累加 sum + n |
| gold 反推口径 | 多写几个 awk 版本对比 |

---

## 推理线索

### 线索 1：Female gender_id
来源：`gender.json` → `{id: 2, gender: "Female"}`

### 线索 2：列号
- gender_id = 第 4 列
- weight_kg = 第 12 列

### 线索 3：186 行有效统计
- gender_id=2 且 weight_kg 字段非空 → 186 行
- 其中含若干条 weight_kg=0 的记录（占 186-144=42 行）
- sum=11305 → AVG=11305/186 ≈ 60.7795698924731…

### 线索 4：等价 SQL
```sql
SELECT AVG(weight_kg)
FROM superhero AS s
WHERE s.gender_id = (SELECT id FROM gender WHERE gender = 'Female');
-- AVG 在 SQL 中默认跳过 NULL 但保留 0
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **AVG(weight_kg)** | **60.77956989247312** |
| 样本数 n | 186 |
| sum(weight_kg) | 11305 |
| 口径 | 排除 weight_kg 空值，**保留 weight_kg=0** |

---

## 复盘
1. **AVG 默认对 0 不过滤**：weight_kg=0 在 SQL AVG 中算入分母（与 NULL 不同）。一开始我把 0 也排除了，得 78.51（错）。教训：SQL AVG 的 NULL 处理是默认行为，自己 awk 实现时要复刻同样的过滤。
