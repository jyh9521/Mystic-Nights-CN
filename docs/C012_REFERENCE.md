# C012 FRAME380：称呼消歧来源

**译文：简！** 依据为角色与相邻剧情的高置信情境推断（`editorial-context`），不是原声逐字稿的书面证实。听审转录保留`신!`，另记`inferred_reference=제인 / Jane`；原C012脚本只有VAG调度，没有这句话的韩文字幕。

## 可复核锚点

- 原`EVENT.SCR@0x91bd/0x92c1`（EVENT161）：`제인?`及再次询问简发生何事；随后赶往声音所在房间。
- EVENT163显示`제인2_03`（字段`@0x954a`）、将其HP设55，再加载C012；EVENT164的`@0x9696`明确写简处境危急。
- 原`C012.SCR@0x109d`为女性出血注释；`@0x11e4`的VOICE节点在FRAME380播放`007_001.VAG`。该声音节点没有说话人标识。
- 原`ST0201.SCN@0x5f72`的局部名称为`제인2_03`，其后32字节处`@0x5f92`为`F003.GEO`，对应C012女性角色。此处仅证明局部字节关系，不扩充为完整SCN格式结论。
- 名词表`person:jane`：`제인 블레어 → 简·布莱尔`。上游固定提交的同一人物字段为`Jane Blair`，相邻呼叫也用`Jane?`。[上游来源](https://github.com/jeremydecola/Mystic-Nights-Translation/blob/d58734cccf29b702330d131ea981de45512d3b76/RES/SUBSYS.RES)

短促感叹仍是声学备选；检查范围内没有独立“신/Shin”人名或房间名支持。因而采用既有人物简称“简”，不另造实体。原声音节与情境指代分字段保留。

## 身份

| 来源 | SHA-256 |
|---|---|
| 韩版原盘 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 原EVENT.SCR | `bf82b81aaaf4aa02c03926c7c77daca10560bd176a87012c57a2b9d3a3a6e2e0` |
| 原C012.SCR | `d2f37199d8987f345f7a24f6eae8346d6216a823d848259de1d554c2843ad127` |
| 原007_001.VAG | `dd5b6c3961327e117cd7eb954865e5dbc425a3b454a441301930d5f4b9528242` |
| 原ST0201.SCN | `4a149704cf9f61b7b12dc7d0832d28a198e856354fd01ecd796bc5bd99342986` |
| 上游EVENT.SCR（d58734c） | `f8d3b94eaae2eae9bc4a0f32ab15ce462a7f1274aa153b40bcb4e39153a855ea` |

来源核查阶段只生成报告；随后字幕目录采用“简！”，并在`reference_interpretation`保留推断性质。详细本地字段证据见`build/subtitle-listening-20261106/c012-context-evidence.json`，本次采用记录见[听审回填](SUBTITLE_LISTENING_20261106.md)。游戏未启动。
