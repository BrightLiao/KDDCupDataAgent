# KDDCup Demo 50 Tasks — 解题轨迹分析与 data_agent 设计建议

**分析日期**：2026-04-25
**任务数**：50（demo 集 5 个数据库：student_club、financial、superhero、formula1、codebase_community 等）
**轨迹来源**：`claude_trajectory/task_<id>/reason.md`

---

## 数据性质声明

> 本数据集是 **「带 gold 答案做的解题示范」**，不是 agent 盲跑的能力测试结果。每个 task 都允许 subagent 反复迭代直到与 gold.csv 一致，因此本报告**不讨论准确率**，只总结**解题路径中出现的通用模式、tips、踩过的坑**。
>
> 用途定位：(a) 给我们设计 data_agent 提供解题策略参考；(b) 作为后续盲评测的 reasoning 教材；(c) 工具链（awk/jq/sqlite3）使用范例。

---

## 任务难度分布

| 难度 | 数量 | 典型耗时 |
|---|---|---|
| easy | 15 | < 90s（单表 SELECT/COUNT） |
| medium | 23 | 90-150s（2-3 表 JOIN） |
| hard | 10 | 150-220s（嵌套查询、聚合分组） |
| extreme | 2 | 200s+（多步推理、需要先聚合再过滤） |

---

## 一、通用解题模式（Patterns）

### Pattern 1：「先建字典 → 再抽约束 → 再选语义 → 执行 → 自洽校验」五步法

本批次 reason.md 的步骤顺序（先抽约束再读 knowledge）是因为有 gold 兜底，可以反复纠正实体到字段的映射。**真实盲跑场景**下需要把顺序倒过来：先读完 schema/字典，再做实体抽取和谓词归属，否则约束可能挂在不存在的字段上。

修订后的循环：

```
Step 1: ls context/  →  分清事实表 / 维度表 / 数据字典 / 散文 doc
Step 2: 通读 knowledge.md  →  建立字段语义、KPI 公式、单位、合法取值
Step 3: 抽取约束（基于 Step 2 的字典做实体对齐）
        - 题面里的实体名 → context 中哪张表
        - 题面里的谓词词汇 → 哪个字段（含同源字面匹配 + 语义匹配两组候选）
        - 待求是 scalar / list / 多列
Step 4: 选择查询语义（同行 JOIN vs 对象级 EXISTS；阈值是 context 内还是外部知识）
        - 若涉及外部知识阈值 → 显式标注
        - 若候选字段有歧义 → 保留 ≥2 种映射并行计算
Step 5: 执行 awk/jq/sqlite3 查询
Step 6: 自洽校验（不依赖 gold）
        - 行数 / 数量级是否合理（与 wc -l 等粗略量级一致）
        - 候选字段映射的多个结果是否有显著差异 → 触发 ambiguity report
        - 命中率太低（如 join 后 0 行）→ 反查是否漏字段或 CRLF 之类
Step 7: 输出（list 答案必须穷举，scalar 答案带量纲）
```


→ **设计建议**：
1. data_agent 主循环固化这套 state machine，**不要让 LLM 自由发挥步骤顺序**。
2. **Step 2 必须在 Step 3 之前**：先有数据字典再做实体抽取。本批次的 reason.md 顺序（先抽约束）是被 gold 兜底惯坏的，不要照搬。

---

### Pattern 2：工具按数据规模分层

| 数据形态 | 选用工具 | 不要用 |
|---|---|---|
| 小文件（<200 行）：task.json / knowledge.md / 短 doc | `Read` | awk |
| 大 CSV（千行+）：事实表 | `awk` 流式过滤 + 聚合 | Read 全文 |
| JSON 维度表/字典 | `jq` | Python 自己解析 |
| SQLite (.db) | `sqlite3` 命令行 | 转 CSV 再 awk |
| 双表 join | `awk 'NR==FNR{m[$k]=...; next} ...'` 双文件模式 | 多次 grep + 手工合并 |

