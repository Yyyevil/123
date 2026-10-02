# dsh_project — PDF/图片 通用表格提取（多模态）

三种能力，四个入口脚本：

| 脚本 | 用途 |
|---|---|
| `read_pdf.py` | 纯读取：pdfplumber 把 PDF 文本打印到终端 |
| `extract_info.py` | 固定字段：DeepSeek **文本**模型抽「姓名/电话/邮箱/日期」→ 纯 JSON |
| `batch_process.py` | 固定字段批处理：遍历 `data\` → `employees.xlsx` |
| `batch_extract.py` | **通用表格提取**：遍历目录下的 **PDF/图片** → 视觉模型识别**任意表格** → 动态多表 Excel |

## 通用提取（batch_extract.py）怎么工作

```
PDF / PNG / JPG
   ↓  pypdfium2 渲染（PDF 每页 → 图片）
多页图片一起送模型（同一张表跨页会合并）
   ↓  DeepSeek 视觉模型 deepseek-flash（OpenAI 兼容接口）
动态 JSON：{"表名": {"表头": [...], "数据": [{列: 值}, ...]}}
   ↓  pandas（列完全由模型决定，不写死任何字段）
output\extracted_tables.xlsx
   ├─ sheet「汇总索引」：每个文件识别到哪些表、多少行、状态
   └─ 每张表一个 sheet，同名表跨文件自动合并，多余列补空
```

## 目录结构

```
D:\dsh_project
├─ .venv/                     # 虚拟环境（Python 3.12）
├─ data/                      # 固定字段批处理的输入（4 个档案 PDF）
├─ examples/
│  └─ in/                     # 通用提取输入（6 个不同形态的样例）
│     ├─ invoice_table.pdf          # 带表格的 PDF（商品清单，5 列）
│     ├─ two_tables.pdf             # 一页含 2 张表（销售明细 + 员工信息）
│     ├─ profile_record.pdf         # 档案型键值对（无表格线）
│     ├─ price_tag_handwritten.png  # 模拟手写价签账单
│     ├─ sales_table_screenshot.png # 模拟屏幕截图表格
│     └─ meeting_notes_no_table.png # 纯段落、无表格（验证防崩溃）
├─ output/
│  ├─ uploaded/               # 网页上传的文件会先落盘在这里（按批次分目录）
│  ├─ web/                    # 网页每次提取生成的 Excel 副本
│  ├─ extracted_tables.xlsx   # 命令行通用提取产物（多表）
│  └─ extracted_tables.json   # 逐文件原始 JSON
├─ app.py                     # ⭐ Streamlit 网页界面
├─ .streamlit/config.toml     # Streamlit 主题与端口配置
├─ read_pdf.py
├─ extract_info.py
├─ info_extractor.py          # 文本模型抽取逻辑 + Prompt 常量
├─ multimodal_extractor.py    # 多模态核心：渲染 / 调用 / 解析 / 动态 Excel
├─ batch_process.py           # 固定字段批处理（旧）
├─ batch_extract.py           # 通用表格批处理（新）
├─ examples_gen.py            # 生成 examples/in 里的 6 个样例
├─ tests/test_extract.py      # 41 项离线单元测试（不联网）
├─ tests/test_app.py          # 12 项界面测试（Streamlit AppTest，不联网）
├─ tests/test_app_e2e.py      # 模拟「点击开始提取」的端到端测试（会调 API）
├─ requirements.txt
└─ README.md
```

## 0. 网页界面（推荐入口）

```cmd
cd /d D:\dsh_project
.venv\Scripts\activate.bat
set DEEPSEEK_API_KEY=sk-xxxxxxxx
streamlit run app.py
```

然后浏览器打开 **http://127.0.0.1:8501**（无头环境下服务也会自动监听这个地址）。

界面功能：

- 顶部大标题「智能文档表格提取器」，渐变字色。
- **拖拽上传区**：支持一次拖入多个 PDF / JPG / PNG / WebP 等，图片会直接显示缩略图。
- 上传的文件**先落盘**到 `output\uploads\<时间戳>\`，界面上会显示保存路径。
- 点击 **🚀 开始提取**，逐个文件调用多模态提取逻辑，进度条实时显示「正在处理 N/M」。
- 结果区展示指标卡（上传文件数 / 识别到表格 / 累计数据行 / 跳过数）、每张表的**数据预览标签页**，
  以及 **⬇️ 下载 Excel 表格** 按钮（同时可下载 JSON 和单表 CSV）。
- 侧边栏可调：API Key、视觉模型、额外提示、宽表/长表布局、渲染清晰度、间隔秒数、
  列名归一开关，以及「清理历史上传与结果」。

命令行与网页的关系：

| 场景 | 用什么 |
|---|---|
| 日常用鼠标操作、要预览 | `streamlit run app.py` |
| 批量脚本、定时任务、CI | `python batch_extract.py` |
| 只要固定四字段（姓名/电话/邮箱/日期） | `python batch_process.py` |

两者共用同一套提取逻辑（`multimodal_extractor.py`），改一处两边都生效。

## 1. 激活虚拟环境

```cmd
cd /d D:\dsh_project
.venv\Scripts\activate.bat
```

PowerShell：`.venv\Scripts\Activate.ps1`　Git Bash：`source /d/dsh_project/.venv/Scripts/activate`

## 2. 配置 API Key

按 `--api-key` → 环境变量 `DEEPSEEK_API_KEY` → 项目 `.env` 的顺序查找。

```cmd
set DEEPSEEK_API_KEY=sk-xxxxxxxx
```

```powershell
$env:DEEPSEEK_API_KEY="sk-xxxxxxxx"
```

## 3. 运行

```cmd
:: 生成样例（如果 examples\in 是空的）
python examples_gen.py examples\in

