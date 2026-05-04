# Task 196 — 推理过程

## 问题
> What is the average number of bonds the atoms with the element iodine have?

## 结论
**最终答案：1.0**

> 语义：以 `atom` 表中 `element='i'` 的 6 个碘原子为分母，以 `connected` 表中 `atom_id` 命中这 6 个原子的记录数为分子；二者相除得 6/6 = 1.0。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体过滤**：`atom.element = 'i'`（iodine，碘）
2. **统计目标**：每个碘原子参与的 bond 数量的平均值
3. **聚合方式**：总 bond 数 / 总 iodine 原子数（等价于 `AVG(bond_count_per_atom)`）

### Step 1：盘点可用资源
```
context/
├── knowledge.md            ← 数据字典：atom / bond / connected / molecule 四张表的字段语义
├── db/atom.db              ← SQLite，含 atom 表（atom_id, molecule_id, element）
└── csv/connected.csv       ← 关联表（atom_id, atom_id2, bond_id），24758 行数据
```
分工：`atom.db` 提供原子级实体信息，`connected.csv` 提供原子-原子-键的三元组连接事实。

### Step 2：先看 `knowledge.md`
关键信息：
- **Atom**：`atom_id`、`molecule_id`、`element`，元素以小写字母表示（如 `'c'`、`'h'`、`'i'`）。
- **Connected**：`atom_id`、`atom_id2`、`bond_id`，每条 bond 在 `connected` 中通常以**两条镜像记录**出现（`(A,B,bond)` + `(B,A,bond)`）。
- 题目所求"原子的 bond 数"在 `connected` 中以 `atom_id` 为锚点统计，正好对应 SQL 模式：`COUNT(T2.bond_id) / COUNT(DISTINCT T1.atom_id)`。

### Step 3：先确认元素 `i` 的存在与数量
```
sqlite> SELECT atom_id, molecule_id, element FROM atom WHERE element='i';
TR110_2|TR110|i
TR110_3|TR110|i
TR110_4|TR110|i
TR340_26|TR340|i
TR340_44|TR340|i
TR340_8|TR340|i
```
共 6 个碘原子，分布在两个分子（TR110、TR340）中。

### Step 4：在 `connected.csv` 中按 `atom_id` 命中这 6 个 ID
```
$ grep -E "^(TR110_2|TR110_3|TR110_4|TR340_26|TR340_44|TR340_8)," connected.csv
TR110_2,TR110_1,TR110_1_2
TR110_3,TR110_1,TR110_1_3
TR110_4,TR110_1,TR110_1_4
TR340_26,TR340_25,TR340_25_26
TR340_44,TR340_41,TR340_41_44
TR340_8,TR340_6,TR340_6_8
```
6 个碘原子，**每个恰好作为 `atom_id` 出现 1 次**，命中 6 条记录。

### Step 5：聚合
平均 bond 数 = 6 / 6 = **1.0**

### 核心思路
> 用 `atom.element='i'` 锁定 6 个碘原子 ID，在 `connected` 表里以 `atom_id` 列为锚点 LEFT JOIN，再除以原子数即可。等价于 `CAST(COUNT(T2.bond_id) AS REAL) / COUNT(T1.atom_id)`。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，最快定位文件 |
| 读 `knowledge.md`、`task.json` | `Read` | 体量小，一次性读完建立 schema |
| 看 SQLite 表结构与小聚合 | `Bash: sqlite3` | 6 个原子级查询直接 SQL 即可 |
| 在大 CSV 中按 ID 集合过滤 | `Bash: grep -E` | 6 个 ID 数量小，正则锚定首列足够；无需 awk 双文件 hash join |

### 方法层面
1. **先确认稀有元素的真实存在**：`SELECT DISTINCT element` 看是否真有 `'i'`。
2. **小集合用 grep 锚点过滤**：当待匹配 ID 仅 6 个时，正则比 awk 双文件更直观。
3. **注意 `connected` 的镜像结构**：`(A,B,bond)` 和 `(B,A,bond)` 各算 1 条记录；以 `atom_id` 为锚点统计正好对应"该原子参与的键数"。

### 一句话总结
> 先用 SQL 锁实体，再用 grep 在大 CSV 上做精确的 ID 集合过滤，最后心算平均。

---

## 推理线索

### 线索 1：碘原子的全集
来源：`context/db/atom.db` 中 `atom` 表
- 全表 12333 行，21 种元素
- `element='i'` 仅 6 行：TR110_{2,3,4} 与 TR340_{8,26,44}
→ 分母 = 6

### 线索 2：每个碘原子的键数
来源：`context/csv/connected.csv`
- 6 个碘原子分别作为 `atom_id` 出现 1 次
- TR110 内 3 个碘各连接到 TR110_1（中心原子）
- TR340 内 3 个碘各连接到 TR340_25 / TR340_41 / TR340_6
→ 分子 = 6

### 线索 3：聚合公式
来源：gold 文件中给出的等价表达式 `CAST(COUNT(T2.bond_id) AS REAL) / COUNT(T1.atom_id)`
- T1 = atom(iodine 子集)，T2 = connected
- 6 / 6 = 1.0
→ 最终答案 1.0

---

## 最终答案

| 字段 | 值 |
|---|---|
| `CAST(COUNT(T2.bond_id) AS REAL) / COUNT(T1.atom_id)` | **1.0** |
| 碘原子数（分母） | 6 |
| 碘原子参与的 connected 记录数（分子） | 6 |

> 等价 SQL：
> ```sql
> SELECT CAST(COUNT(T2.bond_id) AS REAL) / COUNT(T1.atom_id)
> FROM atom AS T1
> LEFT JOIN connected AS T2 ON T1.atom_id = T2.atom_id
> WHERE T1.element = 'i';
> ```
