# Score Transposer

一个面向 AI Agent 的乐谱移调与数字化 Skill。

它支持 MusicXML / MXL 高可靠性移调、清晰 PDF 乐谱识谱、PDF 移调，以及 MusicXML 和 PDF 输出。它适合清晰、结构常规的声乐谱、钢琴谱和常见器乐谱，不承诺模糊扫描、大型总谱或特殊现代记谱能够 100% 自动还原。

## 安装

### 在 Codex 或其他 AI Agent 中安装

如果你正在使用 Codex、Claude Code、Cursor、GitHub Copilot、Cline 等支持 Agent Skills 的工具，可以直接告诉 Agent：

> 请从 https://github.com/Rui-Huang-dotcom/score-transposer.git 安装 score-transposer Skill。

也可以在终端运行通用 Skills CLI：

```bash
npx skills add Rui-Huang-dotcom/score-transposer --skill score-transposer
```

安装后重新加载或重启 Agent，使它发现新的 Skill。不同 Agent 的安装目录可能不同；CLI 会根据当前环境提示安装到用户级目录或项目目录。

### 只想手动安装到 Codex

Codex 的 Skill 目录通常是 `~/.codex/skills`。可以运行：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo Rui-Huang-dotcom/score-transposer
```

安装后重新打开 Codex，或让 Codex 重新扫描 Skills。

### 直接克隆仓库

```bash
git clone https://github.com/Rui-Huang-dotcom/score-transposer.git
```

直接克隆适合开发和修改；如果希望 Agent 自动发现 Skill，仍需使用上面的安装命令，或把目录放到对应 Agent 的 Skills 目录。

## 使用方法

安装完成后，不需要记住脚本名、OMR、OCR 或 MuseScore 参数，直接用自然语言描述任务：

> 把这份 MusicXML 从 D 大调移到 G 大调，并输出 PDF。

> 把这份 PDF 乐谱从 E 小调移到 D 小调。

> 把这份 PDF 乐谱转换成可编辑的 MusicXML。

MusicXML / MXL 会直接走结构化移调路线。PDF 会先分析，然后让用户选择：

1. **标准模式**：更快、消耗较少，适合清晰、简单、常规乐谱；
2. **精细校对模式**：逐页对照原始 PDF 与 MuseScore 渲染结果，发现问题后修复 MusicXML 并重新检查；更慢，但更重视准确度。

用户不需要了解内部的 `fast`、`accurate`、`verified`、Audiveris、OMR 或 OCR 名称。

## 第一次运行与依赖

第一次处理 PDF 时，Skill 会检查 Python、Audiveris、MuseScore 和 Poppler 或等效 PDF 工具。Audiveris 负责主识谱，MuseScore 负责渲染和导出，Python 脚本负责结构与音高 QA。

HOMR 是可选的备用识谱路线，LilyPond 是可选的渲染 fallback。初始化成功后会保存 `.score-transposer-initialized` 状态，后续不会每次重复完整检查；只有实际调用失败时才重新检查相关依赖。Python 包会安装到 Skill 自己的虚拟环境中。

## 处理流程

MusicXML / MXL：

```text
MusicXML / MXL → 分析调性 → 移调 → 结构与音高 QA → MuseScore → MusicXML + PDF
```

PDF 标准模式：

```text
PDF → 基础分析 → Audiveris → 必要时一次 HOMR fallback → MusicXML QA → 移调 → MuseScore
```

PDF 精细校对模式：

```text
PDF → OMR MusicXML → MuseScore 渲染 → 原谱/渲染谱逐页比较 → 修复 MusicXML → 重新渲染复查
```

正式修复只修改 MusicXML / MuseScore 结构，不直接移动 PDF 或 JPG 的像素、音头或 glyph。

## 输出与可靠性

默认输出：

- `.musicxml`：可继续在 MuseScore、Sibelius、Dorico 等软件中编辑；
- `.pdf`：重新排版后的乐谱。

原文件不会被覆盖。如果没有通过 Musical QA、Content Preservation QA 或精细模式的 Visual Fidelity QA，输出文件名会包含 `_DRAFT_UNVERIFIED`，并提示用户在 MuseScore 中人工校对。

## 最适合的乐谱与限制

效果最好的是 MusicXML / MXL、清晰印刷谱、单声部声乐谱、简单声乐 + 钢琴、简单钢琴谱和常见器乐谱。

模糊扫描、老旧复印件、大型总谱、复杂 polyphony、跨谱表、多次换谱号、极端加线、现代记谱以及古筝等专用演奏符号风险较高。无法可靠判断的内容会标记为需要人工确认，而不是编造结果。

## 开发与测试

在仓库根目录运行：

```bash
python3 -m unittest discover -s tests -v
```

仓库中的 `scripts/`、`workflows/`、`references/` 和 `tests/` 用于 Skill 的实际工作流与维护。

## License

MIT License，详见 [LICENSE](LICENSE)。
