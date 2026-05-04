# Task 415 — 推理过程

## 问题
> What is the constructor reference name of the champion in the 2009 Singapore Grand Prix? Please give its website.

## 结论
**最终答案：constructorRef = `mclaren`，website (url) = `http://en.wikipedia.org/wiki/McLaren`**

> 语义假设：champion = 该场比赛 `positionOrder = 1` 的车队（即车手获得冠军时所在的 constructor）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **赛事约束**：2009 年的 Singapore Grand Prix（新加坡大奖赛）。
2. **目标实体**：该场比赛的 champion（冠军）所在 constructor。
3. **待求**：constructor 的 `constructorRef`（参考名）以及 `url`（官方网址）。

### Step 1：盘点可用资源
```
context/
├── knowledge.md                  ← 数据字典（Formula_1 库的语义层）
├── db/results.db                 ← 仅含 results 表（含 raceId / constructorId / positionOrder）
├── json/constructors.json        ← constructors 维度（constructorId → constructorRef、name、url）
└── doc/races.md                  ← races 维度（散文式描述，含每场比赛的 raceId、年份、circuit）
```
分工：`results.db` = 事实表；`constructors.json` = 维度表；`races.md` = races 维度（散文式，需关键词锚点）；`knowledge.md` = Schema 字典。

### Step 2：先看 `knowledge.md`
关键信息：
- **Constructors** 维度：`constructorId`、`name`、`nationality`、`url`，参考名为 `constructorRef`。
- **Races**：以 `raceId` 标识，含 `year`、`round`、`name`、`date`。
- **Ambiguity Resolution**：`positionOrder` 才是真正的「最终名次」，`position` 仅指网格/资格赛位置。因此 champion 应当用 `positionOrder = 1` 而非 `position = 1`。

### Step 3：定位 2009 Singapore Grand Prix 的 raceId
`races.md` 的相关段落（关键词锚点 "Singapore"）明确写明：
> "the demanding Singapore Grand Prix (Race ID: 14) ... 2009 calendar ... held on September 27, 2009 ... Marina Bay Street Circuit ..."

→ **raceId = 14**。

### Step 4：在 results.db 中找 champion 的 constructorId
```sql
SELECT driverId, constructorId, positionOrder
FROM results
WHERE raceId = 14
ORDER BY positionOrder
LIMIT 5;
```
返回首行：`driverId=1, constructorId=1, positionOrder=1, points=10.0`。
→ **champion 所在 constructorId = 1**。

### Step 5：在 constructors.json 中查 constructorRef 与 url
```sh
jq '.records[] | select(.constructorId == 1)' context/json/constructors.json
```
返回：
```json
{
  "constructorId": 1,
  "constructorRef": "mclaren",
  "name": "McLaren",
  "nationality": "British",
  "url": "http://en.wikipedia.org/wiki/McLaren"
}
```

### 核心思路
> races.md 锚定 `2009 Singapore GP → raceId=14`；results.db 取 `positionOrder=1` 行得 `constructorId=1`；constructors.json 反查得 `constructorRef=mclaren` 与 url。三跳路径：races.md → results.db → constructors.json。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 快速摸清 4 类资源（knowledge / db / json / doc） |
| 读 knowledge.md / task.json | `Read` | 小文件，一次读全 |
| 在散文 races.md 中找特定 race | `Bash: grep -i "singapore"` | 关键词锚点法，避免逐句精读 92KB 散文 |
| 查 results 表 | `sqlite3` | results.db 是 SQLite，直接 SQL 查询 |
| 反查 constructors 维度 | `jq` | JSON 文件用 jq 过滤最直接 |

### 方法层面
1. **分层阅读**：先 knowledge.md 摸 Schema，再到事实表/维度表对号入座。
2. **关键词锚点**：散文里只看 "Singapore" 周围几行，立刻拿到 raceId=14。
3. **Schema 反推**：根据 knowledge.md 的歧义说明，确认 champion 应用 `positionOrder=1` 而非 `position=1`。

### 一句话总结
> 先在散文里锚定 raceId，再让 SQL/jq 接力做 join，是处理「散文维度 + 结构化事实」混合数据集的标准姿势。

---

## 推理线索

### 线索 1：2009 Singapore GP 对应的 raceId
来源：`context/doc/races.md`
- 散文明确写有 "Singapore Grand Prix (Race ID: 14)"、"2009 calendar"、"September 27, 2009"。
→ raceId = 14。

### 线索 2：该场冠军所在 constructor
来源：`context/db/results.db`，表 `results`
- `WHERE raceId=14 ORDER BY positionOrder LIMIT 1` → `constructorId=1`、`positionOrder=1`、`points=10.0`。
- 依据 `knowledge.md` 的 Ambiguity Resolution，`positionOrder` 才是最终名次，故 positionOrder=1 即冠军车队。
→ champion 所在 constructorId = 1。

### 线索 3：constructorId=1 的参考名与官网
来源：`context/json/constructors.json`
- 记录：`constructorRef = "mclaren"`，`name = "McLaren"`，`url = "http://en.wikipedia.org/wiki/McLaren"`。
→ 答案落地。

---

## 等价 SQL（若 constructors / races 表也在同库）
```sql
SELECT C.constructorRef, C.url
FROM results R
JOIN constructors C ON C.constructorId = R.constructorId
JOIN races        Ra ON Ra.raceId      = R.raceId
WHERE Ra.year = 2009
  AND Ra.name = 'Singapore Grand Prix'
  AND R.positionOrder = 1;
```
本任务实际通过「races.md 锚定 raceId=14 → results.db SQL → constructors.json jq」三段式实现等价语义。

---

## 最终答案

| 字段 | 值 |
|---|---|
| constructorRef | **mclaren** |
| url (website) | **http://en.wikipedia.org/wiki/McLaren** |
| 对应 constructorId | 1 |
| 对应 raceId | 14（2009 Singapore Grand Prix） |
| 判定依据 | `positionOrder = 1`（最终名次第一） |
