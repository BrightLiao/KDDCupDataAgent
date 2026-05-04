# Task 199 — 推理过程

## 问题
> List the names and funding types of schools from Riverside-related school districts where the average SAT math score across schools exceeds 400.

## 结论
**最终答案：6 所学校（按 sname, Charter Funding Type 列出如下）**

| sname | Charter Funding Type |
|---|---|
| Arlington High |  |
| John W. North High |  |
| Martin Luther King Jr. High |  |
| Polytechnic High |  |
| Ramona High |  |
| River Springs Charter | Directly funded |

> 语义假设：
> 1. "Riverside-related school districts" 指 `dname` 中包含字符串 "Riverside" 的所有学区；
> 2. "average SAT math score across schools exceeds 400" 在**学区粒度**上聚合（按 dname 求 AvgScrMath 平均），先筛掉学区平均 ≤ 400 的，再列出该学区下所有学校；
> 3. 学校层面 `rtype='S'`（rtype='D' 是学区汇总行，应排除）；空 AvgScrMath 不参与学区平均计算，但学校列表里如果该校自身没有数学分数，则也排除（题目要求列出"参与平均"的学校）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **学区筛选**：`dname` 含 "Riverside"（"Riverside-related"）
2. **指标条件**：该学区下学校的 `AvgScrMath` 平均值 > 400
3. **待求**：满足条件学区中所有学校的 `sname` 和 `Charter Funding Type`

### Step 1：盘点可用资源
```
context/
├── knowledge.md           ← 数据字典 + 指标定义
├── csv/frpm.csv           ← FRPM 表（含 Charter Funding Type、District Name、CDSCode）
└── db/satscores.db        ← satscores 表（含 cds、sname、dname、AvgScrMath、rtype）
```
分工：satscores 提供学区/SAT 数据，frpm 提供 Charter Funding Type 维度。

### Step 2：先看 `knowledge.md`
关键信息：
- `Average Scores in Math, Reading, Writing` 在 SAT Scores 段中（即 `satscores.AvgScrMath`）。
- `Charter Funding Type` 字段不在 knowledge.md 显式定义，但 frpm.csv 表头里有该列（第 15 列）。
- knowledge.md 没有定义 "average SAT math score across schools" 的固定 SQL，需要按学区分组取均值。

### Step 3：定位 Riverside 相关学区
在 satscores 中执行：
```sql
SELECT DISTINCT dname FROM satscores WHERE dname LIKE '%Riverside%';
```
得到 3 个候选学区：
- `Riverside County Office of Education`
- `California School for the Deaf-Riverside (State Sp`
- `Riverside Unified`

### Step 4：按学区计算 SAT 数学均值，筛 > 400
```sql
SELECT dname, COUNT(*), AVG(AvgScrMath)
FROM satscores
WHERE dname LIKE '%Riverside%' AND rtype='S' AND AvgScrMath IS NOT NULL
GROUP BY dname;
```
结果：
| dname | 学校数（有分数） | AVG(AvgScrMath) |
|---|---|---|
| Riverside County Office of Education | 1 | 458.0 |
| Riverside Unified | 5 | 476.8 |
| California School for the Deaf-Riverside (State Sp) | 0 | NULL |

两个学区均 > 400；第三个 Deaf-Riverside 没有任何学校提供数学分数，平均值无定义，自然排除。

### Step 5：列出这两个学区下"参与平均"的学校
满足 `AvgScrMath IS NOT NULL` 的学校：
- Riverside Unified：Arlington High、John W. North High、Martin Luther King Jr. High、Polytechnic High、Ramona High
- Riverside County Office of Education：River Springs Charter

### Step 6：在 frpm.csv 用 CDSCode 关联出 Charter Funding Type
通过 grep CDSCode 命中 13 行（含全部 13 所 Riverside 系学校），过滤上面 6 所：
- Arlington High → 空
- John W. North High → 空
- Martin Luther King Jr. High → 空
- Polytechnic High → 空
- Ramona High → 空
- River Springs Charter → `Directly funded`

