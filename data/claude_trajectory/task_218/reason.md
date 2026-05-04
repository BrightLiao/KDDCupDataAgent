# Task 218 — 推理过程

## 问题
> What is the telephone number for the school with the lowest average score in reading in Fresno Unified?

## 结论
**最终答案：(559) 248-5100**

> 该电话来自 Fresno Unified 学区中阅读 SAT 平均分最低的学校 McLane High（CDSCode = 10621661034214，AvgScrRead = 370）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **学区约束**：District = "Fresno Unified"
2. **指标约束**：satscores 的 `AvgScrRead`（Average Reading Score）取最小值
3. **过滤要求**：`AvgScrRead IS NOT NULL`（满足"有阅读分数的学校"）；并且应排除 District 级聚合行（sname 为空）
4. **待求**：对应学校的 `Phone`

### Step 1：盘点可用资源
```
context/
├── knowledge.md                ← 数据字典 + 指标定义
├── db/satscores.db             ← SAT 分数事实表（含 cds, sname, dname, AvgScrRead, ...）
└── json/schools.json           ← 学校维度表（含 CDSCode, School, District, Phone, ...）
```
分工：satscores 提供 reading 分数 + 学区/学校名；schools.json 提供电话。两者通过 `CDSCode = cds` 关联。

### Step 2：先看 `knowledge.md`
关键信息：
- `Schools` 实体含 `CDSCode`、`School Name`、`District`、`Phone` 等字段。
- `SAT Scores` 实体含 `Average Scores in Math, Reading, Writing`，对应 satscores 表的 `AvgScrRead`。
- 没有为 reading 设定额外的过滤阈值，只需按值取最小。

### Step 3：在 satscores 中筛 Fresno Unified 并取 AvgScrRead 最小行
```sql
SELECT cds, sname, dname, AvgScrRead
FROM satscores
WHERE dname = 'Fresno Unified' AND AvgScrRead IS NOT NULL
ORDER BY AvgScrRead ASC
LIMIT 5;
```
返回前 5：
| cds | sname | AvgScrRead |
|---|---|---|
| 10621661034214 | McLane High | 370 |
| 10621661035831 | Roosevelt High | 377 |
| 10621661030295 | Erma Duncan Polytechnical High | 396 |
| 10621661030675 | Sunnyside High | 403 |
| 10621661032911 | Herbert Hoover High | 415 |

最低：**McLane High（cds = 10621661034214，AvgScrRead = 370）**。
注意：还有一行 `cds = 10621660000000, sname = NULL, AvgScrRead = 435`，sname 为空，是 District 级聚合行，应排除（题目问"the school"）；即便不排除，它的分数也比 McLane High 高，对答案无影响。

### Step 4：在 schools.json 中按 CDSCode 取 Phone
```sh
jq -r '.records[] | select(.CDSCode == "10621661034214") | {School, District, Phone}' \
   context/json/schools.json
```
输出：`School = "McLane High", District = "Fresno Unified", Phone = "(559) 248-5100"`。学校名与学区匹配，电话即为答案。

### 核心思路
> 在 satscores 内按 `dname='Fresno Unified'` 排序拿到最低 AvgScrRead 学校的 cds，再到 schools.json 里 ID 反查 Phone。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，能直接看清两个数据源的位置 |
| 读 knowledge.md | `Read` | 文件较小，一次看全 schema 与指标定义 |
| 查 SAT 分数最小值 | `sqlite3` | satscores 在 SQLite 里，SQL ORDER BY + LIMIT 最直接 |
| 在 25MB 学校 JSON 里按 CDSCode 反查 | `jq` | 自动允许，专为 JSON 设计，不必加载全部到上下文 |

### 方法层面
1. **分层阅读**：先读 knowledge.md 把 schema 心智模型建好，再下数据查询。
2. **针对不同载体用不同读法**：satscores 用 SQL；schools.json 用 jq 按主键反查。
3. **两表关联用 ID 桥接**：satscores.cds = schools.CDSCode 是显式外键，先在 satscores 里筛出最小值的 cds，再去 schools.json 反查 Phone。

### 一句话总结
> SQL 找极值，jq 按主键取字段，两步串起来即可。

---

## 推理线索

### 线索 1：knowledge.md 给出 Schools 与 SAT Scores 的字段定义
来源：`context/knowledge.md`
- Schools 表含 `CDSCode`、`District`、`Phone`。
- SAT Scores 中 `Average Scores in Math, Reading, Writing` 对应 satscores 的 `AvgScrRead/AvgScrMath/AvgScrWrite`。
→ 题目里 "average score in reading" → satscores.AvgScrRead；"telephone number" → schools.Phone。

### 线索 2：satscores 中 Fresno Unified 的 AvgScrRead 极小值
来源：`context/db/satscores.db`
```sql
SELECT cds, sname, AvgScrRead FROM satscores
WHERE dname = 'Fresno Unified' AND AvgScrRead IS NOT NULL
ORDER BY AvgScrRead ASC LIMIT 1;
-- → 10621661034214 | McLane High | 370
```
→ 目标学校是 McLane High（CDSCode = 10621661034214）。

### 线索 3：schools.json 里 McLane High 的 Phone
来源：`context/json/schools.json`
- `CDSCode = "10621661034214"` 的记录：`School = "McLane High"`, `District = "Fresno Unified"`, `Phone = "(559) 248-5100"`。
→ 答案 Phone = `(559) 248-5100`。

---

## 等价 SQL（若将 schools.json 也视作 schools 表）
```sql
SELECT s.Phone
FROM schools s
JOIN satscores t ON t.cds = s.CDSCode
WHERE t.dname = 'Fresno Unified'
  AND t.AvgScrRead IS NOT NULL
ORDER BY t.AvgScrRead ASC
LIMIT 1;
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| Phone | **(559) 248-5100** |
| School | McLane High |
| District | Fresno Unified |
| CDSCode | 10621661034214 |
| AvgScrRead | 370（Fresno Unified 学区内最低） |

> 数据来源：satscores.db（取最低阅读均分的 cds）与 schools.json（按 CDSCode 反查 Phone）。