→ **设计建议**：data_agent 的工具入口要**强制根据文件类型路由**，而不是 LLM 临时决定。Python 在这套 task 里几乎没用到（无法走 allowlist）；jq 是 JSON 的最优解。

---

### Pattern 3：CSV 处理三道预处理

每次读 CSV 前都要做：

```sh
# 1. 看头
head -1 data.csv

# 2. 看规模
wc -l data.csv

# 3. 处理 CRLF（KDDCup 数据集普遍是 Windows 行尾）
awk 'BEGIN{FS=","} {gsub(/\r/,""); ...}'
```

→ **设计建议**：把 `gsub(/\r/, "")` 当成 awk 的「默认前奏」加进 prompt，否则会出现「字段值看起来一样但 == 失败」的静默失败。

---

### Pattern 4：先用 gold 反查正确语义（如果允许）

很多题目存在多种合法语义解读（例如 task_89 的「ranked second」可能是 position=2、positionOrder=2、rank=2 三种），先把候选都列出，用 gold 反查命中哪一个。

→ **盲跑场景下没有 gold**：必须**穷举所有候选语义并保留至少 2 种解释**让上层选择，不能贸然挑一种 commit。

---

## 二、踩过的坑（Pitfalls，按出现频率）

### 坑 1：CRLF 行尾导致字段比较静默失败 ★★★★★（高频）

```sh
awk -F',' '$7 == "VYDAJ"'   # 即使该行是 VYDAJ 也匹配不到，因为 $7 = "VYDAJ\r"
```

修复：所有 awk 脚本第一句 `gsub(/\r/, "")`。

涉及任务：task_25, task_38, 还有很多隐性影响。

---

### 坑 2：「对象级谓词」误用同行 JOIN ★★★★

题型：「X 的对象中有多少满足 Y」（task_344）

错误写法：
```sql
JOIN Lab ON ... WHERE WBC normal AND FG abnormal  -- 要求同一行同时满足两条件
```

正确写法（对象级 EXISTS）：
```sql
WHERE EXISTS (SELECT 1 FROM Lab L WHERE L.ID = P.ID AND L.WBC ...)
  AND EXISTS (SELECT 1 FROM Lab L WHERE L.ID = P.ID AND L.FG ...)
```

→ **设计建议**：data_agent 解析问句时，识别「主语 + 多个谓词」结构，默认走 EXISTS 而非同行 JOIN，仅当谓词显式指向同一事件（如「在同一次化验中」）才用同行 JOIN。

---

### 坑 3：散文维度文档不是结构化表的冗余 ★★★★

涉及任务：task_344

`patient_sex.csv`（92 个 ID，男性）+ `Patient.md`（散文，描述 100 个 ID，每个都标注 male）→ 两者**取并集**才是完整候选集，只取一边漏 8 个 ID。

