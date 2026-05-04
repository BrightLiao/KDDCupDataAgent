# Task 261 — 推理过程

## 问题
> Among the superheroes with the super power of "Super Strength", how many of them have a height of over 200cm?

## 结论
**最终答案：56**

> 语义：先用 `superpower.power_name = 'Super Strength'` 锁定 `power_id`，再通过 `hero_power` 取得拥有该超能力的英雄集合（去重），最后在 `superhero` 表中筛选 `height_cm > 200`。计数对象是英雄（hero），故采用 `COUNT(DISTINCT superhero.id)`。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **超能力约束**：power_name = "Super Strength"
2. **身高约束**：height_cm > 200（严格大于，不含等于）
3. **待求**：满足上述两个条件的英雄个数（去重）

### Step 1：盘点可用资源
```
context/
├── knowledge.md                ← 数据字典 / 字段语义 / SQL 示例
├── csv/superhero.csv           ← 英雄主表（含 height_cm）
├── db/hero_power.db            ← 桥接表 hero_power(hero_id, power_id)
└── json/superpower.json        ← 超能力维度表（power_id ↔ power_name）
```
分工：
- 维度查找：`superpower.json` 提供 power_name → power_id 映射
- 桥接：`hero_power.db` 把英雄和超能力关联起来
- 事实属性：`superhero.csv` 的 `height_cm` 字段提供身高过滤依据

### Step 2：先看 `knowledge.md`
关键信息：
- `superhero.height_cm` 单位为厘米，整数；`weight_kg` 为千克
- `hero_power(hero_id, power_id)` 是多对多桥接表
- knowledge.md 的 Use Case 1 给出了模板：`COUNT(hero_power.hero_id) ... INNER JOIN superpower ON hero_power.power_id = superpower.id WHERE superpower.power_name = 'Flight'`
- 题目本质是 Use Case 1 的变体 + 在 superhero 表上加身高过滤

### Step 3：定位 "Super Strength" 的 power_id
通过 `jq` 在 `superpower.json` 中查找：

```sh
jq '.records[] | select(.power_name == "Super Strength")' context/json/superpower.json
# => { "id": 18, "power_name": "Super Strength" }
```

→ `power_id = 18`

### Step 4：取得拥有 Super Strength 的英雄集合
```sh
sqlite3 context/db/hero_power.db \
  "SELECT COUNT(DISTINCT hero_id) FROM hero_power WHERE power_id=18;"
# => 358
```
→ 共有 358 个英雄拥有 Super Strength（已去重）。

### Step 5：与 superhero 表做 join，过滤 height_cm > 200
为避免污染原始 `hero_power.db`，使用 `:memory:` 数据库 + ATTACH，把 `superhero.csv` 临时导入：

```sql
ATTACH DATABASE 'context/db/hero_power.db' AS hp_db;
.mode csv
.import context/csv/superhero.csv superhero
SELECT COUNT(DISTINCT s.id)
FROM superhero s
INNER JOIN hp_db.hero_power hp
  ON CAST(s.id AS INTEGER) = hp.hero_id
WHERE hp.power_id = 18
  AND CAST(s.height_cm AS INTEGER) > 200;
-- => 56
```

→ **答案 = 56**

### 核心思路
> 三表协同：JSON 维度表（找 power_id）→ SQLite 桥接表（找拥有该超能力的英雄）→ CSV 事实表（按身高过滤）。最终对 superhero.id 做 DISTINCT 计数即可。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，最快 |
| 读 `knowledge.md`、`task.json` | `Read` | 文件小，一次看全 |
| 看 `superhero.csv` 表头 | `head -3` + `wc -l` | 仅看形状无需载入全文 |
| 查 SQLite 桥接表 | `sqlite3` | 表结构清晰，SQL 直查最直接 |
| 在 `superpower.json` 查 power_id | `jq` | 自动允许，专为 JSON 设计 |
| 跨 CSV + DB 连接 | `sqlite3 :memory: + ATTACH + .import` | 用 SQL 表达 join 比 awk 更直观 |

### 方法层面
1. **以 Schema 为中心反推**：先用 knowledge.md 建立"维度表 — 桥接表 — 事实表"心智模型，再决定每张表只查哪一列
2. **维度先行**：先把字符串 power_name 转成 power_id 这个数字键，避免后续 JOIN 时反复字符串匹配
3. **隔离副作用**：用 `:memory:` 数据库 + ATTACH，避免 `.import` 污染原始 `hero_power.db`
4. **DISTINCT 防重复**：题目计数对象是英雄而非"英雄-能力"行；务必 `COUNT(DISTINCT superhero.id)`

### 一句话总结
> JSON 找键、SQLite 找关联、CSV 找属性；DISTINCT 做最后一道闸门。

---

## 推理线索

### 线索 1：power_name → power_id
来源：`context/json/superpower.json`
- `{ "id": 18, "power_name": "Super Strength" }`
→ "Super Strength" 在数据集中的 `power_id` 是 **18**

### 线索 2：拥有 Super Strength 的英雄集合
来源：`context/db/hero_power.db`
- `SELECT COUNT(DISTINCT hero_id) FROM hero_power WHERE power_id=18` → **358**
→ 共 358 个英雄拥有此超能力（去重后），构成候选集

### 线索 3：身高过滤
来源：`context/csv/superhero.csv`（字段 `height_cm`，整数厘米；表头第 11 列）
- 与候选集 hash join 后，筛选 `height_cm > 200`
- `SELECT COUNT(DISTINCT s.id) ... WHERE hp.power_id=18 AND s.height_cm > 200` → **56**
→ 最终答案 56

### 线索 4：与 knowledge.md Use Case 1 结构对齐
来源：`context/knowledge.md` Section 5 Example 1
- 模板：`COUNT(hero_power.hero_id) FROM hero_power INNER JOIN superpower ON hero_power.power_id = superpower.id WHERE superpower.power_name = 'Flight'`
- 本题在此基础上多一层 superhero 表 + 身高谓词
→ 验证了 join 路径无误

---

## 等价 SQL

```sql
SELECT COUNT(DISTINCT T1.id)
FROM superhero AS T1
INNER JOIN hero_power AS T2 ON T1.id = T2.hero_id
INNER JOIN superpower AS T3 ON T2.power_id = T3.id
WHERE T3.power_name = 'Super Strength'
  AND T1.height_cm > 200;
```

注：gold.csv 的列名为 `COUNT(T1.id)`，对应将 superhero 别名为 T1 的写法。本数据集中拥有 Super Strength 的英雄在 hero_power 中无重复行，因此 `COUNT(T1.id)` 与 `COUNT(DISTINCT T1.id)` 数值一致，均为 56。

---

## 最终答案

| 字段 | 值 |
|---|---|
| COUNT(T1.id) | **56** |
| 候选英雄总数（拥有 Super Strength） | 358 |
| 身高阈值 | > 200 cm |
| Super Strength 的 power_id | 18 |

> 数据来源：`superpower.json`（power_id 映射）、`hero_power.db`（英雄-能力关联）、`superhero.csv`（身高字段）。
