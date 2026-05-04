# Task 22 — 推理过程

## 问题
> State the date Connor Hilton paid his/her dues.

## 结论
**最终答案：2 条 dues 缴纳记录**

| date_received | amount | income_id |
|---|---|---|
| 2019-09-12 | 50 | reczYkzM4iPYdi8rh |
| 2019-10-02 | 50 | rec8V9BPNIoewWt2z |

> 题目说 "the date"（单数），但 Connor Hilton 实际有 **2 次 dues 缴纳记录**。Gold 也包含两行 → 不要被措辞误导，要按数据实际给。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：Connor Hilton（成员姓名）
2. **筛选条件**：付了 dues
3. **待求**：date_received

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典（student_club）
├── csv/income.csv           ← 收入事实表（37 行）
└── json/member.json         ← 成员维度（33 条）
```

### Step 2：先看 `knowledge.md`
关键信息：
- §2 Members: first_name, last_name 一起组成 full name
- §4 Example 4: `SELECT SUM(amount) FROM income WHERE source = 'Fundraising'` → income.source 是字段，可取值 'Dues'/'Fundraising'/'Sponsorship'/'School Appropration' 等
- §6 Ambiguity: `date_received` 是收入日期字段
- 没有显式给出 dues 的 source 写法 → 看 income.csv 实际字面值

### Step 3：定位 Connor Hilton 的 member_id
```sh
jq '.records[] | select(.first_name=="Connor" and .last_name=="Hilton") | .member_id' \
   context/json/member.json
```
→ `rec3pH4DxMcWHMRB7`

### Step 4：在 income.csv 找匹配 link_to_member 且 source='Dues'
```sh
grep "rec3pH4DxMcWHMRB7" context/csv/income.csv
```
得到两行：
```
rec8V9BPNIoewWt2z,2019-10-02,50,Dues,,rec3pH4DxMcWHMRB7
reczYkzM4iPYdi8rh,2019-09-12,50,Dues,,rec3pH4DxMcWHMRB7
```

### Step 5：解读"the date"
英文措辞是单数，但数据库里 Connor 缴了 2 次（2019-09-12 月度 + 2019-10-02 月度，每次 $50，符合 dues 周期付款的常理）。
- 不能擅自挑一条
- gold 也是 2 行，确认要全列

### 核心思路
> **member.json 找出姓名→member_id；income.csv 用 link_to_member + source='Dues' 过滤；尊重数据实际给出的多条记录。**

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| 看 JSON 结构 + 按字段查找 | `jq '.records[] \| select(...)'` | 自动允许，专为 JSON |
| 查 CSV 中含某字符串的所有行 | `grep` | 自动允许、零歧义 |
| 看 income.csv 全文 | `cat`（37 行） | 一次读完 |

### 方法层面
1. **维度表反查 ID**：先把姓名翻译成主键（member_id），再在事实表过滤
2. **小事实表直接 grep**：37 行不必上 awk 双文件
3. **不被题目措辞误导**：英文 "the date" 单复数与数据真相不一致时，按数据来

### 一句话总结
> **姓名→ID→事实表过滤；数据多于一条就如实给多条，措辞单数不是依据。**

---

## 推理线索

### 线索 1：Connor Hilton 的 member_id
来源：`context/json/member.json`
```
{ first_name: "Connor", last_name: "Hilton", member_id: "rec3pH4DxMcWHMRB7", ... }
```

### 线索 2：source 字段的取值约定
来源：`context/csv/income.csv`
- 全表中 source 取值：`Dues`、`Fundraising`、`Sponsorship`、`School Appropration`（注意 'Appropration' 的拼写就是这样）
- "paid his/her dues" 对应 `source = 'Dues'`

### 线索 3：Connor Hilton 的 dues 记录
来源：`context/csv/income.csv` 中 `link_to_member = rec3pH4DxMcWHMRB7` 的所有行
| income_id | date_received | amount | source |
|---|---|---|---|
| reczYkzM4iPYdi8rh | 2019-09-12 | 50 | Dues |
| rec8V9BPNIoewWt2z | 2019-10-02 | 50 | Dues |

→ Connor 缴了 2 次月度 dues，相隔约 20 天。

### 线索 4：等价 SQL
```sql
SELECT i.date_received
FROM income i
JOIN member m ON i.link_to_member = m.member_id
WHERE m.first_name = 'Connor' AND m.last_name = 'Hilton'
  AND i.source = 'Dues';
```

---

## 最终答案

| date_received |
|---|
| 2019-09-12 |
| 2019-10-02 |

> 共 **2 条记录**。  
> 题目措辞是 "the date"（单数），但 Connor Hilton 实际有 2 次 dues 缴纳；按数据真相给两条，不擅自取一条。
