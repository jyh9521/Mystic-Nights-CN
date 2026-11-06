# 2026-11-06：原声听审回填

## 文本结论

玩家听审后指定三处修订，其他六条原候选认可；C012的称呼由项目结合上下文消歧，详见[C012来源](C012_REFERENCE.md)。九条译文为玩家确认；C012“简！”是明确标注的高置信情境推断，`source_transcript`和`user_heard`仍为`신!`，没有将`제인!`伪装成确定的原声逐字稿。

| 场景/VOICE | 起始FRAME | 译文修订 | 结束FRAME（不含） |
|---|---:|---|---:|
| C005 / 001_002 | 980 | 这里是……呃啊…… | 1325 |
| C012 / 007_001 | 380 | 简！ | 524 |
| C021 / 016_001 | 335 | 呃啊 | 410 |
| C027 / 021_003 | 1405 | 啊！ | 1472 |

其余保留六条的区间为：C005/001_001 `[720,864)`、001_003 `[1405,1563)`；C008/003_001 `[960,1105)`；C021/016_002 `[410,536)`；C027/021_001 `[210,270)`、021_002 `[270,416)`。原VOICE节点、源VAG/WAV和原相机身份逐项绑定。

## 时间轴：源证据与待验收分开

**Verified offline：** InitGraph在`0x1276C8..0x1276D8`向SetGsCrt传入`interlace=1, mode=2, ffmd=1`；Flip经过`0x127638 → 0x101198 → 0x103EF0`等待INTC_STAT的VBLANK_S；原过场每次循环执行一次Update/Render/Flip，Update在`0x139234..0x139248`将FRAME加一。VOICE通过原声音调用播放，字幕不替换原音频。

**High-confidence deduction / authored timing：** 以NTSC名义`60000/1001`帧/秒换算解码PCM长度，不称为实测常数。结束帧采用精确分数运算：

```text
min(start + ceil(PCM_samples * 60000 / (sample_rate * 1001)),
    next_voice_frame, next_OUT_fade_frame, camera_frames - 1)
```

十条均不重叠。四处由下一VOICE/OUT淡出裁界；波形能量诊断支持尾部已有余量，但它不证明语义边界。玩家未提供结束帧，也未验收新引擎的实际延时，故`timing_review.runtime_sync_verified=false`。完整只读源锚点与分数复算在本地`build/subtitle-listening-20261106/timing/`。

## C005固定槽容量

实际十条编译首次遇到C005：原SCR容量890字节，完整字幕候选953字节。未截短玩家文字，未扩展RES、移动LBA或合并原生CRLF命令。

**Verified offline：** 原`ReadCutsceneSound`将POSITION（token `0x151`）直接分派至下一个GetToken。实际分支回放没有内存写入；SOUND_COUNT按8字节分配的记录只有code/type/argument，无坐标向量，BGM/VOICE播放也不读取坐标。这是明确忽略命令，不是猜测“默认坐标为零”。

`inspect_sound_position_elision`对完整原ELF大小、SHA-256及七处独立字节锚点验证。锚点覆盖`0x13C128`、`0x13C198`、`0x24D808`、`0x13ADB0`、`0x13AEC8`、`0x13BB20`、`0x138DF0`；期望字节在通用模块的`SOUND_POSITION_ANCHORS`，适用原ELF身份见[CUTSCENE_SUBTITLES.md](CUTSCENE_SUBTITLES.md)。

只在容量不足时、只在原SOUND块、明确且唯一的BGM/VOICE类型、唯一且逐字为`POSITION 0 0 0`的行才省略。C005共四行，每行16字节：`953 - 64 = 889`，末尾补一个空格至890。其余场景原命令不删。报告逐条记录原节点序号/帧/NAME/命令位置和token；独立回读先恢复明确省略行，再要求所有原命令及参数逐项相同。`original_tokens_retained=false`据实记录，`original_semantics_retained=true`由此有界证明；未知版本、非零位置、EFFECT、重复/歧义命令仍保留或报容量错误。

## 交付口径

正式数据在`locales/zh-CN/subtitles.json`；审查范围与原始意见在`locales/zh-CN/subtitle-listening-review.json`。历史ASR数组仍标机器结果，保留其`human_listening_verified=false`，不改写历史模型证据。

本次显式字幕构建覆盖**5场景、10条明确VOICE**，不是将47场景都标为完整。其余42个空字幕场景仍未被认定为无对白，`all_speech_transcribed=false`。普通无参数构建继续不启用字幕；此次测试ISO须显式传`--subtitle-catalog locales/zh-CN/subtitles.json`。主字库先并入新增“喂”，再统一生成正文、字幕、HD字库及最终ELF对应的运行补丁CRC。

游戏内字幕位置、混色、换行、实际声音同步、场景跳过和存取仍由玩家验收。没有擅自启动模拟器。
