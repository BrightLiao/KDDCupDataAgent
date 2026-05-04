# Task 292 — 推理过程

## 问题
> For the constructor which got the highest point in the race No. 9, what is its introduction website?

## 结论
**最终答案：http://en.wikipedia.org/wiki/Red_Bull_Racing**

> 在 `constructorResults` 中按 `raceId = 9` 取 `points` 最高的车队，再到 `constructors` 表查其 `url` 字段。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **范围约束**：`raceId = 9`（race No. 9）
2. **聚合约束**：在该比赛中 `points` 最高的车队
3. **待求**：该车队的 introduction website（即 `constructors.url`）

### Step 1：盘点可用资源
```
context/
├── knowledge.md                       ← 数据字典 / Schema
├── db/constructorResults.db           ← 事实表：每场比赛各车队得分
└── json/constructors.json             ← 维度表：车队主数据（含 url）
```
分工：DB 为事实表（聚合点数），JSON 为维度表（解码 constructorId → name/url）。

### Step 2：先看 `knowledge.md`
关键信息：
- **Constructors**：由 `constructorId` 标识，含 `name`、`nationality`、`url`。
- **points**：车队/车手在比赛中的得分。
- Use Case 5 明确：`SELECT MAX(points) FROM constructorResults WHERE raceId = [...]`，正好对应本题。

### Step 3：在 constructorResults 中定位 raceId=9 的最高分车队
```sql
SELECT constructorId, points
FROM constructorResults
WHERE raceId = 9
ORDER BY points DESC
LIMIT 1;
```
结果：`constructorId = 9, points = 18.0`（其他车队最多 7.0，唯一最高）。

### Step 4：到 constructors.json 查该车队的 url
```sh
jq '.records[] | select(.constructorId == 9)' constructors.json
```
得到：
```json
{
  "constructorId": 9,
  "constructorRef": "red_bull",
  "name": "Red Bull",
  "nationality": "Austrian",
  "url": "http://en.wikipedia.org/wiki/Red_Bull_Racing"
}
```

### 核心思路
> 事实表（DB）按 raceId 取 max(points) 选车队，再用 constructorId 在维度表（JSON）查 url。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，快速摸清 context 文件分工 |
| 读 knowledge.md / task.json | `Read` | 文件小，一次性看全 |
| 看 SQLite 表结构 | `sqlite3 ... ".schema"` | DB 原生工具，最稳 |
| 查询 raceId=9 排序 | `sqlite3 ... ORDER BY points DESC` | 一条 SQL 直接得出唯一冠军 |
| 解析 JSON 维度表 | `jq '.records[] \| select(...)'` | 自动允许且专为 JSON 设计 |

### 方法层面
1. **Schema 先于数据**：先看 knowledge.md 与表结构再下查询。
2. **事实/维度分工**：DB 装事件级 points；JSON 装稳定主数据 url，分工清晰。
3. **直接命中字段**：knowledge.md 已经给出 `constructors.url` 是车队介绍网址，无需散文搜索。

### 一句话总结
> 一条 SQL + 一个 jq select，事实-维度两级查到底。

---

## 推理线索

### 线索 1：raceId=9 各车队得分
来源：`context/db/constructorResults.db`（表 `constructorResults`）
- `raceId=9` 共 10 个车队记录
- 最高分：`constructorId=9, points=18.0`
- 第二名：`constructorId=23, points=7.0`（差距明显，唯一最高）
→ 冠军车队 ID = 9

### 线索 2：constructorId=9 的元数据
来源：`context/json/constructors.json`
- `name = "Red Bull"`
- `nationality = "Austrian"`
- `url = "http://en.wikipedia.org/wiki/Red_Bull_Racing"`
→ 即所求 introduction website

---

## 等价 SQL（概念上）

```sql
SELECT c.url
FROM constructorResults cr
JOIN constructors c ON c.constructorId = cr.constructorId
WHERE cr.raceId = 9
ORDER BY cr.points DESC
LIMIT 1;
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| raceId | 9 |
| 最高分 constructorId | 9 |
| 车队名称 | Red Bull |
| points | 18.0 |
| **introduction website (url)** | **http://en.wikipedia.org/wiki/Red_Bull_Racing** |

> 数据来源：`constructorResults.db` + `constructors.json`；最高分唯一，无并列。
