# 汉化构建：离线验收

## 2026-11-05 主菜单两态字号与白线修正

源码提交 `f018cdbe58b1c365e9cca8db831d09c8dc56c5d0`，分支 `master`。`L001_004.TM2` 仅四个选中区域修改 3119 个索引；差分字段 `ranges/modified_sha256/state_checks/authoring_method` 更新。正文、字库、普通态、其余 135 张重绘纹理、UID 脚本和菜单渲染代码保持。

旧 ISO 与旧差分实际一致，并非没有安装：旧字形掩码混入胶囊下框，使四项核心字高缩为 10 像素，并带 59 像素白线。原版静态布局两态 Y 缩放相同，X 仅约 1.46% 差异。修正后普通/高亮字高分别为 14/14、12/13、13/13、13/13，四条额外白线均为 0。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| Mystic-Nights-zh-CN-full-text.iso | `58aa0dd720a0265d5962f23cca812d066365d296c81b8296ef4419d4ededa90e` |
| DIFF_FILE.mnp.zip | `f026bf2c7ff3935be459cb9f5921f5915e49eb126af444bea2035ed2d4ded9d0` |
| manifest.json | `4a4b41f22fdbf90843ac243b77c9cda8303a4ce11076b0800bcdc75bf1c3f259` |
| ROLLBACK.sh | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |

原始 TIM2 SHA `076f1530ee2a270274761a58ee122416255f3215a6e69f22a07694acf6bf39cc`；修正后为 `46209d66a054791c2dda965c8e5846118a0cb146127134bc024d55ed34e889c6`。

交付四件位于 `build/full-text/`：`Mystic-Nights-zh-CN-full-text.iso`、`DIFF_FILE.mnp.zip`、`VERIFICATION.txt`、`ROLLBACK.sh`。ISO 1,696,530,432 字节；差分 8,928,361 字节、20049 个区间。原盘保持；独立回滚输出逐字节恢复原版，并通过 2164 原文槽检查；当前交付镜像仍为修改版。

268 项合成测试与干净源码重建测试通过；6 件重建输出（ISO、差分、manifest、两张字库预览、回滚脚本）逐字节同哈希。最终 ISO 回读 4 对状态通过。以下命令均退出 0；公开记录仅将输出中的本机路径转为相对路径，绝对路径及未经修改的完整输出保存在本地 VERIFICATION。

### BASELINE

```text
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

### MODIFIED

```text
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf
GRAPHICS PASS translated=404 installed=402 pending=0 texture_members=246 save_metadata=1
RAW_IMAGES PASS installed=1 resources=1
FULL_PATHS PASS names=113 references=698 network_strings=270 network_glyphs=293 agreement=1 extra_interface=38
MODIFIED PASS strings=2164 glyphs=1422 changed_files=77 unchanged_files=647 lba=unchanged
SHA256 58aa0dd720a0265d5962f23cca812d066365d296c81b8296ef4419d4ededa90e
EXIT_STATUS 0
```

### ROLLBACK

```text
"C:/Program Files/Git/bin/bash.exe" -c "test -x build/full-text/ROLLBACK.sh && build/full-text/ROLLBACK.sh build/menu-state-fix/applied.iso build/menu-state-fix/restored.iso"
{"mode": "rollback", "output": "build/menu-state-fix/restored.iso", "ranges": 20049, "sha256": "4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b", "size": 1696530432}
EXIT_STATUS 0
```

### RESTORED_BASELINE

```text
python -X utf8 tools/verify_build.py --kind baseline --iso build/menu-state-fix/restored.iso
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

### 原图对照、实装与回归

```powershell
python -X utf8 tools/inspect_menu_layout.py --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/verify_artwork_states.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --catalogue locales/zh-CN/graphics.json
```

`MENU LAYOUT PASS vertical=equal horizontal_difference=1.46% steady_state_only`；`ARTWORK STATES PASS members=1 pairs=4 installed=identical`。原版／旧版／修正的离线 UV 回读图在 `build/full-text/menu-state-readback.png`，不是游戏运行截图。

红灯复现旧资源：`MENU VISUAL FAIL`，退出 1，四行核心高度 10 且额外横线 59；新配方更严格地加入行/列滤波和两态宽度检查。合成测试同时覆盖缩小、放大、缺字、白线、错误区域／阈值，以及导入检查失败不落盘。

