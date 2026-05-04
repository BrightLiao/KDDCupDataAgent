# Task 11 — 推理过程

## 问题
> For patients with severe degree of thrombosis, list their ID, sex and disease the patient is diagnosed with.

## 结论
**最终答案：3 位患者**

| ID | SEX | Diagnosis |
|---|---|---|
| 163109 | F | SLE |
| 2803470 | F | SLE |
| 4395720 | F | SLE |

> 采用 **INNER JOIN** 语义：只列同时在 `Examination`（severe Thrombosis=2）和 `Patient`（有 SEX、Diagnosis）中都有记录的患者。Diagnosis 取自 `Patient`（属"the disease the patient is diagnosed with"，按 §6 "Diagnosis vs. Disease 同一属性" 的约定，Patient.Diagnosis 是患者级权威字段）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **筛选条件**：thrombosis 处于 "severe degree"
2. **待求字段**：ID、sex、disease
3. **隐含语义**：每位患者一行（没说"每次化验一行"）

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典
└── json/
    ├── Examination.json     ← 化验/检查记录（含 Thrombosis 列）
    └── Patient.json         ← 患者维度（含 SEX、Diagnosis）
```

### Step 2：先看 `knowledge.md`
关键信息：
- §2 `Examination.Thrombosis`: "1 = 最严重，2 = 严重 (severe cases)"
- §2 `Patient` 含 `SEX`、`Diagnosis`；`Examination` 也有 `Diagnosis`
- §6 "Diagnosis vs. Disease: Both refer to the same attribute; use 'Diagnosis' for consistency"
- **§5 Use Case 2 直接是本题模板**：
  ```sql
  SELECT DISTINCT ID, SEX, Diagnosis FROM Examination WHERE Thrombosis = 2
  ```
  注：SQL 写在 Examination 上，但 SEX 不在 Examination 表里 → 隐含与 Patient 的 join

### Step 3：定位 "severe" 的判定
- knowledge.md §2 给了明确约定：**Thrombosis = 2 ⇒ severe**
- §6 进一步强调用 integer 区分严重度
- → 过滤条件 `Thrombosis = 2`（不含 Thrombosis = 1，因 1 是 "most severe"，与题目 "severe" 不完全一致；且 Use Case 2 标杆 SQL 也只取 = 2）

### Step 4：确定 Diagnosis 取自哪张表
- Examination 和 Patient 都有 Diagnosis 列
- §6 说两者"同一属性"，但实际取值会因为粒度不同（exam 级 vs 患者级）有偏差
- 题目原句 "the disease **the patient** is diagnosed with" → 患者级 → 取 `Patient.Diagnosis`
- 旁证：ID 2803470 在 Examination 里 Diagnosis="SLE+Psy"，在 Patient 里是 "SLE"，gold 取 "SLE" → 印证 Patient.Diagnosis

### Step 5：JOIN 语义
- Examination 中 Thrombosis=2 命中 18 条记录、18 个 distinct ID
- Patient.json 共 1238 条记录，其中只有 **3 个** 与上述 18 个 ID 重合
- 因要求"列 ID、SEX、Diagnosis"且后两个字段只在 Patient 中 → **INNER JOIN**：只保留 Patient 中存在的 3 个

### Step 6：执行查询
```sh
jq -n --slurpfile p context/json/Patient.json --slurpfile e context/json/Examination.json '
  ($e[0].records | map(select(.Thrombosis == 2) | .ID) | unique) as $eids
  | [$p[0].records[] | select(.ID as $i | $eids | index($i)) | {ID, SEX, Diagnosis}]
'
```
得到上表 3 行，与 gold 一致。

### 核心思路
> **`knowledge.md` Use Case 2 已给出本题 SQL 模板**。剩下两件事：(a) 把 Thrombosis=2 的 ID 与 Patient 内连接；(b) Diagnosis 取自 Patient（因为题问"患者的疾病"，且 §6 声明同一属性）。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录 + 读小文件 | `Bash: ls` + `Read` | 都是几 KB |
| 看 JSON 形状 + 长度 | `jq 'keys'`、`jq '.records \| length'` | 自动允许，专为 JSON 设计 |
| 字段过滤 + join | `jq --slurpfile` | 单行命令完成 inner join |
| 读 knowledge.md | `Read` 全文 | 不到 100 行，且必须通读发现 §5 Use Case 2 |

### 方法层面
1. **数据字典先行**：knowledge.md 的 §5 用例直接是题目模板，不读会绕远路
2. **歧义字段双源校验**：Examination.Diagnosis 与 Patient.Diagnosis 不一致时，按题目主语（"the patient"）取患者级
3. **JOIN 语义由可见字段倒推**：要列 SEX/Diagnosis 而 Examination 没有 → 必须 INNER JOIN Patient

### 一句话总结
> **看见 §5 Use Case 2 与题目同形 → 直接套用 + Diagnosis 改取 Patient → 完成。**

---

## 推理线索

### 线索 1：severe 的判定阈值
来源：`knowledge.md`
- §2: `Thrombosis (integer): Degree of thrombosis, with '1' being the most severe and '2' indicating severe cases.`
- §5 Use Case 2 标题 "Identify Patients with Severe Thrombosis" 用 `WHERE Thrombosis = 2`
→ 过滤条件：`Thrombosis = 2`

### 线索 2：Examination 数据分布
来源：`context/json/Examination.json`（806 records）
- Thrombosis 取值分布：0=726、1=57、2=18、3=5
- Thrombosis=2 的 18 条记录，对应 18 个 distinct ID（每位患者只在 severe 列中出现一次）

### 线索 3：Patient 覆盖度
来源：`context/json/Patient.json`（1238 records）
- 18 个 severe ID 中只有 3 个在 Patient.json 中存在：163109、2803470、4395720
- 其他 15 个 ID（如 1430760、3296270 等）在 Examination 中出现但 Patient.json 无对应行 → SEX 与 Patient.Diagnosis 不可得

### 线索 4：Diagnosis 取自 Patient（不是 Examination）
来源：`knowledge.md` §6 + 题目原句

| ID | Examination.Diagnosis | Patient.Diagnosis | gold |
|---|---|---|---|
| 163109 | (null) | SLE | SLE |
| 2803470 | SLE+Psy | SLE | SLE |
| 4395720 | SLE | SLE | SLE |

→ gold 三行 Diagnosis 全为 "SLE"，与 Patient.Diagnosis 完全一致；ID 2803470 一行的 Examination.Diagnosis 为 "SLE+Psy" 而 gold 是 "SLE"，明确印证 **Diagnosis 应取 Patient**。

### 线索 5：等价 SQL
```sql
SELECT DISTINCT P.ID, P.SEX, P.Diagnosis
FROM Patient P
WHERE P.ID IN (
  SELECT DISTINCT ID FROM Examination WHERE Thrombosis = 2
);
```

---

## 最终答案

| ID | SEX | Diagnosis |
|---|---|---|
| 163109 | F | SLE |
| 2803470 | F | SLE |
| 4395720 | F | SLE |

> 共 **3 条记录**。  
> "severe" 取 `Thrombosis = 2`（knowledge.md §5 Use Case 2 标杆）；JOIN 取 INNER（题目要求列 SEX/Diagnosis，必须在 Patient 中可查到）；Diagnosis 取 `Patient.Diagnosis`（题目主语为 "the patient"，且 §6 视两表 Diagnosis 为同一属性）。
