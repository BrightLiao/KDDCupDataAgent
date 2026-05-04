# Task 396 — 推理过程

## 问题
> In superheroes with height between 150 to 180, what is the percentage of heroes published by Marvel Comics?

## 结论
**最终答案：54.83870967741935（即 17/31 × 100，约 54.84%）**

> 语义假设：身高范围按 SQL `BETWEEN 150 AND 180` 闭区间理解；分母为 superhero 表中 `height_cm` 落在 [150, 180] 的全部记录数；分子为这些记录中 `publisher_name = 'Marvel Comics'` 的数量。占位值 0.0 / NaN 直接由 BETWEEN 谓词排除（不会落入区间）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **数值过滤**：`height_cm BETWEEN 150 AND 180`
2. **目标度量**：`publisher_name = 'Marvel Comics'` 的占比（按超级英雄计数）
3. **待求**：百分比数值（与 gold 列名一致：`CAST(COUNT(CASE ...) AS REAL) * 100 / COUNT(T1.id)`）

### Step 1：盘点可用资源
```
context/
├── knowledge.md            ← Schema/语义层（superhero、publisher 表结构 + 范例 SQL）
├── json/publisher.json     ← publisher 维度表（id ↔ publisher_name），25 行
└── doc/superhero.md        ← 散文式 superhero 事实表（按 ID 散落 height、publisher 等字段）
```
分工：knowledge.md → 数据字典；publisher.json → publisher 维度；superhero.md → 唯一的事实数据来源（无 csv/db）。

### Step 2：先看 `knowledge.md`
关键信息：
- `superhero.height_cm`（integer，单位 cm）、`superhero.publisher_id` → `publisher.id`。
- `publisher.publisher_name` 即用于过滤的字段。
- 范例 5 的 SQL 模板已经给出 `superhero INNER JOIN publisher ON superhero.publisher_id = publisher.id WHERE publisher.publisher_name = 'Marvel Comics'` 的标准 join 写法。
- `Percentage Calculation: MULTIPLY(DIVIDE(SUM(condition), COUNT(total)), 100)`，与 gold 表头一致。

### Step 3：解析 publisher.json，确认 Marvel 对应 publisher_id
`publisher.json` 中 `id=13 ↔ publisher_name="Marvel Comics"`。后续在 superhero.md 里，凡是「publisher 13 / publisher affiliation … 13」的 ID 都视为 Marvel。

### Step 4：从 `superhero.md` 提取 (id, height_cm) 与 (id, publisher_id)
散文按"章节"组织：
- 行 432–645：「core physical biometrics」段，每位英雄给出 height/weight。
- 行 863–末尾：「publisher affiliation and moral alignment」段，每位英雄给出 publisher 编码。

读取规则：
- 当条目里出现「initially X … updated/adjusted/correct measurement … Y」类「temporal evolution / administrative correction」时，**取修正后的 Y 值**（X 是错误的初始记录，Y 才是入库值）。
- 占位 `0.0` 与 `NaN` 不是合法身高，BETWEEN 直接过滤掉，无需回填散文里的"估计值"（如 Riddler "approximately 185 cm"、Kylo Ren "around 189 cm"、Picard "175 cm" 这类备注是 doc 给出的非官方估计，不属于 height_cm 字段值）。

### Step 5：筛选 height_cm ∈ [150, 180] 的英雄
满足条件的 ID（共 **31** 个）：
26, 47, 72, 74, 104, 144, 161, 169, 177, 235, 278, 346, 350, 354, 520, 549, 552, 561, 568, 594, 607, 608, 649, 656, 661, 713, 726, 739, 743, 749, 752。

### Step 6：在这 31 人里数 publisher_id = 13（Marvel Comics）
逐条核对 publisher 段落，命中 publisher 13 的（共 **17** 个）：
26 Angel Dust, 47 Armor, 104 Black Cat, 161 Captain Marvel, 278 Frigga, 346 Hybrid, 354 Invisible Woman, 549 Purple Man, 552 Quake, 608 Shadowcat, 649 Spider-Woman IV, 661 Storm, 713 Venom II, 726 Vulture, 739 Winter Soldier, 749 X-Man, 752 Yellowjacket II。