导入修正记录：布局 CLI 的 str/Path 类型错误已修复；首次从原图重新量化整幅 PNG 得到等价预乘颜色但改变额外透明 RGB 索引，未采用。改为以前版已验证 TIM2 为增量输入，严格只改四个选中字区，再编译为原盘到最终图的差分。新生成的重金边字稿因风格不合未安装。

清理已核对来源的 320 个临时/重复文件，共 6,895,617,398 字节：旧交付副本、正反向验证副本、干净源码重建目录及否定稿；原盘、当前 ISO、PoC 和必要证据保留。README 未改动。

没有启动游戏或模拟器、没有改动其设置/BIOS/存档。玩家截图证明上一版本中文菜单已实装，但修复后的切换动画、实际显示及其余完整流程仍由玩家验收。

## 2026-11-05 全部可读文本与图片

源码提交 `165bffdbc4bb4c09bc5324799e6c192ec38abbc7`，分支 `master`。两种 G362 的 `text-02` 改为无逗号的“请勿靠近”；新增 99 张原风格场景／物品／画廊重绘，更新 `graphics.json:artwork_files`、槽的 `install/disposition/artwork_rectangles`，并添加 `config.json:raw_images` 与独立 RGB24 导入／构建／回读路径。原 37 张界面差分及对应游戏字节保持。

全部正文 2164 物理槽、1422 主字形、113 名称／698 引用、270 网络字段／293 映射及完整协议继续通过。TIM2 图片累计 136 张唯一纹理、402 项可翻译文字、246 个物理成员，待重绘 0 项；2 个 D.I.A 标识保留，NETGUI 标题另计 1 项。模糊手稿与微字按用户决定保持原像素。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 当前测试 ISO | `dd107d508af30b61f0b1a9c98edb7a8659b1c517ffaf014c858138427e03f5d9` |
| 可逆差分 | `c3407a4a38ef9d350f710f9085205b368fe93d911f66f83a9e8df26819f2e68d` |
| manifest | `1769d16ec9df939d38fc88206a3879abd622ec5c42b1ac0f36f86c316deba1a5` |
| 回滚脚本 | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |

ISO 1,696,530,432 字节；差分 8,928,251 字节，20049 个区间。四个交付文件位于 `build/full-text/`：`Mystic-Nights-zh-CN-full-text.iso`、`DIFF_FILE.mnp.zip`、`VERIFICATION.txt`、`ROLLBACK.sh`。本地 VERIFICATION 保存绝对路径、完整命令、输入、字面输出和退出码。

改动前 254 项测试通过，改动后及干净源码重建均 260 项通过。以下真实命令均退出 0；公开记录的回滚输出路径转为仓库相对路径，未经缩写的原样输出保存在本地 VERIFICATION：

### BASELINE

```text
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

### MODIFIED

```text
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf
GRAPHICS PASS translated=404 installed=402 pending=0 texture_members=246 save_metadata=1
RAW_IMAGES PASS installed=1 resources=1
FULL_PATHS PASS names=113 references=698 network_strings=270 network_glyphs=293 agreement=1 extra_interface=38
MODIFIED PASS strings=2164 glyphs=1422 changed_files=77 unchanged_files=647 lba=unchanged
SHA256 dd107d508af30b61f0b1a9c98edb7a8659b1c517ffaf014c858138427e03f5d9
EXIT_STATUS 0
```

### ROLLBACK

```text
"C:/Program Files/Git/bin/bash.exe" -c "test -x build/full-text/ROLLBACK.sh && build/full-text/ROLLBACK.sh build/artwork-completion/applied.iso build/artwork-completion/restored.iso"
{"mode": "rollback", "output": "build\\artwork-completion\\restored.iso", "ranges": 20049, "sha256": "4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b", "size": 1696530432}
EXIT_STATUS 0
```

### RESTORED_BASELINE

```text
python -X utf8 tools/verify_build.py --kind baseline --iso build/artwork-completion/restored.iso
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

正向补丁结果与交付 ISO 逐字节相同；实际执行可执行 ROLLBACK.sh 后，恢复副本与原盘逐字节相同并再次通过全部 2164 个源槽。交付 ISO 仍保持修改状态。

