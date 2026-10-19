# 内容计划 JSON

`examples/lesson.json` 是可运行的格式测试样例，内容故意使用测试题，不适用于授课。将样例复制到任务目录，替换成经过核验的真实课时内容，图片路径相对于该JSON所在目录。

## 顶层

| 字段 | 类型 | 含义 |
|---|---|---|
| title | string | 文件名前缀，建议章节+课题+课时 |
| sources | array | 实际核对过的来源，见下文 |
| outline | object | 导学提纲内容 |
| paper | object | 学生卷与答案共用的题目数据 |
| slides | array | PPT按演示顺序排列的各页 |

## 文本与化学 run

需要排版的文本可以是字符串，也可以是run对象列表。字符串中只有明确包在方括号中的化学式被解析；普通文本中的数字保持正常，避免把系数和页码错误下标。

```json
{
  "字符串示例": "2[H2O]、[SO4^2-]、[Fe^3+]、[NH4+]、[Cl-]",
  "显式run示例": [
    {"text":"[H2] + [Cl2] "},
    {"text":"点燃", "condition":true},
    {"text":" 2[HCl]"}
  ],
  "同位素示例": [{"text":"C", "isotope":{"mass":12, "atomic":6}}],
  "幂示例": [{"text":"10"},{"text":"23", "sup":true}],
  "常数示例": [{"text":"N"},{"text":"A", "sub":true, "italic":true}],
  "填空示例": [{"text":"　　　　", "underline":true}]
}
```

run属性：`text`必填；可选`sub`、`sup`、`italic`、`bold`、`underline`；`charge:true`表示离子电荷，text为`2-`/`3+`/`+`等；`condition:true`时text为条件；`isotope`给出质量数mass和原子序数atomic。上/下标不能同时为true。反应条件与同位素应独立成run。

`[Fe3+]` 表意不清，必须写为 `[Fe^3+]`。复杂配位化学式、分数、根式等超出简写语法时使用显式run或经核验的图，不应让正则猜测。PPT的condition run生成可编辑的等号和居中叠排条件文字；目前仅支持无需换行的单行反应式，过长公式/条件会报错，应拆分或使用经核验图示。等宽字体Courier New须在目标阅读环境可用，并做视觉核验。

## 来源 sources

每个来源记录包括：

```json
{
  "id":"textbook-ch2",
  "category":"textbook",
  "title":"实际教材名称与版次",
  "locator":"原书第X页，PDF第Y页，第二章第二节",
  "evidence":"已核对的真实摘录或可回查原始文件位置",
  "verified":true
}
```

该示意结构中的X/Y是说明，不是可提交的真实页码。不要复制占位来源来绕过检查。category为`textbook/teacher_book/exercises/practice/exam`。ID唯一；题目用`source_ids`引用。三件套入口默认要求除practice以外四类已核实来源，以及每题至少一个已核实来源；practice可缺并在报告注明。脚本无法验证伪造的verified，不可将它当认证。

## 提纲 outline

单独生成使用 `render_outline.py`，详见 [操作流程](outline-workflow.md)；精确字段和边界以 [JSON Schema](outline.schema.json) 为准。`examples/outline.json` 可直接做格式测试。

- `title`：课题和课时，不含脚本自动附加的“导学提纲”。
- `goals`：至少一个学习目标；文本可以是字符串或扁平 run 对象数组。
- `sections`：每项包含 `title` 和非空 `blocks`，可选 `id`、`group`。
- 段落块：`{"type":"paragraph","content":"学生可执行的问题"}`。
- 表格块：`{"type":"table","headers":["反应","化合价变化"],"rows":[["2[Mg] + [O2] = 2[MgO]",null]]}`。`null` 表示空白待填；行列必须齐全。可选 `widths_cm`（列数一致，按比例缩放）和 `min_row_height_cm`（0.5至5，渲染至少0.75cm）。
- `thinking`：可选思考题数组；`schedule_note`：可选课堂安排。
- 标准化自动分配缺失的 section/block `id`；修改时从 `content.json` 读取实际 ID。ID 全文唯一，禁止自行猜测。
- 兼容旧 `sections[].paragraphs` 和 `groups[].blocks[].body`，但不允许未知内容静默丢失；新输入一律用 blocks。

表格是可编辑 Word 原生表格，支持与正文相同的化学 run。页末另有25行笔记表，不计入教学表格数。

## 试卷 paper

- `title`：学生卷标题，不含“限时练”。
- `choice`：14道单选题。
- `written`：至少1道填空/简答题，合计44分。
- `optional`：恰好2道选做题，score省略或0。

每题：

| 字段 | 要求 |
|---|---|
| stem | 非空文本或语义run列表 |
| options | 仅choice必填，恰好4个文本，对应A/B/C/D |
| answer | 非空答案，choice必须为A/B/C/D |
| explanation | 非空解析文本或run列表 |
| score | choice固定4，written正数，optional为0 |
| minutes | 正数；必做合计30至35，选做另计 |
| difficulty | 基础/中档/较难 |
| source_ids | 实际sources中ID的列表 |
| image | 可选本地题图路径，需内容正确、来源可核实 |
| work_lines | 可选1至20整数，答题空间，不应用空白顶替缺失内容 |

同一题多个小题可在stem用语义run或换行组织，各小题分数写入真实题干，总分写score。双线桥及复杂装置图通过已核实的题图提供。答案/解析只写入独立答案卷。

## 课件 slides

每页：

- `title`：字符串，32pt标题；过长报错，需拆分或缩写。
- `stage`：`启/探/析/辩/辩—自由讨论/辩—预设讨论/辩—自由展示/辩—预设展示/辩—梳理内化`之一。
- `paragraphs`：文本数组；其中每项可以是字符串或run列表。正文最多6段且≤200字，24pt，仍须视觉检查。
- `image`：可选PNG/JPEG本地路径，保持宽高比；正文区随之变窄。
- `notes`：可选教师备注字符串，可记录资料引用。

默认8页内容与学案一致，用户指定其他数量时调整。生成器保留模板母版与背景，替换示例内容并添加对应角标，不复制原课题文本。

## 命令结果

`generate_materials.py`成功返回0，失败或资料不足返回2。输出目录中保留`generation_report.json`；缺来源且未加`--allow-unverified`时不生成Office文件。来源齐全的输出仍为`generated_pending_visual_review`；缺来源草案为`draft_missing_sources`，不表示正式教学审核通过。已有输出不覆盖，请每次使用新目录。

导学纲必须使用固定入口 `render_outline.py` 和 `revise_outline.py`。其他单一类型如确需底层装配，可在任务脚本里调用`generate_outline(data,path)`、`generate_paper(data,path,base_dir)`、`generate_answers(data,path)`或`generate_pptx(slides,path,base_dir=...)`，再执行校验。此时调用者仍负责来源核验；底层函数不会自行检索或认证来源。
