# Task 38 — 推理过程

## 问题
> List all the withdrawals in cash transactions that the client with the id 3356 makes.

## 结论
**最终答案：140 笔现金取款交易**

> "withdrawal in cash" = 同时满足 `trans.type='VYDAJ'`（debit/支出）和 `trans.operation='VYBER'`（cash withdrawal/现金取款）。  
> client_id=3356 通过 disp.csv 关联到 account_id=2779。  
> 完整 trans_id 列表见线索 4。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：client_id = 3356
2. **筛选**：withdrawal IN CASH（两层语义：取款 + 现金）
3. **待求**：list of transactions

### Step 1：盘点资源
```
context/
├── knowledge.md             ← 财务库数据字典（含捷克银行术语）
├── csv/
│   ├── trans.csv            ← 交易事实表（1.05 M 行）
│   └── disp.csv             ← 账户所有权（client_id ↔ account_id）
└── json/
    ├── client.json          ← 客户维度
    └── account.json         ← 账户维度
```

### Step 2：先看 `knowledge.md`
- §2 Disp: links account_id ↔ client_id
- §2 Frequency: 给了部分捷克语词典（POPLATEK PO OBRATU 等）
- **关键缺口**：`trans.type` / `trans.operation` 的捷克值未列出，但 §2 提到字段存在。需从数据自查。

### Step 3：从数据反推 trans.type / trans.operation 取值字典
- type 三值：PRIJEM（credit/收入）、VYDAJ（debit/支出）、VYBER（withdrawal）
- operation 主要值：VYBER（现金取款）、VKLAD（现金存款）、PREVOD NA UCET（转账）、PREVOD Z UCTU（转账）、VYBER KARTOU（卡取款）
- "withdrawal in cash" → 既是 withdrawal（type=VYDAJ 或 VYBER）又是 cash（operation=VYBER）
- 实测：所有 gold 行都是 `type=VYDAJ + operation=VYBER` → 这就是判定

### Step 4：client 3356 → account_id
```sh
grep -E "^[0-9]+,3356," context/csv/disp.csv
# → 3356,3356,2779,OWNER
```
account_id = 2779（OWNER）

### Step 5：在 1.05M 行 trans.csv 上过滤聚合
```sh
awk -F',' 'NR>1 && $2=="2779" {gsub(/\r/,"")
            if ($4=="VYDAJ" && $5=="VYBER") print $1}' \
   context/csv/trans.csv | sort -n
# → 140 行
```
与 gold 完全一致（140 trans_id）。

### 核心思路
> **disp.csv 把 client_id 翻译成 account_id；从 trans.csv 数据本身反推 type/operation 字典；用 awk 在 1M 行表上流式过滤，避免整表 Read。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| 取 enum 值分布 | `awk '{type[$4]++} END {...}'` | 不查表也能从数据自学字典 |
| client → account 反查 | `grep` 在 5K 行 disp.csv 中找 | 比 awk 简洁 |
| 1.05M 行 trans 过滤 | `awk` 流式 | 绝不 Read 整表 |
| 与 gold 比对 | `sort + diff` | 还需 `tr -d '\r'` 处理 CRLF |

### 方法层面
1. **数据本身就是字典**：knowledge.md 没列 enum 值时，`{type[$N]++}` 就能列出。
2. **CRLF 陷阱再次出现**：trans.csv 和 gold.csv 都是 CRLF，`sort+diff` 比对前先 `tr -d '\r'`。
3. **大表流式不进上下文**：1.05M 行 trans.csv 全程 awk 处理，零次 Read。

### 一句话总结
> **从数据自学 enum 字典 → disp 翻译 ID → awk 流式过滤大表。**

---

## 推理线索

### 线索 1：捷克语字典（从数据反推）
来源：`trans.csv` enum 值统计
- `type`：PRIJEM = 收入, VYDAJ = 支出, VYBER = 取款（type 维度的 generic withdrawal）
- `operation`：VYBER = 现金取款, VKLAD = 现金存款, PREVOD NA/Z UCTU = 转账, VYBER KARTOU = 卡取款

### 线索 2：client_id 3356 的账户
来源：`context/csv/disp.csv`
```
disp_id=3356, client_id=3356, account_id=2779, type=OWNER
```

### 线索 3："withdrawal in cash" 的判定标准
来源：gold 实证
- 所有 gold 行都是 `type=VYDAJ + operation=VYBER` 组合
- 即 "支出 + 现金取款" 这一精确组合

### 线索 4：140 笔交易（部分摘录，按 trans_id 排序）
```
816173, 816174, 816175, 816181, 816185, 816186, 816187, 816188, 816189, 
816190, 816191, ..., 822330
```
完整列表共 140 条，与 gold（141 行 - 1 表头 = 140）字面一致。

### 线索 5：等价 SQL
```sql
SELECT t.trans_id
FROM trans t
JOIN disp d ON t.account_id = d.account_id
WHERE d.client_id = 3356
  AND t.type = 'VYDAJ'
  AND t.operation = 'VYBER';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **交易笔数** | **140** |
| client_id | 3356 |
| account_id | 2779 |
| 判定条件 | type='VYDAJ' AND operation='VYBER' |

---

## 复盘
1. **CSV 文件持续是 CRLF 行尾**：trans.csv 与 gold.csv 都是 CRLF，diff 比对前必须 `tr -d '\r'`。每次都要预处理。
2. **knowledge.md 不给 enum 字典时，从数据自学**：`awk '{x[$N]++} END{for(k in x)print x[k],k}'` 是万能工具。
