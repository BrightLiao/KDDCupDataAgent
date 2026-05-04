# Task 19 — 推理过程

## 问题
> List the full name of the Student_Club members that grew up in Illinois state.

## 结论
**最终答案：3 位成员**

| first_name | last_name | zip |
|---|---|---|
| Trent | Smith | 60559 |
| Tyler | Hewitt | 60089 |
| Annabella | Warren | 60047 |

> "grew up in" 取地址 zip → state 的映射；full name = `first_name + " " + last_name`（knowledge.md §2 明确"Always use both fields"）。

---

## 整体思考过程（Meta-Reasoning）

### Step 0：阅读问题，抽取约束
1. **实体**：Student_Club members
2. **筛选条件**：grew up in Illinois state
3. **待求**：full name（按 §2 = first_name + last_name）

### Step 1：盘点可用资源
```
context/
├── knowledge.md             ← 数据字典（student_club）
├── csv/member.csv           ← 成员事实表（33 行 + 表头）
└── json/zip_code.json       ← zip → state 维度（41877 条）
```
分工：
- member.csv = **事实表**（含 first_name、last_name、zip）
- zip_code.json = **维度表**（zip → state 映射）
- knowledge.md = **数据字典**

### Step 2：先看 `knowledge.md`
关键信息：
- §2 Members: `first_name, last_name`：full name 必须两者拼接
- §2 Locations: `state, county` 用作"地理标识符 for member addresses"
- 没有显式说哪个字段连接到 state，但常识 + zip_code.json 的存在 → **`member.zip` → `zip_code.zip_code` → `state`**

### Step 3：定位"grew up in"的判定路径
"grew up in" 在 schema 中没有专门字段，但唯一与"地理"相关的属性是 zip_code 间接映射出的 state。所以采用 **member.zip 反查 zip_code.state == "Illinois"**。

### Step 4：执行
```sh
# 1) 取 Illinois 所有 zip_code
jq -r '.records[] | select(.state == "Illinois") | .zip_code' \
   context/json/zip_code.json | sort -u > /tmp/il_zips.txt
# → 1590 个 zip

# 2) awk 双文件 hash join：member.zip 命中 il_zips
awk -F',' 'NR==FNR{z[$1]=1; next}
           FNR==1{next}
           ($8 in z) {print $2, $3}' \
   /tmp/il_zips.txt context/csv/member.csv
```
输出 3 行，与 gold 一致。

### 核心思路
> **把"grew up in Illinois"翻译成"member.zip 在 Illinois 所有 zip 列表内"**：先用 jq 从 zip_code.json 抽出 IL 所有 zip 做成 keys.txt，再用 awk 双文件 hash join 在 member.csv 上过滤。

---

## 阅读文档的方法与工具

### 工具层面
| 场景 | 用的工具 | 为什么 |
|---|---|---|
| 看小文件 / member.csv 全文 | `Read` / `cat` | 33 行，一次读完 |
| 大 JSON 字段过滤 | `jq -r '.records[] \| select(.state=="Illinois") \| .zip_code'` | jq 自动允许，专为 JSON 设计 |
| 两表 hash join | `awk -F',' 'NR==FNR{...; next} ...'` | 流式、零拷贝、避免 41877 条 zip 进入上下文 |

### 方法层面
1. **Schema 反推**：题目说"in Illinois state"，先确认 state 信息住在哪张表 → zip_code.json
2. **维度表先做成 keys.txt**：把 IL 1590 个 zip 落到临时文件，后面 awk 直接 hash 查找
3. **不把 41877 行 JSON 整个进上下文**：用 jq 过滤后落盘

### 一句话总结
> **JSON 维度表用 jq 抽 keys，CSV 事实表用 awk 双文件 join，全程不让大文件污染上下文。**

---

## 推理线索

### 线索 1：full name 拼接规则
来源：`knowledge.md` §2 Members
> first_name, last_name: Represents the full name of a club member. **Always use both fields** to ensure complete identification.

→ 输出列必须是 `first_name + " " + last_name`，不是单字段。

### 线索 2：state 字段所在表
来源：`knowledge.md` §2 Locations + 文件目录
- §2 Locations 提到 `state, county` 用作 member 地址的地理标识符
- 但 member.csv 表头里没有 state 列，只有 zip 列
- zip_code.json 同时提供 zip_code 和 state → **state 通过 zip 间接得到**

### 线索 3：Illinois 的 zip 集合规模
来源：`context/json/zip_code.json`
- 全表 41877 条记录
- 其中 state == "Illinois" 的有 **1590** 条 zip
- 没必要把这 1590 个 zip 进上下文，直接落到 `/tmp/il_zips.txt`

### 线索 4：member.zip 命中 IL 的成员
来源：`context/csv/member.csv` × `/tmp/il_zips.txt`
| member_id | first_name | last_name | zip |
|---|---|---|---|
| recL4aEZBZoPk9NYx | Trent | Smith | 60559 |
| recWh2lJVOT6HjChK | Tyler | Hewitt | 60089 |
| recttfySfQnYb68u3 | Annabella | Warren | 60047 |

→ 共 3 行（IL zip 都以 6 开头，与 USPS ZIP 编码规范一致）。

### 线索 5：等价 SQL
```sql
SELECT m.first_name, m.last_name
FROM member m
JOIN zip_code z ON m.zip = z.zip_code
WHERE z.state = 'Illinois';
```

---

## 最终答案

| first_name | last_name |
|---|---|
| Trent | Smith |
| Tyler | Hewitt |
| Annabella | Warren |

> 共 **3 位成员**。  
> "grew up in Illinois" 取地址 zip 落在 Illinois 州 zip 范围内（共 1590 个 IL zip）。Full name 按 knowledge.md §2 拼 `first_name + last_name`。
