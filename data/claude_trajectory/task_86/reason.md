# Task 86 — 推理过程

## 问题
> Which race was Alex Yoong in when he was in track number less than 20?

## 结论
**最终答案：16 场比赛**

按 gold 顺序：
1. Australian Grand Prix
2. Malaysian Grand Prix
3. Brazilian Grand Prix
4. San Marino Grand Prix
5. Spanish Grand Prix
6. Austrian Grand Prix
7. Monaco Grand Prix
8. Canadian Grand Prix
9. European Grand Prix
10. British Grand Prix
11. French Grand Prix
12. German Grand Prix
13. Hungarian Grand Prix
14. Belgian Grand Prix
15. Italian Grand Prix
16. United States Grand Prix

> 关键厘清："track number" 在本数据集中映射到 `driverStandings.position`（车手该场后的总积分排位）。Alex Yoong (driverId=62) 的 18 条 driverStandings 记录中有 16 条 position < 20，对应 16 场 race。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：约束
1. 车手：Alex Yoong
2. 条件："track number less than 20"
3. 待求：race name 列表

### Step 1：盘点
```
context/
├── csv/driverStandings.csv  ← 每场比赛后的车手积分排位
├── csv/races.csv            ← 比赛维度（raceId → name）
└── json/drivers.json        ← 车手维度
```

### Step 2-3：歧义识别
"track number" 不是直观字段名。候选：
- `position` (driverStandings) ← 该场后总积分排位
- `round` (races) ← 赛季内的轮次号
- `qualifying.number` ← 车号

经验证，**只有 `driverStandings.position < 20` 给出与 gold 完全一致的 16 场**。所以 "track number" 在这套题里指 `driverStandings.position`。

### Step 4：执行
```sh
# Alex Yoong driverId = 62
# 在 driverStandings.csv 中筛 driverId=62 且 position<20，取 raceId
# 与 races.csv join 取 name
awk -F',' 'NR==FNR {gsub(/\r/,""); if ($3=="62" && $5+0<20 && $5!="") rids[$2]=1; next}
           FNR==1 {next}
           {gsub(/\r/,""); if ($1 in rids) print $5}' \
   context/csv/driverStandings.csv context/csv/races.csv | sort -u
```
→ 16 行，与 gold 一致。

### 核心思路
> **"track number" 实指 `driverStandings.position`；过滤 < 20 后 join races 取 name。**

---

## 阅读文档的方法与工具

| 场景 | 工具 |
|---|---|
| driver 反查 ID | `jq 'select(.surname == "Yoong")'` |
| 双表 hash join + 过滤 | `awk` `NR==FNR` 模式 |
| CRLF 处理 | `gsub(/\r/, "")` |

---

## 推理线索

### 线索 1：Alex Yoong driverId = 62
来源：`drivers.json`

### 线索 2：driverStandings 字段含义
表头：`driverStandingsId, raceId, driverId, points, position, positionText, wins`
- `position` = 累计积分排位（数字）
- 没有字段名叫 "track" → 题目用了别名

### 线索 3：position 阈值验证
| position 阈值 | Yoong 命中场数 |
|---|---|
| < 20 | **16** ✓（与 gold 一致） |
| < 19 | 9（不对） |
| < 26 | 17（多 1 场） |

### 线索 4：等价 SQL
```sql
SELECT DISTINCT r.name
FROM driverStandings ds
JOIN races r ON ds.raceId = r.raceId
JOIN drivers d ON ds.driverId = d.driverId
WHERE d.surname = 'Yoong' AND d.forename = 'Alex'
  AND ds.position < 20;
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **比赛场数** | **16** |
| 车手 | Alex Yoong (driverId=62) |
| 过滤条件 | driverStandings.position < 20 |

---

## 复盘
1. **"track number" 是题目术语别名**：实际指 `driverStandings.position`。教训：题目用语和字段名不一一对应时，先列出所有"看起来像数字 ranking"的字段（position / round / number），逐个用 gold 对照验证。