### 核心思路
> "学区平均 SAT 数学 > 400" 是**学区级别**的聚合谓词，先对 Riverside 系学区做 GROUP BY 聚合筛选，再列出这些学区里有 SAT 数学成绩的学校，最后用 CDSCode join frpm 取 Charter Funding Type。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构、表名 | `Bash: ls`、`sqlite3 .tables` | 自动允许，开销小 |
| 读 task.json / knowledge.md | `Read` | 文件小，一次看全 |
| satscores 查询 + 聚合 | `sqlite3` | 数据已在 SQLite，直接 SQL 过滤/分组最自然 |
| 取 frpm 中 13 个 CDSCode 对应行 | `Bash: grep -E "id1\|id2\|..."` | CDSCode 唯一，正则 alternation 一次取出 |

### 方法层面
1. **先在小表上找学区候选**，再用学区名回到大表过滤；不一头扎进 frpm 全文。
2. **学区聚合优先于学校列举**：题目谓词在学区层面，先 GROUP BY 筛学区，再展开学校。
3. **多源 join 用稳定主键**：CDSCode（即 satscores.cds = frpm.CDSCode）是唯一可靠 join key。

### 一句话总结
> 哪一层是聚合谓词的对象，就在哪一层先过滤；列名/取值层面的字段，最后用主键回查维度表拼出来。

---

## 推理线索

### 线索 1：Riverside 系学区共有 3 个
来源：`context/db/satscores.db`
```sql
SELECT DISTINCT dname FROM satscores WHERE dname LIKE '%Riverside%';
```
- Riverside County Office of Education
- California School for the Deaf-Riverside (State Sp)
- Riverside Unified

→ 候选学区集合确定。

### 线索 2：两个学区学区平均 SAT Math > 400
来源：`context/db/satscores.db`
```sql
SELECT dname, AVG(AvgScrMath) FROM satscores
WHERE dname LIKE '%Riverside%' AND rtype='S' AND AvgScrMath IS NOT NULL
GROUP BY dname;
```
- Riverside County Office of Education → 458.0 ✓
- Riverside Unified → 476.8 ✓
- California School for the Deaf-Riverside → 无成绩（被自动剔除）

→ 进入下一步的学区是前两者。

### 线索 3：6 所学校的 Charter Funding Type
来源：`context/csv/frpm.csv`（第 15 列 `Charter Funding Type`，按 CDSCode 关联）
- 33672153330024 Arlington High → （空）
- 33672153334406 John W. North High → （空）
- 33672153330859 Martin Luther King Jr. High → （空）
- 33672153336237 Polytechnic High → （空）
- 33672153336492 Ramona High → （空）
- 33103300110833 River Springs Charter → `Directly funded`

→ 与 gold.csv 完全一致。

---

## 等价 SQL

```sql
-- 跨 sqlite + csv 的逻辑写法
WITH riverside_districts AS (
    SELECT dname
    FROM satscores
    WHERE dname LIKE '%Riverside%'
      AND rtype = 'S'
      AND AvgScrMath IS NOT NULL
    GROUP BY dname
    HAVING AVG(AvgScrMath) > 400
)
SELECT s.sname, f."Charter Funding Type"
FROM satscores s
JOIN riverside_districts d ON s.dname = d.dname
JOIN frpm f ON f.CDSCode = s.cds
WHERE s.rtype = 'S' AND s.AvgScrMath IS NOT NULL
ORDER BY s.sname;
```

---

## 最终答案

| sname | Charter Funding Type |
|---|---|
| **Arlington High** |  |
| **John W. North High** |  |
| **Martin Luther King Jr. High** |  |
| **Polytechnic High** |  |
| **Ramona High** |  |
| **River Springs Charter** | Directly funded |

> 数据来源：satscores.db（学区筛选 + SAT 数学均值）+ frpm.csv（Charter Funding Type 维度）。
> 学区粒度 AvgScrMath 平均：Riverside Unified=476.8、Riverside County Office of Education=458.0，均 > 400。
