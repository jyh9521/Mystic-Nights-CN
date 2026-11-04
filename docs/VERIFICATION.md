# 中文技术验证版：离线验收

日期：2026-11-04（Asia/Tokyo）。代码验证提交：`44c303f7393c49de8f9946b2f75459d36d445f2d`。

这不是完整汉化或游戏内验收。未启动游戏/模拟器；玩家测试另见 [TESTING.md](TESTING.md)。

## 输出身份

| 对象 | SHA-256 |
|---|---|
| 原版 ISO / 单独副本回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 中文 PoC ISO | `9a36ef04077eed6c492a86184a72eac488d6f7bd021d29f66c50c84d1f2a7d8d` |
| `DIFF_FILE.mnp.zip` | `0b2a4b369b48d4d3bfc973635d225de5cab9450b89e9b6f071f20b1c5d12347b` |
| `font-preview.png` | `9b37fdfd0f505134f621dfaa073e73aabc7f5e0e5384dcc4be629ad449980326` |

两种 ISO 均为1,696,530,432字节；差分为22,194字节、40个区间。修改范围是13个ELF系统/界面槽、`EVENT.SCR@00000c77`及47个中文对应的`FONT_8.TM2`字形像素。

## 实测结果

全部命令退出码为0：

```text
python -X utf8 -m unittest discover -s tests
Ran 97 tests
OK

BASELINE PASS files=724 resources=209 scripts=179 source_slots=14
MODIFIED PASS strings=14 glyphs=47 changed_files=3 unchanged_files=721 lba=unchanged
FONT_INSPECTION glyphs=2539 ascii=95 jamo=94 hangul=2350 textures=8 overlaps=0 anchors=9 dwarf_functions=4
```

- 原文SCR提取/回填逐字节一致。
- 只改3个ISO文件，其他721个文件和全部LBA/文件长度相同。
- 正向差分在独立副本产生同一修改哈希；`ROLLBACK.sh`对该副本反向输出，恢复原盘哈希并再次通过基线检查。供测试的修改镜像保留修改状态。
- 从上述提交的纯源码归档重新提取，重新下载锁定字体，执行97项测试、构建及完整验证；ISO、差分和预览哈希与交付一致。
- 源码换行统一为LF后，manifest中的译文文件哈希按干净构建刷新；其他清单字段及ISO/差分/预览内容不变。

## 可重放步骤

基线、构建、修改版校验与正向/反向差分的完整参数见 [BUILDING.md](../BUILDING.md)。本地交付目录的 `VERIFICATION.txt` 另外保存逐条原始stdout/stderr、输入、绝对路径及退出码，`build/verification/`保存JSON报告。

当前仅证明离线构建与字节级恢复。中文混色/字号、菜单布局、对白推进、存读档、各章节/结局、联网及完整通关均仍需游戏内验证。
