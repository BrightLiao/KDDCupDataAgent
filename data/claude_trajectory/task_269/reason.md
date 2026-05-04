# Task 269 — 推理过程

## 问题
> What are the names of the superheroes with the power of death touch?

## 结论
**最终答案：Black Flash, Blackwulf, Hela, Living Tribunal, One-Above-All, Poison Ivy, Spectre**

> 共 7 位超级英雄拥有 "Death Touch" 这一 power（power_id = 37）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **谓词约束**：英雄需拥有名为 "death touch" 的 superpower
2. **待求**：所有满足条件的 `superhero_name`（一组名字）
3. **隐含**：power_name 与 hero 之间通过 `hero_power` 关联表多对多连接

### Step 1：盘点可用资源
```
context/
├── knowledge.md                    ← 数据字典 / 语义层
├── csv/hero_power.csv              ← 关联表（hero_id, power_id），5826 行
├── json/superpower.json            ← 维度表：power_id ↔ power_name
└── db/superhero.db                 ← SQLite，含 superhero 维度表（id, superhero_name, ...）
```
分工：`superpower.json` 解析 power_name → power_id；`hero_power.csv` 做事实关联；`superhero.db` 把 hero_id 映射回名字。

### Step 2：先看 `knowledge.md`
关键信息：
- Superpower 实体仅有 `power_name` 字段
- `power_name` 是英雄"获得性"能力，与 attribute（内在属性）不同
- Use Case 1 给出标准 SQL 模式：`hero_power` INNER JOIN `superpower` 按 `power_name` 过滤
- 维度表分散在三种存储中（json / csv / db），需要跨源 join

### Step 3：定位 power "Death Touch" 的 ID
在 `superpower.json` 中按关键词 "Death" 大小写不敏感搜索：
- `power_id = 37`，`power_name = "Death Touch"`（唯一匹配）

### Step 4：在 `hero_power.csv` 中定位拥有该 power 的 hero_id
对 `hero_power.csv` 抓取 `power_id == 37` 的行，得到 7 个 hero_id：
`105, 116, 331, 424, 518, 539, 637`

### Step 5：通过 SQLite 把 hero_id 映射回 `superhero_name`
对 `superhero.db` 执行 `SELECT id, superhero_name FROM superhero WHERE id IN (...)`，得到 7 个名字。

### 核心思路
> Power name → power_id（json）→ hero_id（csv 关联表）→ superhero_name（sqlite），三跳跨源 join。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，秒看清三种数据源分工 |
| 读 knowledge.md / task.json | `Read` | 小文件，一次读全建立 schema 心智模型 |
| 查 superpower.json | `Bash: jq` | 自动允许，专为 JSON 设计，按关键词过滤一行搞定 |
| 查 hero_power.csv | `Bash: grep` | 5826 行 CSV 不算大，但仍流式过滤；`grep -c` 先确认数量 |
| 查 superhero.db | `Bash: sqlite3` | DB 文件原生工具，IN 子句直接拿名字 |

### 方法层面
1. **分层阅读**（数据字典 → 维度文件 → 关联事实表 → 主体维度表）
2. **针对不同存储用不同读法**：JSON 用 jq、CSV 用 awk/grep、DB 用 sqlite3
3. **Schema 反推检索目标**：先从 knowledge.md 知道需要 power_id 这个枢纽字段，再三跳定位

### 一句话总结
> 跨源 join 时，先在最便宜的维度表（JSON）解析关键词得到 ID，再用 ID 去更大的事实表/SQLite 里 lookup。

---

## 推理线索

### 线索 1：Death Touch 的 power_id
来源：`context/json/superpower.json`
- `jq '.records[] | select(.power_name | test("Death"; "i"))'`
- 唯一命中：`{"id": 37, "power_name": "Death Touch"}`
→ `power_id = 37`

### 线索 2：拥有 power_id = 37 的 hero_id 列表
来源：`context/csv/hero_power.csv`
- `grep ",37" hero_power.csv`（已用 `grep -c` 验证恰好 7 行，无误命中）
- hero_id：`105, 116, 331, 424, 518, 539, 637`
→ 7 位英雄

### 线索 3：hero_id → superhero_name 映射
来源：`context/db/superhero.db`
- `SELECT id, superhero_name FROM superhero WHERE id IN (105,116,331,424,518,539,637)`
- 全部 7 个 ID 都有非空名字
→ 名单：Black Flash, Blackwulf, Hela, Living Tribunal, One-Above-All, Poison Ivy, Spectre

---

## 等价 SQL

```sql
SELECT s.superhero_name
FROM superhero s
INNER JOIN hero_power hp ON s.id = hp.hero_id
INNER JOIN superpower sp ON hp.power_id = sp.id
WHERE sp.power_name = 'Death Touch'
ORDER BY s.superhero_name;
```

---

## 最终答案

| superhero_name |
|---|
| Black Flash |
| Blackwulf |
| Hela |
| Living Tribunal |
| One-Above-All |
| Poison Ivy |
| Spectre |

> 共 7 位。power_name 命名严格匹配 "Death Touch"（superpower.json 中唯一含 "Death" 的条目）。
