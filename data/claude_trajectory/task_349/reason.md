# Task 349 — 推理过程

## 问题
> What's Angela Sanders's major?

## 结论
**最终答案：Business**

> Angela Sanders 在 `member.csv` 中 `link_to_major = recxK3MHQFbR9J5uO`；该 Registry ID 在 `doc/major.md` 中对应 "Business" 专业。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：成员 Angela Sanders（first_name=Angela, last_name=Sanders）
2. **待求**：该成员的 `major_name`（专业名称）

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典（Members.major_name 由 major 表关联）
├── csv/member.csv           ← 成员事实表（含 first_name/last_name/link_to_major）
└── doc/major.md             ← 散文式维度文档：Registry ID ↔ 专业名称
```
分工：member.csv 提供成员→major 的 link，major.md 提供 Registry ID → 专业名的映射。

### Step 2：先看 `knowledge.md`
关键信息：
- Members 表的 `major_name` 通过 `major` 表关联得到
- 应使用 first_name + last_name 完整识别成员
- 本任务无需阈值定义，仅做两步关联查找

### Step 3：在 member.csv 中定位 Angela Sanders
表头：`member_id,first_name,last_name,email,position,t_shirt_size,phone,zip,link_to_major`

`grep "Angela" member.csv` 命中唯一一条：
```
rec1x5zBFIqoOuPW8,Angela,Sanders,angela.sanders@lpu.edu,Member,Medium,(651) 928-4507,55108,recxK3MHQFbR9J5uO
```
→ link_to_major = `recxK3MHQFbR9J5uO`

### Step 4：在 major.md 中查找 Registry ID
`grep "recxK3MHQFbR9J5uO" doc/major.md` 命中两处描述（line 30、line 246），均明确指向同一专业：
- "The program for **Business** (Registry ID: recxK3MHQFbR9J5uO) functions as a generalized pathway..."
- "The general **Business** program (Registry ID: recxK3MHQFbR9J5uO) is managed by the School of Applied Sciences..."

→ 专业名 = **Business**

### 核心思路
> 两步查找：先在成员表用姓名定位 link_to_major，再在散文式 major.md 用 Registry ID 反查专业名。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么这样选 |
|---|---|---|
| 看目录结构 | `Bash: ls` | 自动允许，秒看分工 |
| 读 knowledge.md | `Read` | 只有 90 行，一次看完 |
| 看 member.csv 形状 | `wc -l` + `head -1` | 仅 34 行，确认列含义 |
| 找成员行 | `Bash: grep` | 唯一姓名直接命中 |
| 找 Registry ID | `Bash: grep -n` | 散文中 Registry ID 唯一，关键词锚点最稳 |

### 方法层面
1. **Schema 反推检索目标**：先从 knowledge.md 知道成员→major 是通过 `link_to_major` 字段连接，再到 csv/doc 中执行查找。
2. **关键词锚点法**：散文式 major.md 长达 7 万字，用 Registry ID 作为锚点直接定位，不逐句精读。
3. **小文件全读，大文件 grep**：本任务两个数据文件都不算大，但仍坚持「用 grep 锁定证据行」的姿势。

### 一句话总结
> 先定位实体 ID，再用 ID 在维度文档中精确锚定。

---

## 推理线索

### 线索 1：Angela Sanders 的 link_to_major
来源：`context/csv/member.csv` line 2
- `member_id=rec1x5zBFIqoOuPW8, first_name=Angela, last_name=Sanders, link_to_major=recxK3MHQFbR9J5uO`
→ 该成员关联的专业 Registry ID 为 `recxK3MHQFbR9J5uO`

### 线索 2：Registry ID 对应的专业名
来源：`context/doc/major.md` line 30、line 246
- "The program for **Business** (Registry ID: recxK3MHQFbR9J5uO) ..."
- "The general **Business** program (Registry ID: recxK3MHQFbR9J5uO) is managed by the School of Applied Sciences..."
→ 专业名为 **Business**

---

## 等价 SQL

```sql
SELECT m2.major_name
FROM member m
JOIN major m2 ON m2.major_id = m.link_to_major
WHERE m.first_name = 'Angela' AND m.last_name = 'Sanders';
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| major_name | **Business** |
| link_to_major | recxK3MHQFbR9J5uO |
| member_id | rec1x5zBFIqoOuPW8 |

> 数据来源：`context/csv/member.csv` + `context/doc/major.md`，无外部知识依赖。
