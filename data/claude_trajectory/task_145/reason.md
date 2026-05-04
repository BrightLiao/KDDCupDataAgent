# Task 145 — 推理过程

## 问题
> Among the events attended by more than 10 members of the Student_Club, how many of them are meetings?

## 结论
**最终答案：4**

> 14 个事件出席数 > 10，其中 type='Meeting' 的有 4 个（recggMW2eyCYceNcy、recmbOVHSyzXQZpQr、reczhS8wix6Kzbp9P、recykdvf4LgsyA3wZ）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：约束
1. 事件出席人数 > 10
2. 事件 type = 'Meeting'
3. 待求：满足以上两条件的事件数

### Step 1：盘点
```
context/
├── knowledge.md
├── csv/attendance.csv     ← link_to_event, link_to_member
└── db/event.db            ← event 表（含 type）
```
attendance.csv 327 行；event.db 是 SQLite，含 type 列。

### Step 2：knowledge.md
- attendance 与 event 通过 `attendance.link_to_event = event.event_id` 关联
- type 取值范围：Meeting/Game/Election/Guest Speaker/Social/Registration/Community Service/Budget

### Step 3：聚合 + join
1. awk 在 attendance.csv 上按 event 计数，留出席 > 10 的 event_id
2. 每个 event_id 去 event.db 查 type
3. 数 type='Meeting' 的个数

```sh
awk -F',' 'NR>1 {gsub(/\r/,""); c[$1]++} END {for(e in c) if(c[e]>10) print e}' \
   context/csv/attendance.csv > /tmp/eids.txt   # 14 行
while read eid; do
  sqlite3 context/db/event.db "SELECT type FROM event WHERE event_id='$eid';"
done < /tmp/eids.txt | sort | uniq -c
```

### Step 4：结果
| type | 数量 |
|---|---|
| **Meeting** | **4** |
| Guest Speaker | 3 |
| Game | 3 |
| Social | 2 |
| Registration | 1 |
| Community Service | 1 |

### 核心思路
> **attendance 按 event 聚合 → 阈值过滤 → join event 取 type → 数 Meeting。**

---

## 阅读文档的方法与工具

| 场景 | 工具 |
|---|---|
| CSV 按 key 聚合 | `awk` 关联数组 |
| SQLite 单字段查找 | `sqlite3 DB "SELECT ..."` |
| schema 探查 | `sqlite3 DB ".schema"` |

---

## 推理线索

### 线索 1：attendance.csv 列
表头：`link_to_event, link_to_member`，每行一条出席记录。

### 线索 2：event.db schema
```sql
CREATE TABLE event (event_id TEXT PRIMARY KEY, event_name, event_date, type, notes, location, status);
```
type 共 8 种取值。

### 线索 3：14 个出席 > 10 的事件
4 Meeting · 3 Guest Speaker · 3 Game · 2 Social · 1 Registration · 1 Community Service

### 线索 4：等价 SQL
```sql
SELECT COUNT(*)
FROM event e
WHERE e.type = 'Meeting'
  AND (SELECT COUNT(*) FROM attendance a WHERE a.link_to_event = e.event_id) > 10;
```

---

## 最终答案

| 字段 | 值 |
|---|---|
| **count** | **4** |
| 满足出席阈值的事件总数 | 14 |
| 其中 Meeting 类型 | 4 |
