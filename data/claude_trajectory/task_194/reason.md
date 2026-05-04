# Task 194 — 推理过程

## 问题
> What are the bonds that have phosphorus and nitrogen as their atom elements?

## 结论
**最终答案：6 个 bond — `TR032_2_3`、`TR032_3_5`、`TR058_1_3`、`TR058_1_4`、`TR058_1_5`、`TR298_1_5`**

> 语义假设：一根 bond 的两个端点原子分别为 phosphorus（element='p'）与 nitrogen（element='n'），不限顺序；通过 `connected` 表把 bond 的两端原子连到 `atom` 表后做元素匹配。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：bond（化学键）
2. **谓词**：bond 的两个端点原子，一端是 phosphorus（`p`），另一端是 nitrogen（`n`）
3. **待求**：满足条件的 `bond_id` 列表

### Step 1：盘点可用资源
```
context/
├── knowledge.md            ← 数据字典（实体/字段/常量）
├── csv/connected.csv       ← (atom_id, atom_id2, bond_id)，bond 两端的原子映射
└── db/atom.db              ← 含两张表 atom(atom_id, molecule_id, element) 和 connected(atom_id, atom_id2, bond_id)
```
分工：
- `atom` 表给出每个 atom 的元素（element）
- `connected` 表给出每条 bond 关联的两个 atom_id
- 两表通过 atom_id join，得到 bond 端点的元素信息

注意：context 中**没有** `bond` 表（仅出现在 knowledge.md 的语义描述里），需要的 bond_id 完全可以从 `connected` 中获得。

### Step 2：先看 `knowledge.md`
关键信息：
- **Atom**：`atom_id, molecule_id, element`（元素如 'c'、'h'、'o'、'n'、'p' 等单字母小写表示）
- **Connected**：`atom_id, atom_id2, bond_id` —— 表示这对原子由这条 bond 连接
- **Bond**：`bond_id, molecule_id, bond_type`（本任务无 bond 表，但 bond_id 已可在 connected 中获得）
- 元素采用小写字母缩写约定（参考 KPI 中的 `element = 'o'`、`element = 'c'`），因此 phosphorus → `'p'`，nitrogen → `'n'`

### Step 3：核对元素枚举
```sql
SELECT DISTINCT element FROM atom;
-- 返回: cl, c, h, o, s, n, p, na, br, f, i, sn, pb, te, ca, zn, si, b, k, cu, y
```
确认 `'p'` 和 `'n'` 都在合法取值集合中。

### Step 4：检查 connected 的方向性
`connected.csv` 含 24,758 行，约为 atom 数（12,333）的两倍。抽样：
```
TR000_1,TR000_2,TR000_1_2
TR000_2,TR000_1,TR000_1_2
```
说明 connected 把每条 bond 双向记录了一次，所以无需手工对称化，只需对 bond_id 做 DISTINCT 即可。

### Step 5：执行 join 查询
SQL（在 `db/atom.db` 上直接跑）：
```sql
SELECT DISTINCT c.bond_id
FROM connected c
JOIN atom a1 ON c.atom_id  = a1.atom_id
JOIN atom a2 ON c.atom_id2 = a2.atom_id
WHERE (a1.element = 'p' AND a2.element = 'n')
   OR (a1.element = 'n' AND a2.element = 'p')
ORDER BY c.bond_id;
```
执行结果（6 行）：
```
TR032_2_3
TR032_3_5
TR058_1_3
TR058_1_4
TR058_1_5
TR298_1_5
```

### 核心思路
> bond 端点元素 = `connected` 与 `atom` 双向 join，两端分别为 `p` 与 `n`（不限顺序），DISTINCT 后即得答案。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 列文件分工，零成本 |
| 读 knowledge.md | `Read` | 6 KB 小文件，一次看全 |
| 看大 CSV 形状 | `wc -l` + `head` | 24K 行流式查看 |
| Schema/查询 | `sqlite3` | 任务自带 .db，SQL 直接 join 最准确 |

### 方法层面
1. **优先用 .db**：当 context 同时提供 csv 和 db 时，db 已建表/有索引，SQL 写 join 最少坑。
2. **核对元素小写约定**：从 KPI 例 5 的 `element = 'o'` 推出元素采用小写缩写。
3. **关注表结构差异**：`bond` 在 knowledge.md 里描述了，但本任务 context 没给 bond 表 —— 不必纠结，bond_id 在 `connected` 表已存在。

### 一句话总结
> 先用 knowledge.md 建 schema 心智模型，再用 sqlite3 直接做精确 join。

---

## 推理线索

### 线索 1：元素以单字母小写表示
来源：`context/knowledge.md` §3 KPI（`element = 'o'`、`element = 'c'`）
- phosphorus → `'p'`
- nitrogen → `'n'`
→ 在 atom 表中查询元素值需用小写字母

### 线索 2：connected 双向记录
来源：`context/csv/connected.csv` 抽样
- `TR000_1,TR000_2,TR000_1_2`
- `TR000_2,TR000_1,TR000_1_2`
→ 同一 bond 的两个方向都在表里 → 用 `DISTINCT bond_id` 去重；查询条件用 `(p,n) OR (n,p)` 也安全

### 线索 3：connected ⨝ atom 即可拿到端点元素
来源：`context/db/atom.db` 表结构
- `connected(atom_id, atom_id2, bond_id)` × `atom(atom_id, element)`
→ 两次 join 分别拿到两端元素 → 过滤 (p,n) 配对

### 线索 4：核对结果
- 命中 4 个分子：TR032、TR058、TR298（共 6 条 bond）
- TR058 一个原子（编号 1，可能是 N 或 P）连到 3 个不同原子，构成 3 条 P–N bond，与该分子可能含磷酸/磷酰胺类官能团一致

---

## 最终答案

| bond_id |
|---|
| TR032_2_3 |
| TR032_3_5 |
| TR058_1_3 |
| TR058_1_4 |
| TR058_1_5 |
| TR298_1_5 |

> 数据来源：`context/db/atom.db`（atom + connected 表）。元素编码采用 knowledge.md KPI 中既有的小写字母约定（`p` = phosphorus，`n` = nitrogen）。
