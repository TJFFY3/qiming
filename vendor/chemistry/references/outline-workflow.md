# 导学纲生成与连续修改

命令从SKILL.md所在目录执行；其他工作目录请给脚本绝对路径。输入和输出路径均使用实际路径，包含空格时加引号。模型只准备JSON，不生成Python装配脚本、不用sed修改工具。首次生成、每次修改分别保存版本，供教师对比评分。

## 首次生成

参考examples/outline.json及outline.schema.json。建议顶层使用 `{ "sources": [], "source_gaps": [], "source_conflicts": [], "outline": {...} }`；也接受直接outline，但无来源时只能作为待核验草案。顶层元信息原样留存，outline未知字段会拒绝。

```sh
python3 scripts/render_outline.py --input /实际路径/内容.json --check-only
python3 scripts/render_outline.py --input /实际路径/内容.json --output-dir /实际路径/v001 --version v001
```

检查模式仅验证结构，不代表来源、教学或版式验收通过。缺来源的格式测试可在生成命令末尾加 `--allow-unverified`。真实教学内容须在用户接受草案时才使用该参数。参数不豁免结构错误。

脚本返回JSON。错误字段有path、code、message；只修对应输入，最多两轮仍失败则向用户返回具体错误。不能忽略错误、删表降级或修改检查器绕过。

每个新版本输出：

| 文件 | 用途 |
|---|---|
| outline.docx | 可编辑导学纲；草案标题标待核验 |
| content.json | 标准化内容及稳定的section/block ID |
| source_input.json | 原始输入及来源记录 |
| generation_report.json | 状态、版本、内容哈希、来源缺口、表格统计和结构检查 |

`statistics.content_tables`不含25行笔记表；`data_rows`不含表头。应与输入逐一对应。原生表格保留空单元格、化学run和最小行高。检查Word/WPS中分页、跨页表头、长公式、书写空间及字体。

## 连续修改

先读当前content.json和generation_report.json，结合对话定位需改块。补丁形如：

```json
{
  "base_sha256": "从当前generation_report.json原样复制content_sha256，不能猜测",
  "changes": [
    {
      "block_id": "从当前content.json复制目标块id",
      "replacement": [
        {"type":"paragraph", "content":"修改后的第一步问题"},
        {"type":"paragraph", "content":"修改后的第二步问题"},
        {"type":"paragraph", "content":"修改后的第三步问题"}
      ]
    }
  ]
}
```

上面是结构说明，其中哈希和ID必须替换为实际值。表格也可以作为replacement块，使用同一schema。首个替换块沿用原ID，新增块由工具分配ID（自动跳过已占用编号，支持多轮拆分），或显式使用尚未占用的新ID。不要重复提交同一目标。

```sh
python3 scripts/revise_outline.py --current /实际路径/v001 --patch /实际路径/patch.json --output-dir /实际路径/v002 --version v002
```

工具校验基线哈希、防止修改错版本；只替换指定块，保留其他块、目标、章节和来源。输出目录必须全新且不能位于旧版本目录内。草案状态继承，不能通过修改自动升级。报告previous记录上一版本及修改块。

当前补丁支持替换现有段落或表格、把一个块拆成多个块；不支持删除块、改章节/目标或增加新章节。此类结构变更应读取当前完整内容，按明确要求编辑完整JSON，再用render_outline.py输出新目录并比对差异；不得误称已由局部修改工具保证全部无关内容不变。

## 与三件套入口的关系

导学纲独立入口不需要paper/slides，不要求额外的高考题来源。`generate_materials.py`继续处理完整三件套、试卷分数题量与题源审核。其他文件的生成和修改遵循原规则。两者都不认证来源真伪，也不替代教师评分和Office视觉验收。
