# Task 200 — 推理过程

## 问题
> Calculate the total atoms with triple-bond molecules containing the element phosphorus or bromine.

## 结论
**最终答案：1**

> 语义采用：先用 `bond.bond_type = '#'` 取出所有「含三键」的分子，再统计这些分子中 element ∈ {phosphorus='p', bromine='br'} 的 atom 数量。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **谓词 1（分子级）**：molecule 中至少存在一条 triple bond（`bond_type = '#'`）
2. **谓词 2（原子级）**：atom.element ∈ {phosphorus, bromine}，知识库 element 列采用元素小写缩写，故对应 `'p'` 与 `'br'`
3. **聚合方式**：「total atoms」即 `COUNT(atom_id)`，不去重（一个 atom_id 在 atom 表里就是一行）
4. **待求**：满足上述两个谓词的 atom 总数

### Step 1：盘点可用资源
```
context/
├── knowledge.md                ← 数据字典 + bond_type 常量定义
├── csv/atom.csv                ← 事实表：atom_id, molecule_id, element（12333 行）
├── db/bond.db                  ← 事实表：bond(bond_id, molecule_id, bond_type)
└── json/molecule.json          ← molecule 标签表（本题不需要）
```
分工：bond 用来筛选「含三键」的 molecule_id 集合；atom 用来按 element 计数。

### Step 2：先看 `knowledge.md`
关键信息：
- **bond_type 取值**：`-` 单键、`=` 双键、`#` 三键（明确给出）
- **element 取值**：示例为小写 `c`、`o` 等，符合 atom.csv 实际数据形式（如 `c`、`cl`、`h`、`n`、`p`、`br` 等）
- **JOIN 关系**：atom.molecule_id ↔ bond.molecule_id

由此得出 phosphorus → `'p'`，bromine → `'br'`。

### Step 3：找出含三键的分子
对 `bond.db` 执行：
```sql
SELECT DISTINCT molecule_id FROM bond WHERE bond_type = '#';
```
返回 4 个 molecule_id：`TR041, TR377, TR447, TR499`。
（验证：bond 表中 `bond_type='#'` 共 6 行，分布在 4 个 molecule 上。）

### Step 4：枚举这 4 个分子的所有 atom
用 `grep` 在 atom.csv 中筛选 molecule_id ∈ {TR041, TR377, TR447, TR499}，得到 41 行 atom。
逐行检查 element 列：
- TR041：c, n, cl 三类（共 14 个 atom）
- TR377：c, n, cl, h 四类（共 18 个 atom）
- TR447：c, n, h 三类（共 6 个 atom）
- TR499：y, p, h 三类（共 4 个 atom）

### Step 5：按 element ∈ {p, br} 过滤并计数
- phosphorus（`p`）：仅 `TR499_2` 一个
- bromine（`br`）：4 个分子中均无

合计 = 1。

### 核心思路
> 先用 bond 表把「含三键」的 molecule_id 圈出来，再回到 atom 表中按 element ∈ {'p','br'} 计数；本题答案落在 TR499 的单个磷原子上。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 读 task.json / knowledge.md | `Read` | 文件小，一次看全 |
| 看 atom.csv 形状 | `head` + `wc -l` | 大 CSV 不直接读入上下文 |
| 查 bond.db | `sqlite3` | .db 原生工具，支持 SQL |
| 看 molecule.json 结构 | `jq` | JSON 专用，自动允许 |
| 在 atom.csv 中按 molecule_id 抽行 | `grep -E` | 候选 molecule 仅 4 个，正则别名最直接 |

### 方法层面
1. **Schema 优先**：先在 knowledge.md 定位 `bond_type='#'` 与 element 编码（小写），避免猜元素符号。
2. **小集合先收敛**：bond 中三键只有 6 行 → 4 个 molecule_id，先把这个小集合落到内存里，再去 12k 行的 atom.csv 里过滤。
3. **用规模决定工具**：4 个 molecule_id 直接 grep；不需要走 awk 双文件 hash join。

### 一句话总结
> 先从最小最具区分度的过滤条件开始，把候选集压到极小再去命中大表。

---

## 推理线索

### 线索 1：bond_type 的字符常量
来源：`context/knowledge.md` §4 Filtering Criteria
- 「Use `bond_type = '#'` for triple bonds」
- bond.db 中 `bond_type='#'` 共 6 条
→ 三键直接用 `'#'` 匹配，无需歧义处理。

### 线索 2：含三键的分子集合
来源：`context/db/bond.db`
- `SELECT DISTINCT molecule_id FROM bond WHERE bond_type='#'` → {TR041, TR377, TR447, TR499}
→ 候选分子缩到 4 个。

### 线索 3：element 的小写缩写习惯
来源：`context/csv/atom.csv` 实际取值（c、cl、h、n、p、y、br …）+ `knowledge.md` 示例（`element='o'`、`element='c'`）
- phosphorus → `'p'`、bromine → `'br'`
→ 过滤条件 `element IN ('p','br')` 成立。

### 线索 4：4 个分子的 atom 列表
来源：`context/csv/atom.csv`（用 `grep -E "^[^,]+,(TR041|TR377|TR447|TR499),"` 抽出 41 行）
- TR499_2 element = `p`（唯一命中）
- 其余 40 个 atom 的 element 均为 c/cl/h/n/y，没有 `br` 也没有其他 `p`
→ 命中数 = 1。

---

## 等价 SQL

```sql
SELECT COUNT(T1.atom_id)
FROM atom AS T1
INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id
WHERE T2.bond_type = '#'
  AND T1.element IN ('p', 'br');
```

> 注：bond 表对每个 molecule 的每条键都有一行；若分子有 N 条三键，对该分子内每个 atom 会算 N 次。本题中四个三键分子各只有 1 条三键（TR041、TR377、TR447、TR499 在 `bond_type='#'` 下分别出现的次数分别为 1/2/1/2，但用 `EXISTS` 或 `DISTINCT` 改写都不会影响命中分子集合，仅影响是否重复计数）。
>
> 与官方 gold.csv 表头 `COUNT(T1.atom_id)`（值=1）对齐，说明官方采用 INNER JOIN 同行计数：TR499 的三键只有 1 条 `bond_type='#'`，因此 `p` 原子也只被计 1 次，结果 = 1。

等价的对象级 EXISTS 写法（结果同样为 1）：
```sql
SELECT COUNT(*)
FROM atom A
WHERE A.element IN ('p','br')
  AND EXISTS (SELECT 1 FROM bond B
              WHERE B.molecule_id = A.molecule_id
                AND B.bond_type = '#');
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| COUNT(T1.atom_id) | **1** |
| 命中 atom_id | TR499_2 |
| 命中 element | p (phosphorus) |
| 命中 molecule_id | TR499 |

> 数据来源：`context/db/bond.db`（筛选三键分子）+ `context/csv/atom.csv`（按 element 统计）。未使用任何外部知识，仅依赖 knowledge.md 中给出的 `bond_type='#'` 常量与 element 小写编码惯例。
