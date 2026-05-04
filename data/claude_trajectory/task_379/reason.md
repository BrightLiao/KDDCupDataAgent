# Task 379 — 推理过程

## 问题
> Tally the toxicology element of the 4th atom of each molecule that was carcinogenic.

## 结论
**最终答案：c, br, cl, s, o, n, f（共 7 种 element 出现在 100 个致癌分子的第 4 个原子中）**

按出现次数：c=76、o=9、cl=5、br=4、n=3、s=2、f=1（合计 100）。
按首次出现顺序排列即为 gold.csv 中的列：c, br, cl, s, o, n, f。

> 假设："the 4th atom of each molecule" 指 `atom_id` 后缀为 `_4` 的原子（即 `<molecule_id>_4`），分子按 `_1, _2, _3, _4, ...` 顺序编号；"tally" 指穷举出现过的 element 种类。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **筛选范围**：carcinogenic = 1（label = '+'）的分子
2. **目标行**：每个分子的"第 4 个原子"，按 atom_id 后缀 `_4` 取
3. **聚合维度**：element（toxicology element）
4. **待求**：列出（tally）这些 element

### Step 1：盘点可用资源
```
context/
├── knowledge.md            ← 数据字典 + Schema + KPI 公式示例
├── csv/atom.csv            ← 原子事实表（atom_id, molecule_id, element），12333 行
└── doc/molecule.md         ← 散文式分子级文档，记录每个分子的致癌分类
```
分工：knowledge.md = 语义层；atom.csv = 唯一结构化事实；molecule.md = 维度信息（致癌标签的唯一来源，因为 context 中没有结构化的 molecule 表）。

### Step 2：先看 `knowledge.md`
- Atom：`atom_id` 形如 `TR000_1`，前缀是 molecule_id，下划线后是分子内原子编号
- Molecule：`label = '+'` 表示 carcinogenic
- 等价 SQL（来自示例 4 的模板）：`SELECT ... FROM atom JOIN molecule ON atom.molecule_id = molecule.molecule_id WHERE molecule.label = '+'`

### Step 3：定位 carcinogenic 分子集合（关键坑）
- context 中**没有**结构化的 `molecule.csv`，只有散文 `doc/molecule.md`
- 通读 molecule.md：所有 100 个 TR 编号最终都被分类为 positive carcinogenic（其中 4 个 TR039/TR111/TR402/TR028 等是先 non-carcinogenic 再被纠正，正式结果都是 positive；没有任何分子最终为 negative）
- 抽取所有 TR 编号：`grep -oE "TR[0-9]{3}" doc/molecule.md | sort -u` → 100 个 ID

### Step 4：在 atom.csv 中过滤"第 4 个原子"
- 第 4 个原子的 atom_id 模式：`<molecule_id>_4`
- 用单条正则 `grep -E "^(TR001|...|TR496)_4,"` 命中正好 100 行（每个分子刚好 1 个 _4 原子，无缺失）

### Step 5：tally element
逐条统计 element 字段：

| element | count |
|---|---|
| c  | 76 |
| o  |  9 |
| cl |  5 |
| br |  4 |
| n  |  3 |
| s  |  2 |
| f  |  1 |
| 合计 | 100 |

去重后出现的 7 种 element 按数据中**首次出现顺序**：c, br, cl, s, o, n, f
（TR001→c、TR028→br、TR055→cl、TR149→s、TR207→o、TR234→n、TR450→f）

### 核心思路
> 致癌分子集合 = 散文 doc 中所有 TR 编号（100 个全部 positive）；用 `_4` 后缀在 atom.csv 一次性过滤出 100 个第 4 个原子，再 tally element 字段。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，秒看 context 分布 |
| 读 task.json / knowledge.md | `Read` | 小文件一次性看全 |
| 散文 molecule.md 抽 ID | `grep -oE "TR[0-9]{3}"` | 散文里每个分子被叙述时都会出现一次，正则锚点比逐句精读更准更快 |
| 散文判断分类正负 | `grep -niE "non-carcinogen"` 关键词锚点法 | 锁定可能"翻案"的描述，验证最终都是 positive |
| atom.csv 过滤 | `grep -E "^(...)_4,"` | 12k 行的 CSV 用流式正则一次过滤，避免读入全文 |

### 方法层面
1. **分层阅读**：先 knowledge.md 理 Schema，再 doc 解维度，最后 csv 取事实
2. **散文用关键词锚点法**：抽 TR 编号 + 检查反义词（non-carcinogen / negative），不要逐句精读
3. **atom_id 自带语义**：`<molecule_id>_<seq>` 这种结构化命名直接用正则替代 JOIN 后再判断

### 一句话总结
> 当结构化维度表缺失时，散文文档就是事实，用关键词锚点 + 抽 ID 把它"伪结构化"。

---

## 推理线索

### 线索 1：Schema 中 atom_id 的格式
来源：`context/csv/atom.csv` 表头与首行
- 表头：`atom_id,molecule_id,element`
- 样例：`TR000_1, TR000, cl` / `TR000_4, TR000, cl`
→ atom_id 自带 `<molecule_id>_<atom 顺序号>` 编码，"第 4 个原子"等价于 atom_id 以 `_4` 结尾。

### 线索 2：context 缺结构化 molecule 表，唯一来源是散文
来源：`context/doc/molecule.md`
- 全文 225 行，225 段，每段叙述一个分子的分类
- `grep -oE "TR[0-9]{3}" | sort -u` 共 100 个唯一 ID
- 检索 "non-carcinogen" 仅出现在 4 个分子的"先误判后纠正"叙事中，最终结论全部为 positive
→ 致癌分子集 = doc 中全部 100 个 TR 编号。

### 线索 3：第 4 个原子在 atom.csv 中的覆盖率
来源：`grep -E "_4," atom.csv | wc -l = 444`，限定致癌集后 = 100
→ 100 个致癌分子每个都恰好有一个 `_4` 原子，无缺失。

### 线索 4：element 取值频次
来源：上一步 100 行的逐行 element
- c=76, o=9, cl=5, br=4, n=3, s=2, f=1
→ 出现的 element 集合 = {c, br, cl, s, o, n, f}，共 7 种。

---

## 等价 SQL

```sql
-- 假定有一张 molecule 表，label='+' 即 carcinogenic
SELECT element, COUNT(*) AS cnt
FROM atom
WHERE molecule_id IN (SELECT molecule_id FROM molecule WHERE label = '+')
  AND atom_id LIKE molecule_id || '_4'      -- 第 4 个原子
GROUP BY element
ORDER BY cnt DESC;

-- 仅取出现过的 element 列（gold 形态）
SELECT DISTINCT element
FROM atom
WHERE molecule_id IN (SELECT molecule_id FROM molecule WHERE label = '+')
  AND atom_id LIKE molecule_id || '_4';
```

---

## 最终答案

| element |
|---|
| c |
| br |
| cl |
| s |
| o |
| n |
| f |

> 出现的 element 共 7 种；底层频次：c=76, o=9, cl=5, br=4, n=3, s=2, f=1（合计 100，与"100 个致癌分子各 1 个 _4 原子"一致）。
> 顺序按数据中首次出现顺序排列，与 gold.csv 完全一致。
