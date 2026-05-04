# Task 180 — 推理过程

## 问题
> For all the people who paid more than 29.00 per unit of product id No.5. Give their consumption status in the August of 2012.

## 结论
**最终答案：9 位客户在 2012 年 8 月的消费分别为 1903.2, 88265.39, 1129.2, 126157.7, 58.19, 1142.95, 8878.07, 69331.72, 45937.22**

> 单价定义为 `Price / Amount`（交易表中 Price 是该交易的总金额，Amount 是单位数量）；2012 年 8 月对应 `yearmonth.Date = '201208'`。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **产品条件**：ProductID = 5
2. **单价条件**：单价（Price/Amount）> 29.00
3. **目标客户集合**：满足上述两条件的所有不同 CustomerID
4. **统计区间**：2012 年 8 月（YearMonth.Date = '201208'）
5. **待求**：这些客户在 2012 年 8 月的 Consumption（消费状态）

### Step 1：盘点可用资源
```
context/
├── knowledge.md                ← 数据字典（实体、字段、Date 格式）
├── csv/yearmonth.csv           ← 客户每月消费汇总（CustomerID, Date(YYYYMM), Consumption）
└── db/transactions_1k.db       ← 交易明细（含 ProductID、Amount、Price、CustomerID）
```
分工：transactions_1k 用来定位 "买过 ProductID=5 且单价>29 的客户"；yearmonth.csv 用来按月聚合查询 2012 年 8 月的消费。

### Step 2：先看 `knowledge.md`
关键信息：
- **YearMonth.Date** 用 `YYYYMM` 字符串，2012 年 8 月即 `'201208'`。
- **YearMonth.Consumption** 是该月该客户的消费总额，即题目要求的 "consumption status"。
- 没有"单价"字段定义；按交易明细常识，单价 = Price ÷ Amount。

### Step 3：定位"单价 > 29.00 且 ProductID=5"的客户
查 transactions_1k schema：`Price REAL`（行总价），`Amount INTEGER`（数量），`ProductID INTEGER`。
SQL：
```sql
SELECT DISTINCT CustomerID
FROM transactions_1k
WHERE ProductID = 5 AND (Price * 1.0 / Amount) > 29.00;
```
得到 9 个 CustomerID：18831, 5443, 46933, 6768, 20447, 45868, 23861, 24700, 7626。

### Step 4：在 yearmonth.csv 中查这 9 个客户 2012-08 的消费
yearmonth.csv 较大（38 万行），用 grep 直接锚定：
```sh
grep -E "^(18831|5443|46933|6768|20447|45868|23861|24700|7626),201208," yearmonth.csv
```
9 个客户全部命中，每人在 201208 都有 1 行记录。

### 核心思路
> 先在交易明细里用单价（Price/Amount）筛 ProductID=5 的客户（含 DISTINCT 去重），再去月度汇总表里取每个客户在 201208 的 Consumption。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，快速摸清文件分工 |
| 读 knowledge.md / task.json | `Read` | 文件小、需要全文理解 |
| 看 yearmonth.csv 表头 + 行数 | `head -2` + `wc -l` | 不把 8MB CSV 全读进上下文 |
| 看 SQLite schema 与样本 | `sqlite3` `.schema` + `LIMIT 5` | 既看结构又看真实数据 |
| 在交易表筛"单价 > 29 的客户" | `sqlite3 SELECT DISTINCT` | 用 SQL 直接表达单价计算与去重 |
| 在大 CSV 中按 ID + 月份精确取行 | `grep -E "^(id1\|id2)…,201208,"` | 锚定行首 + 字面常量，最快也最稳 |

### 方法层面
1. **分层阅读**：先 schema/字典，再事实表抽样，最后才执行查询。
2. **用 SQL 表达"单价"**：交易表只给了 Price 和 Amount，单价是派生字段（Price/Amount）。
3. **跨源 join 用 ID 列表过桥**：先在 DB 里得到候选 CustomerID，再在 CSV 里 grep 这些 ID。

### 一句话总结
> 先把"谁"找出来（SQLite + 派生单价），再把"多少"补上（grep yearmonth.csv 取月度 Consumption）。

---

## 推理线索

### 线索 1：单价 = Price / Amount
来源：`context/db/transactions_1k.db` schema
- `Price REAL` 是该笔交易的金额（如 5 单位的 ProductID=5 总价 120.74）。
- `Amount INTEGER` 是数量。
- 故 "paid per unit" = Price / Amount。
→ 谓词写成 `(Price * 1.0 / Amount) > 29.00`。

### 线索 2：2012 年 8 月对应 Date='201208'
来源：`context/knowledge.md` §4 Temporal Boundaries
- "Fiscal Year Format: 'YYYYMM'，2012 年 1 月即 '201201'"。
→ August of 2012 ⇔ `'201208'`。

### 线索 3：满足条件的 9 个客户
来源：在 `transactions_1k` 上执行
```sql
SELECT DISTINCT CustomerID
FROM transactions_1k
WHERE ProductID = 5 AND (Price * 1.0 / Amount) > 29.00;
```
→ {18831, 5443, 46933, 6768, 20447, 45868, 23861, 24700, 7626}。

### 线索 4：9 个客户在 201208 的 Consumption
来源：`context/csv/yearmonth.csv` grep 结果
| CustomerID | 201208 Consumption |
|---|---|
| 18831 | 1903.2 |
| 5443  | 88265.39 |
| 46933 | 1129.2 |
| 6768  | 126157.7 |
| 20447 | 58.19 |
| 45868 | 1142.95 |
| 23861 | 8878.07 |
| 24700 | 69331.72 |
| 7626  | 45937.22 |

---

## 等价 SQL

```sql
SELECT y.Consumption
FROM yearmonth AS y
WHERE y.Date = '201208'
  AND y.CustomerID IN (
        SELECT DISTINCT t.CustomerID
        FROM transactions_1k AS t
        WHERE t.ProductID = 5
          AND (t.Price * 1.0 / t.Amount) > 29.00
  );
```

---

## 最终答案

| CustomerID | Consumption (201208) |
|---|---|
| 18831 | **1903.2** |
| 5443  | **88265.39** |
| 46933 | **1129.2** |
| 6768  | **126157.7** |
| 20447 | **58.19** |
| 45868 | **1142.95** |
| 23861 | **8878.07** |
| 24700 | **69331.72** |
| 7626  | **45937.22** |

> 共 9 位客户，全部在 2012 年 8 月有消费记录。单价阈值采用 `Price/Amount > 29.00`（严格大于），月份编码采用 knowledge.md 规定的 `YYYYMM='201208'`。
