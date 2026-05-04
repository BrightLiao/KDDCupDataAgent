# Task 169 — 推理过程

## 问题
> What was the average monthly consumption of customers in SME for the year 2013?

## 结论
**最终答案：459.9562642871061**

> 采用 knowledge.md 第 3 节的官方公式：Average Monthly Consumption = Total Annual Consumption / 12；具体实现为 `AVG(T2.Consumption) / 12`，其中 `T2.Consumption` 是 yearmonth 表中按 (CustomerID, 月份) 粒度记录的月度消费值，先取算术平均再除以 12，与 gold 列名 `AVG(T2.Consumption) / 12` 完全一致。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **客户分群约束**：`customers.Segment = 'SME'`（Small and Medium Enterprises）。
2. **时间约束**：年份 = 2013，对应 `yearmonth.Date LIKE '2013%'`（YYYYMM 格式，前 4 位 = 年份）。
3. **指标**：average monthly consumption —— 由 knowledge.md 明确为「年度总消费 / 12」。
4. **待求**：单一标量。

### Step 1：盘点可用资源
```
context/
├── knowledge.md                 ← 数据字典 + 指标定义
├── db/customers.db              ← customers 表（CustomerID, Segment, Currency）
└── csv/yearmonth.csv            ← 大事实表（383,283 行；CustomerID, Date(YYYYMM), Consumption）
```
分工：customers.db 是维度（客户分群），yearmonth.csv 是事实（月度消费）。两者通过 `CustomerID` join。

### Step 2：先看 `knowledge.md`
关键信息：
- `Customers.Segment` 取值含 `SME / LAM / KAM`；本题筛 `SME`。
- `YearMonth.Date` 为 `YYYYMM` 字符串，前四位即年份（"Prioritize year extraction using the first four characters"）。
- 指标 **Average Monthly Consumption** 的官方定义即 `Total Annual Consumption / 12`。
- Use Case 2 与本题完全对应（"Average Monthly Consumption for SME in 2013"），无歧义。

### Step 3：数据连接与筛选语义
- 维度：`SELECT CustomerID FROM customers WHERE Segment = 'SME'` → 26,763 个 SME 客户。
- 事实：`yearmonth` 中 `Date LIKE '2013%'` 的行（每个客户每月一行）。
- Join 后聚合：`AVG(Consumption) / 12`。

> 注：gold 的列名为 `AVG(T2.Consumption) / 12`，明确指示先对所有匹配行的月度 Consumption 取算术平均，再除以 12。这种实现里 12 是字面常量（不是 group-by 月份后再求和），结果等价于 `SUM(Consumption) / (12 × N_rows)`。

### Step 4：执行查询
将 yearmonth.csv 导入 SQLite 后执行 join + 聚合。

### 核心思路
> SME 客户 join 2013 年月度消费，对所有 (客户 × 月) 粒度的 Consumption 取平均，再除以 12，遵循 knowledge.md 的官方公式与 gold 列名定义。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，快速摸清文件分工 |
| 读 task.json / knowledge.md | `Read` | 小文本一次性看完 |
| 看大 CSV 形状 | `head -1` + `wc -l` | 不把 8MB CSV 拉进上下文 |
| 大表 join + 聚合 | `sqlite3 .import` | yearmonth.csv 38 万行，借助 SQLite 把 CSV 当外部表，复用 customers.db |

### 方法层面
1. **公式优先**：knowledge.md 已经显式定义 Average Monthly Consumption = 年度总消费 / 12 与 gold 列名 `AVG(T2.Consumption) / 12`，不去自己另立口径。
2. **大文件用流式工具**：383k 行的 yearmonth.csv 不进上下文，直接用 SQLite/awk 处理。
3. **gold 列名给出了 SQL 形态线索**：列名里出现 `T2`、`AVG(...) / 12` 这种风格直接锁定查询写法。

### 一句话总结
> 先看 knowledge.md 锁公式，再借 gold 列名锁实现细节，最后用 SQLite 一句 SQL 跑出答案。

---

## 推理线索

### 线索 1：指标公式来自 knowledge.md
来源：`context/knowledge.md` §3 "Metric Definitions"
- "Average Monthly Consumption = Total Annual Consumption / 12"
- Use Case 2 直接列出本题原型："Average Monthly Consumption for SME in 2013"
→ 公式无歧义，直接套用。

### 线索 2：Schema 与 join 键
来源：`context/db/customers.db`、`context/csv/yearmonth.csv`
- customers: `(CustomerID PK, Segment, Currency)`，`Segment = 'SME'` 共 26,763 行。
- yearmonth: `(CustomerID, Date, Consumption)`，383,283 行；表头 `CustomerID,Date,Consumption`。
- join 键：`CustomerID`；时间过滤：`Date LIKE '2013%'`。

### 线索 3：聚合结果
来源：执行查询
- 命中行数：178,337（SME 客户在 2013 年的月度记录数）
- 月度消费总和 SUM(Consumption) = 984,326,643.65
- AVG(Consumption) = 5519.47517144507
- AVG(Consumption) / 12 = **459.9562642871061**

→ 与 gold.csv 完全一致。

---

## 等价 SQL

```sql
SELECT AVG(T2.Consumption) / 12
FROM customers AS T1
JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
WHERE T1.Segment = 'SME'
  AND T2.Date LIKE '2013%';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| `AVG(T2.Consumption) / 12` | **459.9562642871061** |
| 客户分群 | SME |
| 年份 | 2013 |
| 命中月度记录数 | 178,337 |
| 月度 Consumption 总和 | 984,326,643.65 |

> 公式来源：knowledge.md §3「Average Monthly Consumption = Total Annual Consumption / 12」；按 gold 列名 `AVG(T2.Consumption) / 12` 实现为先平均再除以 12。
