# Task 287 — 推理过程

## 问题
> Identify the gender of the superhero who has the ability of Phoenix Force.

## 结论
**最终答案：Female**

> 拥有 "Phoenix Force" 能力的超级英雄是 Phoenix（Jean Grey-Summers，hero id=534），其 `gender_id=2`，对应 `gender.gender = 'Female'`。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **能力过滤**：`superpower.power_name = 'Phoenix Force'`
2. **目标实体**：拥有该能力的超级英雄
3. **待求**：该英雄对应的 `gender.gender` 文本值

### Step 1：盘点可用资源
```
context/
├── knowledge.md              ← 数据字典 + 示例 SQL
├── csv/hero_power.csv        ← 多对多关联表 (hero_id, power_id)
├── json/superpower.json      ← 维度表 (id, power_name)
├── json/gender.json          ← 维度表 (id, gender)
└── db/superhero.db           ← 主事实表 superhero（含 gender_id）
```
分工：`hero_power.csv` 作为桥接表，`superpower.json` 用来定位 power_id，`superhero.db` 取出 hero 的 gender_id，`gender.json` 把 id 翻译成文本。

### Step 2：先看 `knowledge.md`
关键信息：
- Superhero 表通过 `gender_id` 引用 `gender` 表。
- `power_name` 用于过滤超能力（Use Case 1 已给出 `hero_power INNER JOIN superpower` 的标准范式）。
- 题目仅一条能力过滤条件，不涉及阈值或并集场景。

### Step 3：定位 power_id
在 `superpower.json` 中查 `power_name == "Phoenix Force"`，得 `id = 163`。

### Step 4：查桥接表得 hero_id
在 `hero_power.csv` 中筛选 `power_id == 163`，命中唯一一行：`hero_id = 534`。

### Step 5：在 `superhero` 表中查该 hero 的 gender_id
`SELECT id, superhero_name, full_name, gender_id FROM superhero WHERE id=534;`
结果：`534 | Phoenix | Jean Grey-Summers | 2`。

### Step 6：把 gender_id 翻译成文本
`gender.json` 中 `id=2 → "Female"`。

### 核心思路
> superpower(name→id) → hero_power(power_id→hero_id) → superhero(hero_id→gender_id) → gender(id→text)，四跳一线下来即可。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，先掌握资源全貌 |
| 读 knowledge.md / 小 JSON | `Read` | 文件小，直接全量读取最稳妥 |
| 在 superpower.json 找特定 name | `jq` | JSON 专用，写 select 一行搞定 |
| 在 hero_power.csv 过滤 power_id | `grep ",163"` | 只有两列，直接锚定行尾即可 |
| 在 superhero.db 反查 hero | `sqlite3` | 主表是 SQLite，直接 SQL 最简洁 |

### 方法层面
1. **先 Schema 后数据**：先用 knowledge.md 锁定 4 张表的连接路径，再去逐表查询。
2. **维度表先翻译成 ID**：把人类可读的 `power_name`、`gender` 文字先转成数值键，避免在事实表里做字符串匹配。
3. **每跳都核对结果是否唯一**：`Phoenix Force` 仅 1 个 power_id；`power_id=163` 仅 1 个 hero_id；不存在歧义。

### 一句话总结
> 把"按名字找能力 → 按能力找英雄 → 按英雄找性别"拆成 4 步外键 lookup，一表一跳。

---

## 推理线索

### 线索 1：Phoenix Force 对应的 power_id
来源：`context/json/superpower.json`
- `jq` 查 `power_name == "Phoenix Force"` 返回唯一记录 `{ "id": 163, "power_name": "Phoenix Force" }`。
→ power_id = 163。

### 线索 2：拥有该能力的英雄 ID
来源：`context/csv/hero_power.csv`
- `grep ",163"` 命中唯一一行 `534,163`。
→ hero_id = 534（且全表仅此 1 个英雄拥有该能力）。

### 线索 3：英雄 534 的身份与 gender_id
来源：`context/db/superhero.db`
- `SELECT ... FROM superhero WHERE id=534;` → `Phoenix | Jean Grey-Summers | gender_id=2`。
→ Phoenix 的 gender_id = 2。

### 线索 4：gender_id 到文本的映射
来源：`context/json/gender.json`
- `id=1 Male, id=2 Female, id=3 N/A`。
→ gender_id=2 → **Female**。

---

## 等价 SQL

```sql
SELECT g.gender
FROM superhero s
JOIN hero_power hp ON hp.hero_id = s.id
JOIN superpower sp ON sp.id = hp.power_id
JOIN gender g     ON g.id = s.gender_id
WHERE sp.power_name = 'Phoenix Force';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| gender | **Female** |
| superhero_name | Phoenix |
| full_name | Jean Grey-Summers |
| hero_id | 534 |
| power_id | 163 |

> 数据来源：`superpower.json`（power_id=163）→ `hero_power.csv`（hero_id=534）→ `superhero.db`（gender_id=2）→ `gender.json`（2 = Female）。