### Step 7：计算百分比
`17 / 31 × 100 = 54.83870967741935`，与 gold.csv 完全一致。

### 核心思路
> 把散文式 superhero.md 当成两张窄表（id→height, id→publisher）来抽取，先按身高 BETWEEN 150 AND 180 过滤得 31 人，再数 publisher_id=13 命中 17，最终 17/31×100 即答案。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构、查找章节边界 | `Bash: ls` / `grep -n` | 自动允许，定位章节起止行 |
| 读 task.json / knowledge.md / publisher.json | `Read` | 文件较小，一次性看全 |
| 抽取散文里的 height、publisher 字段 | `grep -nE` 关键词锚点 | 只对带「centimeters」「publisher 13 / publisher … 数字」的段落取行，避免被 demographic / 颜色等无关章节干扰 |
| 多表连接（id → height + id → publisher） | 心智 join + 按 31 个候选 ID 逐条核对 publisher 段 | 候选规模很小（31），手动核对比临时建表更快也更可控 |

### 方法层面
1. **分章节定位**：先用「With the conclusion / Having concluded / With the completion」之类标题切出 biometrics 与 publisher 两个独立段落，避免把 demographic 段里的 `1.0` 误当成 publisher 编码。
2. **针对修正记录优先取最新值**：散文里频繁出现 "initially X … updated to Y" 的句式，统一只取 Y。
3. **占位/估计值不入字段**：0.0、NaN 以及散文里的"approximately/around X cm"是说明性文字，不进入 height_cm 字段，BETWEEN 自然把它们排除。

### 一句话总结
> 散文表当作半结构化数据，关键词锚点切片 + 章节边界切片，再逐条 join。

---

## 推理线索

### 线索 1：publisher.json 直接给出 Marvel 对应的 id
来源：`context/json/publisher.json`
- `{"id": 13, "publisher_name": "Marvel Comics"}`
→ 后续在 superhero.md 中只需匹配 publisher 编号 13。

### 线索 2：身高字段从「core physical biometrics」段抽取
来源：`context/doc/superhero.md` 行 432–644
- 全段共 74 条 `centimeters` 记录，覆盖约百名英雄；
- 凡 `0.0 centimeters` / `NaN` 视为占位，直接被 BETWEEN 过滤；
- 出现修正时（如 ID 7「188.0 → 193.0」、ID 104「175 → 178」）取修正后值。
→ 计算得 31 个 ID 落在 [150, 180]。

### 线索 3：publisher 编码从「publisher affiliation」段抽取
来源：`context/doc/superhero.md` 行 863 起
- 每条形如「publisher affiliation … code 13 / publisher 4 / publisher 13」；
- ID 744 Wonder Man 的 publisher 也有修正（"misfiled as 4 … rectified to 13"），统一取最新值；该英雄 height=188 不在 [150,180]，未影响结果。
→ 31 个 ID 中有 17 个对应 publisher 13。

### 线索 4：百分比公式与 gold 表头一致
来源：`context/knowledge.md` §3 Calculation Logic
- `Percentage = SUM(condition)/COUNT(total) × 100`
- 等价 SQL：
```sql
SELECT CAST(COUNT(CASE WHEN T2.publisher_name = 'Marvel Comics' THEN 1 ELSE NULL END) AS REAL) * 100
       / COUNT(T1.id)
FROM superhero AS T1
INNER JOIN publisher AS T2 ON T1.publisher_id = T2.id
WHERE T1.height_cm BETWEEN 150 AND 180;
```
→ `17 / 31 * 100 = 54.83870967741935`。

---

## 最终答案

| 字段 | 值 |
|---|---|
| 满足 height_cm ∈ [150,180] 的英雄数（分母） | 31 |
| 其中 publisher = Marvel Comics 的英雄数（分子） | 17 |
| **百分比** | **54.83870967741935** |

> 数据来源：`context/json/publisher.json`（publisher 维度）+ `context/doc/superhero.md`（biometrics 与 publisher 两段散文事实）。
> 假设：身高 BETWEEN 闭区间；占位 0.0/NaN 自动被过滤；散文中的「estimated/approximately」备注不视作 height_cm 字段值。