→ **设计建议**：data_agent 的维度构建步骤要**显式合并**结构化表 + doc/*.md 中提到的 ID，不能默认前者就是全集。

---

### 坑 4：题面词汇与字段名「字面同源」时优先字面匹配 ★★★

涉及任务：task_89（"ranked" → `rank` 列，即使 knowledge.md 说 `positionOrder` 才是名次）

knowledge.md 可能给出语义解释，但 BIRD-bench 风格的 gold 标注偏向**词形对齐**：
- "ranked" → `rank` 列
- "position" → `position` 列
- "track number" → 同义匹配（`driverStandings.position`，task_86）

→ **设计建议**：当题面词与某列名同源时，先按字面匹配作为 candidate-1，再按 knowledge.md 语义作为 candidate-2，**两者都跑一遍并保留差异**。

---

### 坑 5：SUM(cost) 表面看是 expense.cost，可能等价于 budget.spent ★★

涉及任务：task_163

本地 expense.csv 是样本（缺行），SUM(cost) 算出来比 budget.spent 小。**完整数据下两者等价**，gold 用的是 budget.spent 兜底。

→ **设计建议**：当事实表与汇总表（如 expense vs budget.spent）数值不一致时，data_agent 应该**报告差异**并询问采用哪个。

---

### 坑 6：题目术语 ≠ 字段名（别名问题） ★★

例：
- task_86 「track number」实指 `driverStandings.position`
- task_163 「type of expenses」实指 `event.type`，不是 `budget.category`

→ **设计建议**：data_agent 应建立「题面词 → 候选字段集」的多对多映射，再用数据分布验证。

---

### 坑 7：SQL AVG / 聚合的 NULL 与 0 行为 ★

涉及任务：task_67

`AVG(weight)` 在 SQL 里**保留 0、跳过 NULL**。awk 自实现时要复刻这个行为，不能想当然把 0 也排除。

---

### 坑 8：列表型 gold 的 reason.md 表述方式

涉及任务：task_38（gold 是 140 个 trans_id 列表）

reason.md 倾向「报数量 + 摘录」，没把 ID 全列出来 → 评测时按 token 全列匹配会漏。

→ **设计建议**：data_agent 输出格式应区分「scalar 答案」和「list 答案」，list 答案必须穷举（用代码块包），不能只摘录。

---

## 三、Tips（高效执行小技巧）

### Tip 1：double-file hash join 模板

```sh
awk -F',' 'NR==FNR { if(FNR>1) m[$1]=1; next }     # 加载小表到内存
           FNR==1 { next }                          # 跳过大表头
           ($1 in m) { ... }' small.csv big.csv
```

可以替代 `for id in $list; do grep ... done`，速度快 10-100 倍。

---

### Tip 2：jq 的 records 包裹模式

KDDCup 的 JSON 文件通常是 `{"table": "X", "records": [...]}`，不是裸数组。要用：

```sh
jq '.records[] | select(.year == 2008)'
```

不是 `jq '.[] | select(...)'`（会报错）。

---

### Tip 3：SQLite 当成「带索引的查询引擎」用

```sh
sqlite3 context/db/event.db "SELECT type FROM event WHERE event_id = 'X';"
```

比把 db dump 成 CSV 再 awk 快得多，且支持复杂 JOIN/GROUP BY。

---

### Tip 4：用 `comm` 比对两个 ID 集合

```sh
comm -23 <(sort a.txt) <(sort b.txt)   # a 有 b 没有
comm -13 <(sort a.txt) <(sort b.txt)   # b 有 a 没有
comm -12 <(sort a.txt) <(sort b.txt)   # 交集
```

用于检验「散文文档 ID 是否都在结构化表里」之类问题。

---

### Tip 5：gold 列名暗示 SQL 结构

gold.csv 第一行经常是 `T1.foo, SUM(T3.bar)` 之类带 alias 的表头。这暗示：
- 涉及多少张表（T1 / T2 / T3）
- 用了什么聚合函数

→ data_agent 在写查询前可以先解析 gold 列名（如果可获取），快速锁定查询结构。

---

## 四、对 data_agent 设计的指导

### 建议 1：把修订后的「5+2 step 协议」固化进 state machine

不要让 LLM 自由决定步骤顺序。盲跑生产版本的 state machine：

```
[Step 1 inventory] → [Step 2 read knowledge.md & build dict]
                          ↓
                   [Step 3 extract constraints with dict]
                          ↓
                   [Step 4 pick semantics + handle ambiguity]
                          ↓
                   [Step 5 execute via awk/jq/sqlite3]
                          ↓
                   [Step 6 sanity check (NOT gold check)]
                          ↓
                   [Step 7 emit answer + ambiguity report]
```

每步有 enter/exit 检查（如 Step 3 必须引用至少 1 个 Step 2 提到的字段名；Step 4 必须显式标注是否使用外部知识）。

**最关键的两条：**
- **Step 2 在 Step 3 之前**：先建字典再抽实体，避免约束挂到不存在的字段上
- **Step 6 不是 gold 校验**：盲跑没有 gold，要靠自洽性（数量级、空集警报、多映射 diff）发现问题

---

### 建议 2：工具按数据类型路由，禁止 fallback 到 Python

`Read` / `awk` / `jq` / `sqlite3` 四件套覆盖 KDDCup 全部 case。Python 既不在 allowlist 里也不必要。data_agent 的 tool dispatcher 应根据文件后缀强制路由：

| 后缀 | 唯一允许的工具 |
|---|---|
| .csv (大) | awk |
| .csv (小, <200 行) | Read 或 awk |
| .json | jq |
| .db | sqlite3 |
| .md | Read |

---

### 建议 3：在 prompt 中显式列出三个高频坑

把以下三条写进 data_agent 的 system prompt 顶部：

> 1. **CRLF**：所有 awk 在比较字段前先 `gsub(/\r/, "")`
> 2. **维度并集**：当存在多份维度信息（结构化 CSV + 散文 doc），默认取并集
> 3. **对象级谓词用 EXISTS**：「X 中有多少满足 Y 和 Z」用对象级 EXISTS，不要同行 JOIN

这三条覆盖了本批次最容易出错的三类失误。

---

### 建议 4：盲跑场景下保留多解释路径

不能用 gold 反查时，遇到歧义（如「ranked」、「track number」、「type」）应：
1. 列出所有 candidate 字段
2. 各跑一次得到答案
3. 在最终输出中**并列展示**多种解释及其数值，由上层（用户/评估器）选择

而不是单选一个 commit。

---

### 建议 5：list 型 / scalar 型答案分别处理

输出格式契约：
- scalar：一行 `{"answer": 42}`
- list：完整数组 `{"answer": [id1, id2, ..., idN], "count": N}`，禁止「报总数 + 摘录」

便于自动评测。

---

### 建议 6：gold 列名解析作为 hint 机制（可选）

当 evaluator 允许把 gold 列名（不是值）作为 schema hint 给 agent 时，可以提前告诉 agent 「答案是 1 列还是多列、聚合函数是什么、涉及多少张表」。这能大幅提升 agent 的命中率，且不算泄漏答案。

---

### 建议 7：把 demo 50 题的 reason.md 当成 few-shot 池

按 (database, 难度, 查询模式) 分类，盲评测时根据题面相似度检索 1-3 个 reason.md 注入 prompt。这是最直接的能力提升手段。

---

## 五、Baseline 工具栈的具体问题

> 来源：`kddcup2026-starter-kit/src/data_agent_baseline/tools/`（filesystem.py / python_exec.py / sqlite.py / registry.py）+ `agents/prompt.py / react.py`
> 对比对象：本批次 50 task 在 Claude Code 下用 `awk / jq / sqlite3 / Read` 实际做的操作

### 5.1 工具能力缺口

#### 缺口 1：没有 grep/awk 等价物 ★★★★★（最致命）

baseline 提供了 `read_csv(path, max_rows=20)`，但**没有任何按谓词过滤、按列聚合、流式扫描的能力**。本批次 50 task 中至少 35 个任务依赖 awk 的过滤+聚合（`awk -F',' '$N==X {s+=$M} END{print s}'`），这些在 baseline 下只能 fallback 到 `execute_python` 跑 pandas。

**后果**：
- task_169（38 万行 yearmonth.csv 求 SME 段年消费均值）：execute_python 必须 read_csv 全表 → 加载 + groupby，30s 超时是实打实的风险
- task_38（找 140 笔 trans_id）：必须 Python 全表扫描，没有 `awk '$type=="VYDAJ"&&$op=="VYBER"'` 这种轻量过滤
- task_283 / task_303 / task_396 等比例/百分比类任务：本质上 `count(filter)/count(all)`，理应 5 行 awk 解决

**建议**：增加 `grep_csv(path, where: "col==val", group_by, agg)` 类的轻量过滤工具；或直接暴露 `awk_filter`。

---

#### 缺口 2：read_csv 默认 max_rows=20 + 无 row_count 提示 ★★★★

实际执行轨迹里，**LLM 第一件事永远是 `wc -l` 看规模**。baseline 的 read_csv 返回 row_count（实际数据行数），但 max_rows=20 默认值 + 没有任何 dtype/列分布信息：
- LLM 看到前 20 行不知道总规模 → 会盲目尝试拉更多
- 没有 `head` + `tail` 同时返回的能力（KDDCup 数据常按时间排序，看尾巴能判断时间跨度）
- 没有 column dtypes / null 比例 / unique 值数等 EDA 信息

**建议**：read_csv 默认应返回：
- header + row_count + 文件 byte size
- 前 5 行 + 后 5 行
- 每列：dtype 推断、null 数、unique 数（截断到 ≤20 个 distinct value 时列出来）

把「探查」和「读数据」分成两个工具：`profile_csv` vs `read_csv_rows(filter=...)`。

---

#### 缺口 3：read_json 用 max_chars 切，破坏 JSON 结构 ★★★★

```python
preview = json.dumps(payload, ensure_ascii=False, indent=2)
return preview[:max_chars]  # 在 record 中间剁一刀
```

实际执行轨迹里，**所有 JSON 都用 jq 按字段过滤**（如 `jq '.records[] | select(.year==2008)'`）。baseline 强制全文 dump + 字符截断 → 大 JSON 直接废了。

**典型受害**：
- task_89 / task_292 的 races.json（数千条 race），4000 字符切完只能看到前 ~10 条
- 任何 `{"records": [...], "table": "X"}` 包裹模式 → 截断后破坏 JSON parseability

**建议**：read_json 改成 `query_json(path, jq_expr)`，把 jq 选择器作为 first-class 参数。或者直接接受 JSONPath。

---

#### 缺口 4：read_doc 同样字符截断，无 section 锚点 ★★★

knowledge.md 普遍 5-10KB，包含 §1 介绍 / §2 实体 / §3 KPI / §4 约束 / §5 用例。max_chars=4000 会把 §4-5（最关键的阈值定义和示例 SQL）截掉。

**建议**：
- 增加 `read_doc(path, section: str)` 按 markdown heading 锚点读
- 或返回 outline + 按需展开

---

#### 缺口 5：execute_python 的 30s 超时 + 冷启动 ★★★★

```python
EXECUTE_PYTHON_TIMEOUT_SECONDS = 30
process = multiprocessing.Process(...)  # 每次都新开进程
```

每次 `execute_python` 调用都是 fresh process：
- pandas 冷启动 import 就要 ≈1-2s
- 大 CSV 读取（如 yearmonth.csv 380K 行）pd.read_csv 又要几秒
- 跨步骤无法保留 DataFrame，每次重读
- 30s 对中等聚合是真的紧

namespace 只预注入 `Path`，连 `pd` / `np` / `sqlite3` / `re` 都要 LLM 自己 import。

**建议**：
- 提供持久 kernel（类 Jupyter），跨 step 保留变量
- 预导入 `pandas as pd`, `numpy as np`, `sqlite3`, `pathlib`, `json`, `re`
- 缓存常用 CSV 的 pd.read_csv 结果（按 mtime）
- 超时改为可配置，默认放宽到 120s
- 或者干脆用 DuckDB 作为查询引擎（直接 `SELECT ... FROM 'file.csv'`），比 pandas 更适合 ad-hoc 查询

---

#### 缺口 6：sqlite 工具无 ATTACH，无法跨 db join ★★★

```python
def execute_read_only_sql(path, sql, *, limit=200):
    with _connect_read_only(path) as conn:  # 单 db 连接
        ...
```

每次 call 单连接、单 db 文件。但 task_145、task_163 同时用了 event.db + attendance.csv + budget.json — 这种**跨数据源 join** 在 baseline 下只能：
1. SQL 查 db 拉一批 ID
2. Python 读 CSV/JSON
3. Python 自己合并

而 sqlite3 命令行可以 `ATTACH DATABASE 'a.db' AS a; CREATE TABLE b AS SELECT * FROM read_csv('b.csv'); SELECT a.x, b.y FROM a JOIN b ...` 一步搞定。

**建议**：
- 用 DuckDB 替换或并存 sqlite — DuckDB 原生支持 `SELECT FROM 'file.csv'` / `'file.json'`，跨格式 join 一步到位
- 或 sqlite 工具支持 ATTACH 多个 db + load CSV virtual table

---

#### 缺口 7：sqlite 的 read-only 检查太弱

```python
normalized_sql = sql.lstrip().lower()
if not normalized_sql.startswith(("select", "with", "pragma")):
    raise ValueError(...)
```

只检查首 token，多语句（`SELECT 1; ATTACH DATABASE ...`）能逃过。虽然 sqlite3 默认只执行第一条，但 connection 是 read-only mode 兜底所以 OK，但仍是 sloppy 代码。

**建议**：用 sqlite3 的 `executescript` + 真正的 SQL parser 校验所有 statement。

---

#### 缺口 8：inspect_sqlite_schema 不返回 row_count / 样本值 ★★

LLM 需要先 `inspect_sqlite_schema` 看表结构，再 `SELECT COUNT(*) FROM ...` 看大小，再 `SELECT * LIMIT 5` 看样本 — **3 个 step**。

**建议**：inspect 一次返回所有表的 row_count + 前 3 行样本 + 各列 distinct count（小列直接展示 distinct values）。

---

### 5.2 默认参数 / Prompt 设计的问题

#### 问题 1：max_steps=16 对 medium+ 难度严重不足 ★★★★

```python
@dataclass(frozen=True, slots=True)
class ReActAgentConfig:
    max_steps: int = 16
```

实际轨迹里，medium 题平均 step 数：
- list_context (1) + read knowledge.md (1-2) + inspect schema (1) + 2-3 探索性 read (2-3) + 3-5 SQL/Python 查询 (3-5) + answer (1) = **11-15 step**

加上任何错误/重试就爆 16。task_344 / task_163 这种需要并行多语义验证的，必须 ≥ 25 step。

**建议**：max_steps 默认 30；对 hard/extreme 难度提到 50。

---

#### 问题 2：observation 全文塞回 context，越跑越胖 ★★★★

每个 step 的 observation（CSV 前 20 行 / JSON dump / SQL 200 行结果）都 json.dumps 后塞回 prompt history。前 5 步还行，跑到 step 12 时 prompt 已经几万 token。

**建议**：
- observation 中长结果用 hash + reference，让 LLM 用 `recall(hash)` 取回；或截断到 top-5 + total count，详情按需重查
- 或限制 observation 大小（>4KB 自动截断 + 提示「use a more specific query」）

---

#### 问题 3：prompt 完全没提任何「数据特性警告」★★★★

`REACT_SYSTEM_PROMPT` 通篇是 ReAct 协议的 housekeeping，没有：
- CRLF 警告
- 同名字段歧义提示
- 维度文档可能不冗余的提醒
- 大文件的处理建议（>10K 行不要 read_csv 全文，用 SQL）
- 列名 vs 题面词的字面/语义对齐策略
- python_exec 预导入了什么 / 没导入什么

LLM 在「干净的 ReAct prompt + 通用 Python」下，几乎注定要踩本报告第二节列的坑。

**建议**：把本报告 §三「三个高频坑」+ §四「five-step 协议」直接缝进 system prompt。

---

#### 问题 4：answer 必须是 columns+rows 表格，scalar 答案被迫包成单格 ★★

```python
if not isinstance(columns, list) or not columns or ...:
    raise ValueError("answer.columns must be a non-empty list of strings.")
```

scalar 答案（如 task_67 的 60.78、task_196 的 1.0）只能写成 `{"columns":["avg"],"rows":[["60.78"]]}` — 多了模板压力，列名怎么取还得猜（gold.csv 列名是 `AVG(weight)` 这种带 SQL 函数的）。

**建议**：answer 工具支持 scalar / list / table 三种 shape，列名缺失时自动用 `value` / `value_1, value_2`，由 evaluator 做列名宽容比对。

---

#### 问题 5：错误恢复机制弱 ★★

```python
except Exception as exc:
    observation = {"ok": False, "error": str(exc)}
    # ... 仍然占用一个 step 名额
```

- LLM JSON 格式错误 → 浪费一个 step
- 工具 raise → 浪费一个 step
- 没有 retry / repair 机制（如 JSON repair lib）

**建议**：parse_model_step 失败时自动重试一次（带 error feedback），不计入 step 配额。

---

#### 问题 6：observation 用 JSON dumps 嵌一坨 ★

```python
def build_observation_prompt(observation: dict) -> str:
    rendered = json.dumps(observation, ensure_ascii=False, indent=2)
    return f"Observation:\n{rendered}"
```

CSV preview 在 JSON 里被双层 escape，可读性差，token 消耗高。

**建议**：表格类 observation 用 markdown table 渲染；error 用 stderr-style 文本。

---

### 5.3 优先级总结（如果只能改 5 处）

| 优先级 | 改动 | 预期收益 |
|---|---|---|
| **P0** | 引入 DuckDB 作为统一查询引擎，替代 read_csv + execute_python 的过滤聚合场景 | 一次性解决缺口 1、2、5、6 |
| **P0** | 把 §三「三个高频坑」缝进 system prompt | 消除 CRLF / 维度并集 / EXISTS 三类系统性失误 |
| **P1** | max_steps 默认 30 + observation 截断/引用机制 | 解决 context 爆炸 + 步数不够 |
| **P1** | read_json 接受 jq 表达式作为 query 参数 | 解决 JSON 截断破坏结构问题 |
| **P2** | answer 接受 scalar/list shape；inspect_sqlite_schema 一次返回 row_count + 样本 | 减少 step 浪费 |

---

## 六、各模式覆盖统计

| 模式/坑 | 涉及任务数 | 占比 |
|---|---|---|
| 大 CSV awk 双文件 join | 35+ | 70%+ |
| jq JSON 维度反查 | 20+ | 40%+ |
| sqlite3 .db 查询 | 12+ | 24%+ |
| 题面词→字段名歧义 | 8 | 16% |
| CRLF 处理 | ≈ 全部 | 100% |
| 对象级 EXISTS 必需 | 1 + 潜在多个 | - |
| 维度并集 | 1 + 潜在多个 | - |
| 显式使用外部知识并标注 | 3 | 6% |
| 写了「复盘」段（自我纠正） | 8 | 16% |

---

## 七、附录：8 个写了「复盘」的任务

这些 task 的 reason.md 末尾有详细的失败→修正过程，是最有教学价值的样本：

| Task | 关键教训 |
|---|---|
| task_25 | CRLF 行尾陷阱；cost vs spent 字段歧义 |
| task_38 | CRLF；从数据自学 enum 字典 |
| task_67 | SQL AVG 对 0 vs NULL 的处理 |
| task_80 | 同名字段（drivers.number vs qualifying.number）按所有格判定 |
| task_86 | 「track number」实指 driverStandings.position |
| task_89 | 「ranked」字面对应 rank 列，胜过 knowledge.md 语义 |
| task_163 | "type of expenses" 实指 event.type；本地表样本不全用 budget.spent 兜底 |
| task_344 | 散文文档非冗余；对象级 EXISTS；隐式使用外部知识应声明 |

→ 直接读这 8 份 reason.md 的复盘段，能拿到 80% 的有用经验。
