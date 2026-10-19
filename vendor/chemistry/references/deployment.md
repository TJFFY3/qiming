# FastGPT 部署与依赖

## 导入

1. 使用含技能和沙盒能力的 FastGPT 环境。在技能列表导入ZIP，检查根目录能看到 `SKILL.md`、`entrypoint.sh`、`requirements.txt`、`scripts/` 和 `assets/`。
2. 技能编辑终端执行 `sh entrypoint.sh`。调试模式不自动执行该脚本；部署后入口脚本由平台执行。
3. 执行 `python3 -m unittest discover -s tests -v`，再从 `SKILL.md` 的命令运行格式样例。为每次运行指定新的输出目录。
4. 为智能体配置教材/题库检索，必要时配置图片工具，再用一个真实课时检验来源、答案和版式。
5. 发布技能正式版本，并在智能体中关联。确认部署后新沙盒仍能安装依赖及生成文件。

本包仅供导入，不自动访问或发布到你的 FastGPT 实例。官方说明：
- [开发与调试](https://doc.fastgpt.io/zh-CN/guide/build/skill/development)
- [初始化脚本](https://doc.fastgpt.io/zh-CN/guide/build/skill/initialization)
- [智能体集成](https://doc.fastgpt.io/zh-CN/guide/build/skill/integration)

## 依赖

Python3.10+；`lxml==6.1.1` 、`python-docx==1.2.0` 和 `jsonschema==4.25.1`。python-docx还会安装传递依赖typing_extensions；jsonschema会安装attrs、referencing、rpds-py及jsonschema-specifications等传递依赖。jsonschema用于生成前结构校验，不调用外部服务。这些版本已在适配时的本地测试环境运行；不同Linux镜像、网络、CPU架构仍需目标沙盒验证。`os/re/sys/json/pathlib/zipfile/tempfile/copy` 等为标准库。

入口脚本只安装本包依赖，不安装Word/WPS、中文字体或图像生成服务。FastGPT初始化有执行超时，若镜像网络受限或下载过慢，应在沙盒镜像预装所需版本或配置合法可用的包源；不要把安装失败当作依赖已就绪。不要在ZIP中携带本机 `.venv`。

## 字体和预览

正文引用宋体、黑体、楷体_GB2312、Times New Roman，PPT可使用阿里巴巴普惠体M，单行反应式使用Courier New。字体未打包，不附字体授权。最终阅读者或渲染环境应具备这些字体；缺少时使用已获授权的替代字体，并重新检查分页、文本溢出及化学符号。

本包不包含PDF/PNG渲染环境。若需要自动预览，应另在目标镜像配置可用Office渲染器；不应在每次启动时盲目安装大型办公软件。Word EQ/OMML缓存必须在实际Word/WPS中确认。PPT支持单行反应条件与等号的原生叠排；过长或需要换行的反应式需拆分、使用已核验图片或在任务副本中精修，并做视觉核验。

## 本次适配范围

保留三份原模板，补齐可移植Word/PPT基础装配、化学run、统一入口、来源报告和结构校验。原始《化学符号》标准未附带；生产规范按原SKILL文字整理。基础PPT支持文字、图片、备注，复杂表格/图示及旧课件任意编辑需要单独处理。无内置教材检索客户端、自动生图或字体分发功能，不假定用户已有这些服务。

## 本次 POC 更新

新增导学纲独立生成、原生 Word 教学表格及按块版本修改。导学纲仅校验当前产物需要的教材/教师用书来源；三件套旧入口保留原题源规则。导入更新包后需重新初始化依赖、发布技能版本，并确认 AgentV2 关联新版本。仅修改本地包不会更新已发布应用。

先执行 `python3 scripts/render_outline.py --input examples/outline.json --check-only`，再按导学纲流程生成。样例无真实教材证据，仅能用 `--allow-unverified` 做格式测试。不得将本机回归通过当作 FastGPT Linux 沙盒或 Word/WPS 的验收结果。
