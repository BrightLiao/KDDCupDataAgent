# Task 350 — 推理过程

## 问题
> Among the students from the Student_Club who attended the event "Women's Soccer", how many of them want a T-shirt that's in medium size?

## 结论
**最终答案：7**

> 语义假设：以 `attendance` 表中出现的 `link_to_member` 表示"出席过 Women's Soccer 事件"的学生集合，再用 `member.t_shirt_size = 'Medium'` 过滤。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **事件约束**：event_name = "Women's Soccer"
2. **行为约束**：该事件的 attendance 记录中作为 attendee 出现
3. **属性约束**：member.t_shirt_size = "Medium"
4. **待求**：满足以上条件的成员数（COUNT(DISTINCT member_id)）

### Step 1：盘点可用资源
```
context/
├── knowledge.md                       ← 数据字典（语义层）
├── csv/member.csv                     ← 成员维度表（含 t_shirt_size）
├── db/attendance.db                   ← attendance(link_to_event, link_to_member)
└── doc/
    ├── event.md                       ← 散文式事件文档（含 event_id ↔ event_name）
    └── event_event.md                 ← 散文式事件文档（与 event.md 同源加粗版）
```
分工：member.csv 是维度表；attendance.db 是事实表；event.md / event_event.md 是事件维度的散文式补充（结构化 event 表缺失，event_id 与 event_name 的对照只能在散文里找）。

### Step 2：先看 `knowledge.md`
关键信息：
- `member.t_shirt_size` 用于事件商品规划，是字符串字段（取值如 "Medium"、"Large"、"X-Large" 等）。
- `attendance` 表通过 `link_to_event` 关联 event，通过 `link_to_member` 关联 member。
- 没有给出 Women's Soccer 的 event_id；event 维度需从 doc 散文里抽取。

### Step 3：在散文中定位 event_id
在 `doc/event.md` 中 grep "Women's Soccer"，第 6 行明确写出：
> "Strategic Unit **rec2N69DMcrqN9PJC**, formally designated as the Women's Soccer event"

`event_event.md` 的第 7 行复述同一映射，互相印证。→ event_id = `rec2N69DMcrqN9PJC`。

### Step 4：拉出该事件的全部出席者
SQLite 查询 `attendance.db`：
```sql
SELECT link_to_member FROM attendance WHERE link_to_event='rec2N69DMcrqN9PJC';
```
返回 17 位 member_id。

### Step 5：与 member.csv 取交集，按 t_shirt_size = 'Medium' 过滤
对 17 个 member_id 逐行匹配 `member.csv`，列出 `t_shirt_size`：

| member_id | first_name | last_name | t_shirt_size |
|---|---|---|---|
| rec28ORZgcm1dtqBZ | Luisa | Guidi | **Medium** |
| recD078PnS3x2doBe | Phillip | Cullen | X-Large |
| recEFd8s6pkrTt4Pz | Matthew | Snay | Large |
| recEymrwCUKxiiosI | Adele | Deleon | **Medium** |
| recJMazpPVexyFYTc | Casey | Mason | Large |
| recL94zpn6Xh6kQii | Rafi | Mckee | **Medium** |
| recP6DJPyi5donvXL | Katy | Balentine | Large |
| recQaxyXBQG5BBtD0 | Dean | O'Reilly | **Medium** |
| recT92PyyZCGq1R68 | Emily | Jaquith | Small |
| recTjHY5xXhvkCdVT | Edwardo | Ing | **Medium** |
| recZ4PkGERzl9ziHO | Maya | Mclean | **Medium** |
| reccSUPwy30AeZLEb | Vincent | Ratcliffe | Large |
| reccW7q1KkhSKZsea | Adela | O'Gallagher | **Medium** |
| recf4UKTfipCzgcSA | Garrett | Gerke | Large |
| recjHj4BS5A541n9v | Keaton | Mccray | X-Large |
| recro8T1MPMwRadVH | Elijah | Allen | X-Large |
| recttfySfQnYb68u3 | Annabella | Warren | Large |

Medium 命中 7 人。

### 核心思路
> "事件 → attendance → member" 的两跳 join；事件名到 event_id 的映射要从散文 doc 中挖出来。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，最快摸清文件分工 |
| 读 knowledge.md（小文件） | `Read` | 一次性看全语义层 |
| 在散文 doc 里定位 event_id | `Bash: grep -in "Women's Soccer"` | 关键词锚点，避开通读冗长散文 |
| 查询 attendance | `Bash: sqlite3` | .db 原生方言，最直接 |
| join attendance 与 member.csv | `grep -E "id1|id2|..."` 多 ID 联合过滤 | 17 个 ID 直接拼正则即可，无需临时文件 |

### 方法层面
1. **Schema 反推检索目标**：先确认要的字段是 `event_id`，再到散文里定向 grep。
2. **散文文档关键词锚点法**：直接 `grep "Women's Soccer"`，看锚点周围一句话即可拿到 ID，不必逐段精读。
3. **维度表 + 事实表分离**：member.csv 为维度，attendance.db 为事实；先在事实表上拿到候选 ID，再回维度表过滤属性。

### 一句话总结
> 用 grep 做散文里的 schema 解析，用 sqlite3 做事实查询，用 grep -E 多 ID 联合过滤维度表。

---

## 推理线索

### 线索 1：Women's Soccer 的 event_id
来源：`context/doc/event.md` 第 6/96/186/276 行，`context/doc/event_event.md` 第 7/97/187/279 行
- 多处一致写出 "Women's Soccer event (rec2N69DMcrqN9PJC)"
- 事件性质：Game；地点：Campus Soccer/Lacrosse stadium；日期：2019-10-05；状态：Closed
→ event_id = `rec2N69DMcrqN9PJC`

### 线索 2：该事件的出席名单
来源：`context/db/attendance.db` 中的 `attendance` 表
- `SELECT link_to_member FROM attendance WHERE link_to_event='rec2N69DMcrqN9PJC'`
- 共 17 条出席记录（17 位独立 member_id）
→ 候选成员集合 = 17 人

### 线索 3：T-shirt 尺寸
来源：`context/csv/member.csv` 的第 6 列 `t_shirt_size`
- 17 人中 t_shirt_size = "Medium" 的有 7 人（Luisa Guidi、Adele Deleon、Rafi Mckee、Dean O'Reilly、Edwardo Ing、Maya Mclean、Adela O'Gallagher）
→ 最终答案 = **7**

---

## 等价 SQL

```sql
SELECT COUNT(DISTINCT m.member_id)
FROM member m
JOIN attendance a ON a.link_to_member = m.member_id
JOIN event e      ON e.event_id      = a.link_to_event
WHERE e.event_name = 'Women''s Soccer'
  AND m.t_shirt_size = 'Medium';
-- 结果：7
```

由于 context 没有结构化的 event 表，实际执行中 `event_name → event_id` 的映射来自 `doc/event.md`：`Women's Soccer → rec2N69DMcrqN9PJC`。

---

## 最终答案

| 字段 | 值 |
|---|---|
| event_name | Women's Soccer |
| event_id | rec2N69DMcrqN9PJC |
| 出席者总数 | 17 |
| 其中 t_shirt_size = Medium 的人数 | **7** |

> 数据来源：event_id 来自 `context/doc/event.md`；出席名单来自 `context/db/attendance.db`；t-shirt 尺寸来自 `context/csv/member.csv`。