原生读回 136 张纹理／246 个物理成员以及 1 张 RGB24 图；全部差分可逆，新 99 张 PNG 与 ISO 中解码像素一致。全部 TIM2 头部、CLUT、成员长度和允许区域外像素不变；原有 37 张图与上一交付逐字节相同。两种标牌的无逗号预览从最终 ISO 回读。

干净 Git 归档重新跑 260 项测试、完整构建及修改版验证；ISO、补丁、manifest、两张字体预览、回滚脚本 6 项逐一同 SHA-256。重复正向、回滚、重建和上一版 ISO 共 4 份，以及源码 ZIP、重复 raw 导入差分已在路径／尺寸／哈希预检后删除，共 6,788,126,977 字节。保留原盘、当前完整测试镜像和既有 PoC；模拟器目录未动。

本地原生审查辅助脚本的两次失败记录保留：一次为未使用的错误模块导入，一次为相同 JSON 的 CRLF/LF 字节差异；修正后原生回读通过。后者只规范化差分文件换行，不改变图像像素。

此结果完成已提取文字和可读图片的离线翻译、写回及构建；未启动游戏或模拟器。玩家需按 [TESTING.md](TESTING.md) 验收完整流程、存读档、结局及实际画面，正式发布门槛仍保留。

## 2026-11-04 界面与职员表续作

源码提交 `9f06afab6aae6b3f01fd0fe8ec3466c147c6d8a8`，分支 `master`。修改 `graphics.json:artwork_files`、图片槽的 `install` / `disposition` / `artwork_rectangles` 及其源哈希绑定差分。本轮新增30张界面贴图、146项文字、70个物理成员；累计37张、189项、77个物理成员。前7张已修正残影的图片差分逐字节保持。正文、字体、关联名称和网络文字输出保持。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 当前测试ISO | `b6631d64f19363bb90e916ad71fcfb3f6515ebda495e1f36f08f5ed22d4c3948` |
| 可逆差分 | `1bac6066d46be0b48cf51d50baea912140117015e646a485a1db74f7250961ac` |
| manifest | `c9d6bda4b7d4ccdb8f7f5a4fd728ee8bef76dfd6958249449ca4fe1ca5294e3a` |
| 回滚脚本 | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |

ISO为1,696,530,432字节；差分6,260,043字节、13825个区间。完整命令、输入、字面输出、退出码及绝对交付路径保存于本地 `build/full-text/VERIFICATION.txt`。

全部下列检查退出0：

```text
Ran 254 tests in 1.428s
OK
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
GRAPHICS PASS translated=404 installed=189 pending=213 texture_members=77 save_metadata=1
FULL_PATHS PASS names=113 references=698 network_strings=270 network_glyphs=293 agreement=1 extra_interface=38
MODIFIED PASS strings=2164 glyphs=1422 changed_files=52 unchanged_files=672 lba=unchanged
NATIVE PREVIEW PASS new_textures=30 source_palette_readback=identical
REBUILD PASS files=6 iso=identical patch=identical manifest=identical previews=identical rollback_script=identical
CLEANUP PASS files=6 bytes=6789551696
```

正向差分在隔离副本得到相同修改哈希；实际执行可执行 `ROLLBACK.sh` 后恢复原盘哈希，恢复副本再次通过全部2164源槽基线检查。原盘未改，交付镜像保留修改状态。仅做离线验证，没有启动游戏或模拟器。

干净Git归档再次跑254项测试、构建和完整资源验证；ISO、差分、manifest、两种字库预览和回滚脚本6项逐一同哈希。本轮30张原生PNG与正式构建中的差分回读逐像素相同；37份图片差分可逆，调色板、头部和允许文字区之外保持不变。新增通用图片导入器另用真实纹理跑命令行验证，6个新测试覆盖原盘身份、尺寸、允许区域、透明像素和重复调色板颜色索引。

清理前逐一核对路径、尺寸、哈希，删除正向/回滚/重建副本和上一版ISO共4份、重建源码ZIP及1张未采用的生成稿，共6,789,551,696字节。保留原盘、当前测试ISO、已有显示反馈的PoC和必要研究记录；没有清理模拟器目录。

目前仍有213项场景／画廊文字及NETGUI背景标题待原风格重绘，模糊微字按既定决定保留。原生预览不等于玩家美术或完整流程验收；手动检查项见 [TESTING.md](TESTING.md)。

