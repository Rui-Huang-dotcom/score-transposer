# score-transposer

AI 乐谱移调工具：支持 MusicXML/MXL 高可靠性移调，也支持 PDF 乐谱识谱、移调和重新制谱。

## 用户用法

用户只需要说：

> 把这个乐谱从 D 调移到 B♭ 调。

MusicXML / MXL 会直接处理。PDF 会先分析，然后在用户没有指定质量时询问：

- **标准模式**：更快、token 更少，适合清晰常规乐谱。
- **精细校对模式**：逐页比较原谱和 MuseScore 渲染结果，修复 MusicXML 结构后重新渲染和复查；更慢、更耗 token，但优先追求准确度。

用户不需要知道内部的 `fast`、`accurate`、`verified`、Audiveris、OMR 或 OCR。

## 实际路线

```text
MusicXML/MXL → 语义移调 → Musical QA → Content QA → MuseScore → MusicXML + PDF

PDF 标准 → PDF 分析 → Audiveris → 必要时 HOMR fallback → MusicXML QA → 移调 → MuseScore

PDF 精细 → OMR → 逐页原谱/渲染谱比较 → MusicXML 修复 → 重新渲染 → 只复查修改区域
```

Audiveris 是主 OMR，HOMR 只做一次备用尝试，不并行融合。正式修复只修改 MusicXML/MuseScore 结构，不移动扫描图像像素。

## 输出和可靠性

成功时默认输出 MusicXML 和 PDF，不覆盖原文件。MusicXML 移调还会比较移调前后的 lyrics、slurs、ties、tuplets、dynamics、articulations、clefs、tempo、text 等内容。

PDF 标准模式不默认逐页看图。精细模式会缓存已确认的页面、system 和 measure，只重新检查修改过的区域；没有实质改善、遇到无法可靠判断的特殊记谱，或需要专业人员确认时停止深度修复。

不可靠结果只输出 `_DRAFT_UNVERIFIED`，不会伪装成正式成功。模糊扫描、老旧复印件、大型总谱、复杂 polyphony、现代记谱和古筝等专用符号可能需要人工校对。

## 依赖

首次使用时一次性检查 Python、Audiveris、MuseScore 和 Poppler。LilyPond 是可选的渲染 fallback，HOMR 是可选的 OMR fallback。初始化成功后写入 `.score-transposer-initialized`；后续只有真实调用失败才重新检查。

## 开发检查

```bash
python3 -m unittest discover -s tests -v
```

`prepare_visual_review.py` 和旧实验资源仅作 debug/兼容保留，不属于公开主流程。
