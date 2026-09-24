---
name: score-transposer
description: Transpose MusicXML/MXL reliably and digitize or transpose clear PDF sheet music into MusicXML and PDF, with standard or detailed review workflows and honest draft output for uncertain results.
---

# Score Transposer

目标是让普通用户用一句话完成可靠的乐谱移调或数字化。它适合清晰、结构常规的乐谱，不承诺任意 PDF 或 100% 自动准确。

## What it does

- MusicXML / MXL → 移调 → MusicXML + PDF
- PDF → 识谱 → MusicXML
- PDF → 识谱 → 移调 → MusicXML + PDF

MusicXML / MXL 是最高可靠性路线：不经过 OMR，也不要求视觉校谱。移调后会检查音程、调号、结构、渲染和内容保留，包括 notes、rests、lyrics、slurs、ties、tuplets、dynamics、articulations、clefs、time signatures、tempo 和 text。

## Usage

用户只需说：

> 把这份乐谱从 D 调移到 G 调。

或：

> 把这份 PDF 从 E 小调移到 D 小调。

输入 MusicXML / MXL 时直接处理，不询问模式。输入 PDF 且用户没有指定质量时，先做轻量分析，再只询问：

1. **标准模式**：更快、token 更少，适合清晰常规乐谱。
2. **精细校对模式**：逐页对照原谱、修复结构并重新检查，耗时和 token 更高，但优先追求准确度。

用户不需要知道 Audiveris、OMR、OCR、MuseScore、MusicXML 或内部 mode 名称。标准/精细选择由内部映射到现有代码路线。

## PDF standard mode

标准模式执行：PDF 分析 → Audiveris 主识谱 → 必要时一次 HOMR fallback → MusicXML QA → 移调 → MuseScore → 输出。

程序化 QA 检查 parts、measures、notes、rests、key/time signatures、clefs、lyrics、dynamics、slurs、ties、tuplets、articulations、duration、empty/suspicious measures 和 OMR 日志。声乐谱若 `lyrics == 0`，或出现严重 rhythm、duration、missing measure、structure 错误，不得正式交付。

标准模式不默认逐页看图。QA 失败时输出 `_DRAFT_UNVERIFIED`，并简洁提示用户可以改用精细校对模式。

## PDF detailed review mode

精细模式逐页比较：原始 PDF 页面与当前 MusicXML 经 MuseScore 重新渲染的页面。除了 XML 结构，还检查漏音、多音、音高、临时记号、节奏、附点、休止符、三连音、voice、chord、measure boundary、谱号、调号、拍号、8va/8vb，以及 slur、tie、articulation、dynamics、渐强渐弱、fermata、ornament、rehearsal/expression text 和歌词对应关系。

发现问题后优先修改 MusicXML/MuseScore 结构，再重新渲染。第一轮可以修复多个按 page/system 合并的问题；后续只检查被修改的页面、system 或小节。没有固定的“两轮”上限，继续修复直到：

- 没有新的明显音乐错误；
- 剩余内容属于无法可靠判断的特殊记谱；
- 连续一轮没有实质改善；或
- 需要演奏者/专业制谱人员确认。

已确认页面和区域写入 `verified_review.json`，不会重复检查。能用 Python/XML 判断的内容优先程序化验证；视觉检查只处理“结构合法但与原谱不一致”的问题。正式修复不得直接移动 PDF/JPG 像素或 glyph。

## Best results and limitations

效果最好：MusicXML / MXL、清晰印刷谱、单声部声乐、简单声乐+钢琴、钢琴谱和常见器乐谱。

模糊扫描、老旧复印件、大型总谱、复杂 polyphony、跨谱表、现代记谱、频繁换谱号、极端加线和古筝等专用符号会提高风险。无法可靠判断时不编造，明确提示需要人工确认。

## Initialization and outputs

首次使用只检查一次必要系统依赖：Python、Audiveris、MuseScore、Poppler。LilyPond 仅作为可选 fallback；HOMR 仅作为可选备用。缺失依赖一次性请求安装授权，并在成功验证后写入 `.score-transposer-initialized`。后续不重复完整检查，只有真实调用失败才定向重查。

正式结果默认包含 `.musicxml` 和 `.pdf`，不覆盖原文件。未通过 Musical QA、Content Preservation QA 或精细模式 Visual Fidelity QA 时，只输出带 `_DRAFT_UNVERIFIED` 的文件。详细日志写入 JSON/debug report，普通用户只看到简洁结果。

读取 [workflows/initialization.md](workflows/initialization.md)、[workflows/digitize.md](workflows/digitize.md) 和 [references/qa_schema.md](references/qa_schema.md) 获取维护细节。`prepare_visual_review.py` 仅保留为旧版/debug 辅助，不是公开主流程。
