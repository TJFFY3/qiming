---
name: chemistry-teaching-fastgpt
description: 用于高一化学教学资料的生成与修改，适用人教版必修第一册导学提纲、30至35分钟限时练、独立答案卷和教学PPT；需要遵循随包模板、化学符号与题源核验规范时使用。
---

# 化学教学资料生产规范 · FastGPT 适配版

为高一化学教师制作导学提纲、限时练、独立答案和教学 PPT。保留原技能的化学符号、模板与教学流程要求，所有生成工具及模板均在本包内，不依赖原作者电脑或 WorkBuddy。

## 运行前

- 当前技能的 `SKILL.md` 所在目录是包根目录。命令示例从该目录执行；路径有空格时加引号。不要假定技能部署在某个固定 `/workspace` 子目录。
- 环境需要 Python 3.10+，依赖见 `requirements.txt`。FastGPT 部署后使用根目录 `entrypoint.sh`；编辑调试时先手动执行 `sh entrypoint.sh`，再测试。
- 本包不包含教材、题库、字体、PDF渲染器或生图服务。新增结构校验依赖 `jsonschema`；只配置实际存在的应用工具，工具名称以当前 FastGPT 应用为准。
- 生成教学内容前阅读 [生产规范](references/production-rules.md)；检索资料时阅读 [资料与图片策略](references/source-policy.md)；填写输入时阅读 [输入格式](references/input-format.md)。

## 导学提纲优先入口（本次 POC）

仅生成或修改导学提纲时，必须使用以下固定工具。先读 [导学纲生成与修改](references/outline-workflow.md) 和 [结构契约](references/outline.schema.json)。不要为本次任务编写装配脚本、用 sed 修代码或修改随包工具。模型负责内容 JSON，工具负责校验与 Word 装配。

1. 确认课时和目标，检索本课教材或教师用书；整理真实来源及缺口。导学纲单独生成不要求试卷、PPT、高考真题来源。
2. 使用 `outline.sections[].blocks[]` 标准结构；文本用 `type: paragraph`，教学填表用 `type: table`。表格必须保留表头、每行及空白单元格，不能改成“自行画表”。参考 `examples/outline.json`（仅格式样例）。
3. 先执行 `python3 scripts/render_outline.py --input /实际路径/内容.json --check-only`。按返回的字段路径修 JSON，最多修正两轮；仍失败则报告实际错误，不临时重写生成器。
4. 执行 `python3 scripts/render_outline.py --input /实际路径/内容.json --output-dir /实际路径/v001 --version v001`。来源不足且用户接受草案或仅格式测试时加 `--allow-unverified`，保留“待核验”。输出目录必须是新目录。
5. 用户提出连续修改时，以当前版本的 `content.json` 和对话定位目标块；从 `generation_report.json` 读取当前哈希，写局部补丁，再调用 `scripts/revise_outline.py`。不冲突的内容、原版本和来源必须保留。逐版保存，分别交付和评价。
6. 读取生成报告，确认教学表格数量、行列数和结构检查；再检查 Word/WPS 的分页、化学域、空白作答区。没有视觉检查时明确标注。实际可下载后才返回下载链接。

旧版 `sections[].paragraphs` 与 `groups/blocks/body` 会由工具转换；不继续生成这两种旧结构。嵌套方程式仅在旧结构转换中展开，标准 run 必须为扁平对象数组。未知字段、类型和不齐的表格行会报错，不能默默丢弃。

## 三件套完整执行流程

1. 从当前请求确定教材版本、章节、课时、教学目标和需要的产物；已给出的信息不重复询问。默认三件套实际交付四个文件：提纲、限时练、独立答案、PPT。
2. 调用应用已配置的资料检索工具，或读取用户上传的原始资料。记录教材、教师用书、课时题库、必刷题、高考真题五类来源。工具不可用时，说明缺少什么资料；不得假装检索或编造教材页码。
3. 依据资料准备内容计划 JSON。教材原始页码与 PDF 文件页序分开记录。逐题核实题干、选项、答案、解析、分数、难度与用时。默认 I 卷 14 题×4分，II 卷44分，选做2题不计分；必做总时长30至35分钟。
4. 用语义 run 表示化学符号。字符串中用 `[H2O]`、`[SO4^2-]`、`[Fe^3+]` 明确标记化学式及电荷；反应条件、同位素和幂使用显式 run。普通文本不做全局数字替换。
5. 为本次任务选一个尚未使用的输出目录，执行：

   ```sh
   python3 scripts/generate_materials.py --input /实际路径/lesson.json --output-dir /实际路径/本次课时输出
   ```

   来源不足时，默认只输出缺口报告。若用户接受草案，或仅进行格式测试，可加 `--allow-unverified`，文件名及正文标题会带“待核验”。草案不得称为已核验教学资料。脚本不覆盖已有产物。
6. 生成入口自动校验，也可单独检查：

   ```sh
   python3 scripts/validate_outputs.py /实际路径/本次课时输出 --json --report /实际路径/结构检查.json
   ```

   检查 `generation_report.json`，确认状态、来源缺口、错误和人工复核项。校验失败时修复后在新输出目录重试，不能只改报告的通过标记。
7. 使用当前环境可用的 Office/WPS/渲染工具检查所有页：化学 EQ 域缓存、上下标、字体替换、文字溢出、分页与答题空间。无渲染能力时明确“仅通过结构检查，视觉效果待核验”。
8. 通过当前 FastGPT 环境支持的下载或预览方式交付四个文件，简述资料缺口和待核验项。无法生成下载链接时说明文件的沙盒位置，引导使用虚拟机文件管理器；不编造链接，不调用原平台的交付接口。

## 随包工具

- `scripts/render_outline.py`：导学纲单独生成、结构契约校验、旧格式转换、来源报告和版本快照。
- `scripts/revise_outline.py`：按块修改、基线哈希校验、保留无关内容并输出新版本。
- `scripts/outline_contract.py`：标准化及 JSON Schema 校验。
- `scripts/chemistry_runs.py`：化学式 run、Word EQ 域及缓存结果。
- `scripts/docx_tools.py`：从两份 Word 模板生成提纲、试卷和独立答案；保留页面设置、字体规范、答题区域。
- `scripts/ppt_tools.py`：从 PPT 模板空白内容页装配，沿用母版和背景；上/下标用 baseline 属性。
- `scripts/generate_materials.py`：JSON入口、题量/分数/时长检查、来源检查、生成与报告。
- `scripts/validate_outputs.py`：OOXML、域、页面尺寸、PPT关系、字体与边界结构校验；不等同于视觉或化学答案审核。

## 调试与部署

[部署与依赖说明](references/deployment.md)包含 FastGPT 导入、初始化、字体与可选检索/生图配置。`examples/lesson.json` 仅为格式测试数据，重复题干及答案不能用于正式授课。调试命令：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/generate_materials.py --input examples/lesson.json --output-dir /实际路径/唯一测试目录 --allow-unverified
```

修改已有 DOCX/PPTX 时先复制到任务目录，保留原件。生成器负责新课时模板装配；已有复杂课件的任意逐页修改需要单独分析其逻辑页序和关系，不应直接覆盖原件。