:: 通用提取：PDF + 图片一起处理，动态生成多表 Excel
python batch_extract.py
python batch_extract.py --input examples\in --output output\extracted_tables.xlsx --json output\extracted_tables.json

:: 常用参数
python batch_extract.py --hint "这是一批超市价签"   :: 给模型额外提示（也能用来统一表名，便于合并）
python batch_extract.py --delay 2                   :: 每个文件间隔 2 秒（防限流）
python batch_extract.py --scale 3                   :: PDF 渲染更清晰（默认 2，约 144 DPI）
python batch_extract.py --layout long               :: 档案卡型文档转成 来源文件/字段/值 三列
python batch_extract.py --no-normalize-headers      :: 关闭列名同义归一
python batch_extract.py --limit 2                   :: 只跑前 2 个文件（调试）
```

### 宽表 / 长表两种布局

字段结构差异大的文档（比如不同人的档案卡字段完全不同），宽表会膨胀出一堆空列。
这时用 `--layout long` 把它转成标准的「来源文件 / 字段 / 值」三列：

```cmd
python batch_extract.py --input data --output output\employees_long.xlsx --layout long ^
  --hint "这些文件都是员工档案，请统一使用同一个表名：员工信息"
```

结果是一张 21 行的整洁长表：

| 来源文件 | 字段 | 值 |
|---|---|---|
| employee_01.pdf | 姓名 | 张伟 |
| employee_01.pdf | 电话 | 13812345678 |
| employee_01.pdf | 邮箱 | zhangwei@example.com |
| employee_01.pdf | 入职日期 | 2023年4月10日 |
| ... | ... | ... |

脚本会自动判断哪些表属于「字段名当列名」的档案卡（列名命中`姓名/工号/部门/电话`等，或表头是`字段/值`），
只对这类表做转换，商品清单这种真正的多列表保持原样。

## 4. 实测结果（6 个不同形态样例）

```
[1/6] invoice_table.pdf ... 1 张表：商品清单(4行)
[2/6] meeting_notes_no_table.png ... 跳过：无结构化数据
[3/6] price_tag_handwritten.png ... 1 张表：价签账单(4行)
[4/6] profile_record.pdf ... 1 张表：员工信息(1行)
[5/6] sales_table_screenshot.png ... 1 张表：商品销售统计(4行)
[6/6] two_tables.pdf ... 2 张表：销售明细(3行)、员工信息(3行)

