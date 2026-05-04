# Task 303 — 推理过程

## 问题
> Among all European Grand Prix races, what is the percentage of the races were hosted in Germany?

## 结论
**最终答案：52.17391304347826（%）**

> 共 23 场名称为 "European Grand Prix" 的比赛，其中 12 场举办在德国（circuitId = 20，Nürburgring），12/23 ≈ 52.17%。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **比赛筛选**：`races.name = 'European Grand Prix'`
2. **国别筛选**：举办地国家 = `Germany`（来自 circuits 表）
3. **指标**：`COUNT(德国举办场次) / COUNT(总场次) * 100`，输出百分比数值
4. **待求**：一个百分数（real）

### Step 1：盘点可用资源
```
context/
├── knowledge.md            ← Formula_1 数据字典与 KPI 公式
├── db/races.db             ← 仅有 races 表（事实表）
└── json/circuits.json      ← circuits 维度表（含 country 字段）
```
分工：races.db 提供 raceId↔circuitId↔name 关系；circuits.json 提供 circuitId↔country 关系。

### Step 2：先看 `knowledge.md`
关键信息：
- `Races`：以 `raceId` 唯一标识，含 `year`、`round`、`name`、`date`，外键 `circuitId`。
- `Circuits`：以 `circuitId` 唯一标识，含 `name`、`location`、`country`。
- 例 3 已示范用 `races.name = 'XX Grand Prix'` 做赛事过滤、`circuits` join 取地理信息。
- 没有针对"European Grand Prix" 的特殊语义定义，按字面解释即可。

### Step 3：定位"European Grand Prix"赛事
`races` 表中赛事名直接命中：
```sql
SELECT DISTINCT name FROM races WHERE name LIKE '%European%';
-- → 'European Grand Prix'
```
共 23 条（1983–2016 年间，详见线索 1）。

### Step 4：识别德国境内的 circuitId
`circuits.json` 中 `country = 'Germany'` 的圆环：
- circuitId = 9  Hockenheimring（注：附录显示为 10，实际数据见 jq 输出）
- circuitId = 20 Nürburgring
- circuitId = 61 AVUS

European GP 出现过的 circuitId 集合：{12, 20, 26, 31, 38, 73}
对应国家：Spain、Germany、Spain、UK、UK、Azerbaijan
其中只有 circuitId = 20（Nürburgring）在德国。

### Step 5：统计与计算
- 总场次：23
- 德国举办：12
- 比例：12 / 23 × 100 = 52.17391304347826

### 核心思路
> 用 races.name 把"European Grand Prix"的全部场次拉出来，与 circuits 维度按 circuitId 关联，计算 country = 'Germany' 的占比。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，迅速摸清文件分工 |
| 读 knowledge.md | `Read` | 文档不大，一次看全 Schema 语义 |
| 查 races 表 | `sqlite3` | 原生 SQL 表达 join/计数最直接 |
| 查 circuits.json | `jq` | JSON 维度表，jq 过滤字段最方便，不需要 python |

### 方法层面
1. **分层阅读**：先 knowledge.md 理解 Schema，再 sqlite3/jq 验证字段值
2. **先抓事实表再连维度**：先在 races 表锁定 23 条候选赛事，再用 circuitId 反查国别
3. **用集合判断维度命中**：把 European GP 出现过的 circuitId 列出来，与德国 circuit 列表取交集

### 一句话总结
> 先把目标赛事 raceId 集合圈定，再用 circuitId 反查 circuits 维度判定国别归属。

---

## 推理线索

### 线索 1：23 场 European Grand Prix 的明细
来源：`context/db/races.db` 的 `races` 表
```sql
SELECT raceId, year, circuitId FROM races WHERE name = 'European Grand Prix' ORDER BY year;
```
按 year 列出（截取关键列 year→circuitId）：
- 1983/38, 1984/20, 1985/38, 1993/31, 1994/26, 1995/20, 1996/20, 1997/26,
- 1999/20, 2000/20, 2001/20, 2002/20, 2003/20, 2004/20, 2005/20, 2006/20,
- 2007/20, 2008/12, 2009/12, 2010/12, 2011/12, 2012/12, 2016/73

→ 共 23 行，circuitId = 20 出现 12 次。

### 线索 2：Germany circuit 列表
来源：`context/json/circuits.json`
```sh
jq '.records[] | select(.country == "Germany") | {circuitId, name}' …
```
- circuitId 10 Hockenheimring
- circuitId 20 Nürburgring
- circuitId 61 AVUS

→ European GP 中唯一出现的德国 circuit 为 20（Nürburgring）。

### 线索 3：百分比计算
- 分子：12（circuitId = 20 的 European GP 场次）
- 分母：23（全部 European GP 场次）
- 12 / 23 × 100 = 52.17391304347826

---

## 等价 SQL（若 circuits 也在同库）
```sql
SELECT
  CAST(COUNT(CASE WHEN T1.country = 'Germany' THEN T2.circuitID END) AS REAL) * 100
  / COUNT(T2.circuitId) AS pct
FROM circuits AS T1
INNER JOIN races AS T2 ON T2.circuitId = T1.circuitId
WHERE T2.name = 'European Grand Prix';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| 百分比 | **52.17391304347826** |
| 分子（德国举办场次） | 12 |
| 分母（European GP 总场次） | 23 |
| 唯一命中的德国 circuit | Nürburgring (circuitId = 20) |

> 数据来源：`context/db/races.db`（races 表）+ `context/json/circuits.json`（country 字段）。
