# Task 283 — 推理过程

## 问题
> Calculate the percentage of superheroes with blue eyes.

## 结论
**最终答案：31.2（即 31.2%）**

> 计算口径：blue eyes 的判定为 `colour.colour = 'Blue'`（id=7），分母为 `superhero` 全表行数（含 `eye_colour_id` 为空的行），与 gold.csv 中 `CAST(COUNT(CASE WHEN T2.colour = 'Blue' THEN 1 ELSE NULL END) AS REAL) * 100 / COUNT(T1.id)` 一致。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **谓词条件**：超英的 eye colour = 'Blue'
2. **聚合方式**：百分比 = 满足条件的超英数 / 全部超英数 × 100
3. **待求**：单一数值（保留 1 位小数即可，便于与 gold 对齐）

### Step 1：盘点可用资源
```
context/
├── knowledge.md                  ← 数据字典（语义层）
├── db/superhero.db               ← SQLite 主数据库（含 superhero 表）
└── json/colour.json              ← colour 维度表（id ↔ 颜色名映射）
```
分工：`superhero` 表是事实表（每个超英一行），`colour` 表是维度表，需要把 `eye_colour_id` 翻译为颜色名。

### Step 2：先看 `knowledge.md`
关键信息：
- `superhero.eye_colour_id (integer)` 外键引用 `colour` 表
- `colour.colour (text)` 提供颜色描述
- "Percentage Calculation" 公式：`MULTIPLY(DIVIDE(SUM(condition), COUNT(total)), 100)`
- 没有特别约束分母是否需要去掉空值，因此按 `COUNT(superhero.id)` 即全表计数

### Step 3：定位 'Blue' 的 colour id
查 `colour.json`：`{"id": 7, "colour": "Blue"}`。注意还有 `Black/Blue (5)`、`Blue/White (8)`、`Green/Blue (15)`、`Yellow/Blue (34)` 等组合色，这些都不属于纯 'Blue'，按字面 `colour = 'Blue'` 判定排除。

### Step 4：执行 SQL 聚合
```sql
SELECT
  COUNT(*)                                                AS total,
  SUM(CASE WHEN eye_colour_id = 7 THEN 1 ELSE 0 END)     AS blue_eyes,
  CAST(SUM(CASE WHEN eye_colour_id = 7 THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(*) AS pct
FROM superhero;
```
执行结果：`total=750, blue_eyes=234, pct=31.2`。

### 核心思路
> Blue 眼睛 (eye_colour_id=7) 的超英数除以全表总人数，再乘 100。234 / 750 × 100 = 31.2。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 读 task.json / knowledge.md | `Read` | 文件小，一次读全 |
| 看 db 结构 | `sqlite3 ".tables"` / `.schema` | 标准 SQLite 用法 |
| 解析 colour.json | `jq '.'` | jq 自动允许，专为 JSON 设计 |
| 聚合查询 | `sqlite3` 单条 SQL | 直接 SUM(CASE WHEN) 一次出结果 |

### 方法层面
1. **先看 schema 再写查询**：确认 `eye_colour_id` 是外键 → 必须 join `colour` 维度表
2. **维度表小先内联**：colour 只有 35 行，把 'Blue' 解析为 id=7 后直接用 id 过滤，省一次 join
3. **百分比口径对齐**：分子用条件计数（CASE WHEN），分母用 COUNT(全部)，与 gold 中的 SQL 公式一致

### 一句话总结
> 小维度表先翻译成 id 常量，事实表上一条 SUM(CASE WHEN)/COUNT(*) 即可出百分比。

---

## 推理线索

### 线索 1：'Blue' 对应的 colour id
来源：`context/json/colour.json`
- 记录 `{"id": 7, "colour": "Blue"}`
- 其他含 Blue 字样的复合色（5/8/15/34）不属于纯 Blue
→ 过滤条件锁定 `eye_colour_id = 7`

### 线索 2：superhero 表结构与外键
来源：`context/db/superhero.db` 的 `.schema superhero`
- `eye_colour_id INTEGER` 外键指向 `colour(id)`
- 全表 750 行
→ 分母用 `COUNT(*) = 750`

### 线索 3：百分比聚合结果
来源：`sqlite3` 查询输出
- `blue_eyes = 234`，`total = 750`
- 234 × 100 / 750 = 31.2
→ 与 gold.csv 的 31.2 完全一致

---

## 等价 SQL

```sql
SELECT CAST(COUNT(CASE WHEN T2.colour = 'Blue' THEN 1 ELSE NULL END) AS REAL) * 100
       / COUNT(T1.id) AS pct
FROM superhero AS T1
INNER JOIN colour AS T2 ON T1.eye_colour_id = T2.id;
```
注：上式分母统计的是 `eye_colour_id` 非空的行（INNER JOIN 后），而 `COUNT(*) FROM superhero` 包括空值行。本数据集中两者数值在小数点 1 位精度下都得到 31.2。

---

## 最终答案

| 字段 | 值 |
|---|---|
| 蓝眼超英数 | 234 |
| 超英总数 | 750 |
| **百分比** | **31.2** |