## 2026-11-04 全文与七图重绘（残影修正）

源码提交 `9ae133001157535350df15d81fe0311e7312b880`。主目录2034条非空译文全部完成；实际正文2164槽、主字形1422，113名称/698静态引用、270网络字段/293映射及完整协议。图片只安装7张原风格重绘、43项文字，359项待重绘、2个技术标识保留；旧方块覆盖输出撤下。两张菜单图最终完整重建旧英文文字底纹和透明字层，不只清除亮色笔画。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 当前测试ISO | `452d2779b858572a05b4bf3478f7a12b8502eec9971912b9676dabb649e66412` |
| 可逆差分 | `f4608b824e23e0e7e59faeb9121142ddc84c686704954a9dfa85dad10743d333` |
| manifest | `17d5e650f98a09397c9278d0b269ad51514954b1a5ee04c55441fb685fdb27b3` |

全部命令退出0；本地 `build/full-text/VERIFICATION.txt` 保存完整命令、输入、字面输出与退出码：

```text
Ran 248 tests
OK
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2164
GRAPHICS PASS translated=404 installed=43 pending=359 texture_members=7 save_metadata=1
FULL_PATHS PASS names=113 references=698 network_strings=270 network_glyphs=293 agreement=1 extra_interface=38
MODIFIED PASS strings=2164 glyphs=1422 changed_files=36 unchanged_files=688 lba=unchanged
REBUILD PASS files=6 iso=identical patch=identical manifest=identical previews=identical rollback_script=identical
```

ISO 1,696,530,432字节；差分2330553字节、4648个区间。正向补丁在独立副本得到同一修改哈希，实际执行可执行`ROLLBACK.sh`后恢复原盘哈希；恢复副本再次通过全部2164源槽检查。原盘不改，交付镜像保持修改状态。

干净Git归档重新跑248项测试、构建及完整验证，ISO、差分、manifest、两种字库预览及回滚脚本6项逐一相同。已删除7个明确的重复/过时生成文件，共8485456551字节；保留当前测试镜像、原盘和已收到显示反馈的PoC。必要格式与失败研究证据保留。

七张图片的差分逐项反向恢复原纹理，调色板、头部和允许文字区外像素不变。最终预览从实际TIM2回读，未将高分辨率生成稿直接当成交付图。当前仍待玩家美术/游戏流程验收，没有启动游戏或模拟器。

## 2026-11-04 首批全文版

`partial`配置实际装入340个物理正文槽（328条逻辑译文）、646字形，209项名词表与113个道具译名已建立；名称修改不在本次ISO中。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离副本回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 首批ISO | `a40878eac2a5645b810d13ed69c8f8d8317ca8d3652f584765e120ced2907e95` |
| 差分 | `b8fde390baeb53bbce8cf592dc4a88a87efe064bd2c9d215d04bcb5967af5ff6` |
| 实际图集预览 | `a0ed8c21e0fa04ba8a4a77f3a2c90716d3624f06278914239565346d95bb63ce` |

ISO为1,696,530,432字节；差分1,364,389字节，3367个区间。

实际命令均退出0，完整输入/输出保存在本地`build/partial/VERIFICATION.txt`：

```text
Ran 142 tests
OK
BASELINE PASS files=724 resources=209 scripts=179 source_slots=340
MODIFIED PASS strings=340 glyphs=646 changed_files=6 unchanged_files=718 lba=unchanged
```

正向差分在隔离副本上得到同一修改哈希；交付`ROLLBACK.sh`反向产生原盘哈希，恢复副本再次通过340源槽基线检查。仍保留修改镜像，未把交付版回滚。字体保护1356码位，重算集合与manifest相同；英文资源不参与构建。

从源码提交`90bcd55bf58e00dc626e8e98ee4c60e505e0f101`的干净Git归档重跑142项测试、构建和完整修改版验证，ISO、差分、预览、manifest四项SHA-256均与交付逐项一致。清理了三份重复验证镜像、临时源码ZIP及一次性译文填入脚本；保留原盘、已反馈的PoC和当前分批版。

菜单中文已有玩家反馈；本批对白推进、分页、存读档与完整流程仍待手动验收，没有启动游戏/模拟器。

## 历史：14条PoC

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