共 5 张表：商品清单(4行)、价签账单(4行)、员工信息(4行)、商品销售统计(4行)、销售明细(3行)
跳过 1 个文件（无表格）：meeting_notes_no_table.png
```

生成的 Excel 里列数**各不相同**，完全由模型识别出的表头决定：

| sheet | 列 |
|---|---|
| 商品清单 | 来源文件, 商品名称, 规格, 数量, 单价, 金额 |
| 价签账单 | 来源文件, 商品名称, 数量, 单价, 金额 |
| 员工信息 | 来源文件, 姓名, 工号, 部门, 职位, 电话, 邮箱, 入职日期, 月薪 |
| 商品销售统计 | 来源文件, 日期, 商品名称, 销量, 单价, 销售额 |
| 销售明细 | 来源文件, 商品名称, 批次号, 日期, 销量, 销售额 |

`员工信息` 这一张表由 `profile_record.pdf`（8 行键值对）和 `two_tables.pdf` 里的员工表**自动合并**成 4 行 9 列，缺的字段填空。

## 5. 测试

```cmd
python tests\test_extract.py      :: 41 项核心逻辑单元测试，不联网、不消耗额度
python tests\test_app.py          :: 12 项界面测试（Streamlit AppTest），不联网
python tests\test_app_e2e.py      :: 模拟「点击开始提取」全链路，会真实调用 API
```

`test_extract.py` 覆盖：JSON 解析、多表识别、无表格/乱码/截断 JSON 不报错、
```json 代码块剥离、列名归一、跨文件合并且不丢数据、长表转换、sheet 名合法性。

`test_app.py` 覆盖：页面能无异常渲染、大标题/上传控件/按钮/侧边栏都在、
下载用的 Excel 字节流是合法 xlsx 且包含「汇总索引」、上传落盘正确。

## 实现要点

- **不写死字段**：列名/列数完全来自模型的"表头"，脚本里没有任何字段常量。
- **视觉模型**：`deepseek-flash`（旧名 `deepseek-v4-flash-vision-exp` 由它承接），
  图片以 base64 data URL 传入，OpenAI 兼容格式，`response_format=json_object`，失败自动回退一次。
- **多表合并**：同名表 → 同一个 sheet 纵向合并；列名做同义归一（`商品/品名 → 商品名称`、`联系电话 → 电话`），
  不同列自动补空；归一表是显式映射，不做模糊匹配，避免错误合并。
- **防崩溃三层**：① 模型判定无表格 → 状态记为「跳过：无结构化数据」；② JSON 解析失败/被截断 → 返回空结果；
  ③ 任何异常都被 `extract_structured` 捕获写进状态列，整批继续跑。
- **PDF 渲染**：`pypdfium2` 按 `--scale` 渲染成 PNG（默认 2 倍≈144 DPI），
  多页文档一次请求带多张图并标注页码，跨页表格由模型合并。

## 常见问题

- **`401 Authentication Fails`**：Key 错误或已失效。
- **`Insufficient Balance`**：DeepSeek 账户余额不足。
- **表格识别不全**：调大 `--scale 3` 让渲染更清晰，或用 `--hint "这是手写单据"` 给提示。
- **同类表没合并成一张 sheet**：模型给出的表名不同（如"商品清单"vs"价签账单"）。
  列名会归一，但表名不做模糊合并（避免把不同数据的表错误混在一起），可用 `--hint` 引导表名。
- **中文在 cmd 显示乱码**：先 `chcp 65001`，或设置 `PYTHONUTF8=1`。
