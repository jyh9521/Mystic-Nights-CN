# 汉化构建：离线验收

## 2026-11-06：意见 e004 的28项修订（当前）

原盘 SHA `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` 保持；新 ISO 为 `17e7dc6d9e2f4138493975f0b8697744f4347fdd71af46284e94b173b4e2a44d`，1696530432字节、24504个可逆差分区间。原始意见下载文件104717字节/hash `576aa60d674aea1568b23be75d23f29c9711aea9025968c27311888a445573d0` 保留。

相对意见所对应的e004382f镜像，只修改28张TIM2/70个物理成员/34个RES，690个光盘文件逐字节未变；153项已认可图片、其他163张汉化TIM2、两张明确保留原图、正文/字库/ELF/RGB24和运行包不变。相对原盘的整套汉化仍为77个修改文件，不与这次34个RES混淆。具体处理见[IMAGE_FEEDBACK_E004.md](IMAGE_FEEDBACK_E004.md)。

原365项Python基线通过；新增4项跨轴对齐测试先失败再修复，最终369项及两组JavaScript测试通过。13对胶囊文字、4组真实控制器文字检查通过；130块原索引指纹分开检查66块保留材质和64块应改变内纹/旧字边缘，零不符。字号、中心和hash检查均不等同于玩家美术认可。

最终筛查页从正式ISO回读：1141个稳定编号，194张默认审查，28张修复筛选，153项未变认可继承；1339 PNG/1343文件重新读取并核对hash/RGBA。实际生成HTML在Node离线运行，旧意见只读、新意见空白和154条导出/导入往返通过；没有把此项写成浏览器UI实测或游戏画面验收。

菜单新键 `de1430d7758e480-28b27f92b46f3d61-00002253.png` 已装到现有配置指向的真实Textures目录，旧键按收据撤销。隔离旧→新→旧安装回滚恢复原PNG；真实8页字库、2份PNACH、当前INI和勾选保持原字节。没有启动游戏或模拟器。

源码 `625552aabe5da3f10589fac1f8ae82f34e96a8bb` 的干净归档重建26件核心输出和1343件网页输出，共1369件逐字节一致。正式`ROLLBACK.sh`在独立修改副本上执行，恢复原盘hash并做全长逐字节比对与基线检查；正式交付ISO仍为17e7dc6d修改状态。重复镜像/重建目录仅在这些证明完成后清理，原始反馈、当前输出、前版可逆补丁和安装收据保留。后续收尾提交只补本文和意见文档，不改变已重建源码或二进制。

完整原样命令、输入、stdout/stderr、退出码及四个交付路径见本地`build/full-text/VERIFICATION.txt`；README保持原blob不变。所有图仍由玩家进行最终游戏内/美术验收。

## 2026-11-05：意见 c7 的91张图修订（历史）

原盘SHA `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` 保持，旧ISO `c7c2d8c2e33f809e27927ce815e2c9ab3748ac8df9cb1bc839403c0157931f1b`；新ISO `e004382f45ae9c9a5a4d2b076db16e819102946aa53cba3b157e3a112aebfce3`，1696530432字节、24593个差分区间。

意见文件91张全部覆盖：89张修订、2张精确恢复原图；最终ISO独立回读确认47盘文件/193物理成员/91源图改变，另外677盘文件、102张其他汉化图、正文/字体/ELF/RGB24及5运行包文件逐字节不变。参见[IMAGE_FEEDBACK_C7.md](IMAGE_FEEDBACK_C7.md)。当前计数191汉化TIM2/359引用/502字段，另1张RGB24。

365项Python与两组JavaScript测试通过。页脚不等距基线8/8失败，新图0/8；最终ISO还验证29个物理锚点组、18状态对、28尺寸组及9个透明边界。52块机械底纹按此次意见恢复原字节，12块EXIT旧字边缘继续改变；不能再把“删除原材质”当成去字干净的证明。空shape-pair不冒称完美轮廓/居中验收。

网页保留1141稳定编号，默认194张（192汉化载体及2恢复原图），修订筛选91张；旧93项认可仅因对应图字节不变而继承，新图待确认。1339张PNG/1343文件均HTTP200且字节/RGBA一致。真实浏览器完成输入框翻页、实际JSON导出94项（93认可及1条受控测试意见）、文件选择器导入94项、清空测试意见与重载；结束为93认可、0条新意见。玩家原意见文件保留，旧意见独立只读显示。

真实PCSX2目录中菜单键由 `794c4ae416f3c9ef` 更新为 `169a7046184c6930`，旧键按安装收据撤销。8字体PNG、2份PNACH和当前INI字节保持。隔离旧→新→旧回到原菜单包，未启动模拟器。实际加载和玩家美术确认仍待手动检查。

干净源码提交 `9d74a5f17cb777f8681e57d32b95ee72aad0f628`，以同一原盘、锁定字体、可选xxhash及显式本地反馈为输入：365测试和两组JS测试通过，26件核心交付、1343件网页文件合计1369件逐字节一致。标准路径重新验证通过；正向副本等于当前ISO，标准ROLLBACK.sh的隔离输出与原盘完整字节一致，当前ISO仍为修改状态。Windows实测使用Git Bash完整路径，未使用指向缺失WSL的系统bash别名。

清理4535件已登记SHA的重复/草稿/隔离构建文件，共10487913753字节；包括验证用ISO副本和代理产生的测试下载。真实玩家意见JSON、原盘、当前交付/网页、已采用素材、旧版本可逆差分、实际安装/撤销收据和完整日志保留。

完整基线/修改版/隔离回滚原样命令、字面输出、退出码、四个绝对交付路径、身份检查与清理/推送状态写入本地 `build/full-text/VERIFICATION.txt`；README不变。下方记录均为历史，不覆盖当前意见修订结论。


## 2026-11-05：全量图像与反馈网页（c7意见前的历史交付）

分支 `master`；原盘 `4eacce4e…` 保持。修改前ISO `8e2277f33d3d9bb68ad8b0ff74504636e69ad8cece0b2161e7a22fe5d4738b68`，新标准ISO `c7c2d8c2e33f809e27927ce815e2c9ab3748ac8df9cb1bc839403c0157931f1b`。差分24160区间，ISO长度1696530432。

全量193张汉化TIM2/361引用、504图字字段及RGB24独立对照，159张其他UI来源联查。8图/20成员/15盘文件修复，其他185汉化图、主菜单、正文/字库/ELF保持。两类已知残留在旧ISO检测64/64保留、最终ISO为0/64；不能把像素巧合、同色量化或空shape-pair检查称为美术认可。

357项Python测试、两组JS测试、18状态对/21透明边界/49尺寸组、整盘验证和源绑定原生回读通过。网页包含1141载体、默认194汉化图，1341 PNG及4入口文件HTTP200且字节/RGBA一致；实际浏览器意见下载、重载和重新导入通过，测试意见已清空。静态文件页无网络数据依赖，浏览器实际验证使用回环HTTP。

PCSX2当前配置路径下9张PNG已缺失，按原路径补回8字库页与1菜单，不写INI。两份既有PNACH和两份当前INI字节保持；新的安装/撤销收据及缺失状态快照在本地审查证据中保留。隔离安装/撤销回到9 PNG缺失的基线，未启动模拟器。

标准四件为 `build/full-text/` 下最新ISO、DIFF_FILE.mnp.zip、VERIFICATION.txt、可执行ROLLBACK.sh；网页为 `build/image-review/index.html`。完整原样命令、输入、字面输出、退出码、正反向和清理/推送身份记录在本地VERIFICATION.txt，不添加到README。

干净源码 `6ca1fbcb4151e4b680e16c35d22435c190b1f1bf` 独立构建357项Python测试、两组JavaScript测试通过；1371件交付文件（26核心、1345网页）逐字节一致。标准路径复验：`ARTWORK MATERIAL PASS retained_source_patterns=0/64`、`ARTWORK REVIEW PASS unique=193 physical=361 ledger=closed provenance=offline-not-game-approval`。空轮廓对明确输出`NOT_DECLARED pairs=0`，不称作居中证明。正向副本与当前ISO、回滚副本与原盘均完整字节一致，恢复原版状态，当前修改版保留。

清理1841件重复构建/隔离副本、临时测试文件，共8,725,286,608字节，删除前逐文件SHA登记并检查绝对路径；原盘、当前交付、网页和实际安装/撤销证据保留。源归档、正反向ISO副本已完成验证后清理，不要求保留大体积重复游戏数据。实际9张PNG与两份既有PNACH再次读回，当前全局/游戏INI字节不变。所有完整日志和文件身份保存在本地构建证据目录。

## 2026-11-05：完整菜单无字内床（后续全量复核已替代）

主菜单的字形状残留没有因“原盘已有”而满足玩家要求。当前只重建4个完整119×16内床，共7616像素；先独立检查无字材质，再叠回相同彩色前景。不是再次更换字体，也不是拿新中文盖住旧字。

- 旧ISO：`f4e6bfbcf6e5153a09818199388af792e639923b8613e0bc7c012acd73c250bf`；旧主图b5f4cc14。
- 新ISO：`8e2277f33d3d9bb68ad8b0ff74504636e69ad8cece0b2161e7a22fe5d4738b68`；新主图99ebe95b。
- 新旧ISO只变RES/LOGO.RES:L001_004.TM2，共4815索引；另外723文件、192汉化图、8字体页及5运行文件不变，原LBA/头/CLUT/外框与火光保持。
- 8个旧暗纹样块原样保留由8/8→0/8；空床所有7616像素重新取样。533/612样块索引不同，79个同色是量化巧合，不写成612像素全部不同。独立看图与全床来源验证另于字形尺寸检查。
- 12个高清前景RLE层逐字节一致，原彩色字稿、抗锯齿、大小、位置不改。修改版从标准ISO独立回读，不只改预览。
- PCSX2精确新菜单键794c4ae416f3c9ef替换旧66c8052abf7573ce；旧键通过旧收据受保护撤销，新键安装读回。其余10个自管文件及两份INI原字节保持。旧菜单包本地保留供安装撤销，未启动模拟器。

四件仍是build/full-text中的ISO、DIFF_FILE.mnp.zip、VERIFICATION.txt、可执行ROLLBACK.sh。350测试、源/修改版全盘验证、隔离正反向与干净源码重建的原样命令/输出、四个绝对路径及当前推送身份写入本地VERIFICATION。后文保留历史状态，f4e6bfbc不再是当前交付。

干净归档源码 `bddc245dc5d1fe10580d3ec4c5dd7ae451a1a05d`：350测试通过，26件输出（11核心、13字体包、2菜单包）与交付件逐字节一致。正向副本与修改版、回滚副本与原盘均完整字节比较一致。清理463件重复/临时文件、6,914,795,017字节；当前镜像、原盘、安装撤销包和全部验证日志保留。

## 2026-11-05：恢复既有字稿与反馈修正（历史，完整内床随后修正）

分支 `master`。原盘SHA `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`，ISO长度1,696,530,432，差分24021区间。当前四件为 `build/full-text/Mystic-Nights-zh-CN-full-text.iso`、`DIFF_FILE.mnp.zip`、`VERIFICATION.txt`、可执行 `ROLLBACK.sh`。

| 文件 | SHA-256 |
|---|---|
| `Mystic-Nights-zh-CN-full-text.iso` | `f4e6bfbcf6e5153a09818199388af792e639923b8613e0bc7c012acd73c250bf` |
| `DIFF_FILE.mnp.zip` | `2b5e3839c49a048acc37cd8bf113de03b39b66b10a960df759a962591792f22e` |
| `manifest.json` | `3cff2f6722f4493785779cfe2fd817a637229e0db5d42f72b9fb7853ed9d419f` |
| `ROLLBACK.sh` | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |

### 干净归档与收尾

源码 7ec6ecd27a0ed9887f0ad70562d445a271210831 的干净归档：350测试通过，11核心文件+13字体包文件+2菜单包文件共26件逐字节一致。原盘/正向副本/两份独立回滚副本已完整字节比较；标准可执行回滚入口实际通过。清理842个废稿/重复/临时文件，8629791866字节，保留原盘、当前镜像、已采用字稿、QA和实际安装撤销收据。

### 变更与边界

源绑定的18张图/54引用已从最终ISO独立回读，175张其他汉化图保持。主菜单用既有彩色字稿SHA5722e343…，不是否定的粗块字；同16px字格与AA，原生中心误差≤0.5px。第三行阈值高度15/16px、部分源裁切边缘仍有像素，不能据此宣称完美美术或无任何裁切损失。当前修正保留旧样式，运行画面须玩家确认。

主逻辑2178字段+镜像/补充共2306物理字段、1433字形、113名称/698引用、网络270、协议1均通过。全量2487字段移除25处多余句号；504图字段安装到193纹理/361成员，2标识保留。

新ELF SHA `20de884f0728dc3303932a1622cc5de351e983469b45bb94b7cde19b0f7cbf27`，其PCSX2 XOR CRC恰仍是634DBCA7。13可选指令不烘焙进ISO，纵轴10752、横轴1792、存储50及16组合回滚通过。实际安装2PNACH+8字体PNG+1菜单PNG。游戏INI与全局INI原字节不变，宽屏及三项作弊继续保留玩家原选择。PNG按当前配置的Textures/SERIAL目录，不误用程序目录或CRC目录。

### 实测命令（完整原样日志见本地 VERIFICATION.txt）

```text
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
python -X utf8 -m unittest discover -s tests
Ran 350 tests
OK
EXIT_STATUS 0
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf
MODIFIED PASS strings=2306 glyphs=1433 changed_files=77 unchanged_files=647 lba=unchanged
SHA256 f4e6bfbcf6e5153a09818199388af792e639923b8613e0bc7c012acd73c250bf
EXIT_STATUS 0
```

350测试的原样耗时行在本地日志；上面只列计数。原版297测试也在独立旧源码归档通过。正向补丁副本与当前ISO字节一致，回滚副本与原盘字节一致，修改版保留；运行补丁和HD包安装器另经独立目录撤销，不对真实配置做演示性回滚。新源码干净归档重建及清理/推送身份在最后收尾记录；没有把这些离线证据等同于游戏启动或玩家认可。

## 2026-11-05 START 外缘修正与 PCSX2 实际安装

本节保留 START 修正时的历史交付。之前 `aae84a…` 确为当时最新输出，但图自身仍留有 START 外缘光晕；没有把“文件已安装/同哈希”等同于“画面干净”。已有用户启动日志的路径和 ELF CRC 与该交付一致，本次工具没有启动游戏。

### 变更和实际目录

- `L001_004.TM2` 字段 `076f1530ee2a/text-06`、完整字床 `[0,225,214,31]` 及 `clear_regions`。旧上沿检测 `START BACKGROUND FAIL ... nontransparent pixels=781`，退出 1；新四边全部为 0，退出 0。新字由内置 imagegen 重绘，14px 核心注册，不复制旧字 alpha。完整提示词见 `assets/artwork-authoring-review.json` 的 `start-prompt-clean-gutters`。
- 新旧 ISO 相比只变 `RES/LOGO.RES:L001_004.TM2` 的 2813 个索引；另外 723 个文件、该图其他字区、CLUT/UV/头/长度和另外 186 张汉化纹理不变。正文、字库和 ELF 没变，中文 CRC 仍为 `634DBCA7`。
- 显式安装器读取现有用户目录 `inis/PCSX2.ini` 的 Folders 设置，实际安装 `patches/SCKA-20055_634DBCA7.pnach`、`cheats/SCKA-20055_634DBCA7.pnach` 及 `gamesettings/SCKA-20055_634DBCA7.ini`。程序目录不是此实例的数据目录。16:9 预选；本游戏 EnableCheats=true，但三项作弊组默认均不选。全局 INI、其他游戏、BIOS 与存档保持。
- 先在只含相关目标状态的隔离 profile 安装再撤销，3 个文件恢复到初态；随后实际安装。安装 receipt 和前后 hash 保存在本地 `build/start-prompt-fix/runtime-installed/`，撤销须显式运行安装器 `--rollback`，不随 ISO 回滚擅自操作模拟器。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| 当前 ISO | `9e166e6f9aec5574ee72a2219691cde500d3d6e07239c006c166ea8298b3c858` |
| DIFF_FILE.mnp.zip | `9f26fe50384ab49d239f862c1ef62a1f8cb6c351a8543c491abb13a1bd74749d` |
| manifest.json | `cf6cb3bd010c2ebe2c6daf452fd6b1cee4bb0bfc4e42374a1ef80df29bd02818` |
| ROLLBACK.sh | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |
| 新 L001_004 | `0427965abaf88f9b58601b06cc52b9cb6f7238d5542cf8c2513529ffc27fb82a` |

交付四件仍为 `build/full-text/Mystic-Nights-zh-CN-full-text.iso`、`DIFF_FILE.mnp.zip`、`VERIFICATION.txt`、可执行 `ROLLBACK.sh`。ISO 1,696,530,432 字节；差分 10,444,679 字节、23772 个区间。所有下列命令退出 0；阴影红灯复现单列为预期退出 1。完整绝对路径、原样输出和退出码在本地 VERIFICATION，公开记录只规范化输出中的本机路径。

### BASELINE / MODIFIED / ROLLBACK

```text
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf
MODIFIED PASS strings=2306 glyphs=1433 changed_files=77 unchanged_files=647 lba=unchanged
SHA256 9e166e6f9aec5574ee72a2219691cde500d3d6e07239c006c166ea8298b3c858
EXIT_STATUS 0
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/full-text/DIFF_FILE.mnp.zip --output build/start-prompt-fix/applied.iso
{"mode": "apply", "output": "build/start-prompt-fix/applied.iso", "ranges": 23772, "sha256": "9e166e6f9aec5574ee72a2219691cde500d3d6e07239c006c166ea8298b3c858", "size": 1696530432}
EXIT_STATUS 0
"C:/Program Files/Git/bin/bash.exe" -c "test -x build/full-text/ROLLBACK.sh && build/full-text/ROLLBACK.sh build/start-prompt-fix/applied.iso build/start-prompt-fix/restored.iso"
{"mode": "rollback", "output": "build/start-prompt-fix/restored.iso", "ranges": 23772, "sha256": "4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b", "size": 1696530432}
EXIT_STATUS 0
python -X utf8 tools/verify_build.py --kind baseline --iso build/start-prompt-fix/restored.iso
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
BYTE_COMPARE PASS forward=identical rollback=identical original=preserved modified=retained
EXIT_STATUS 0
```

恢复的是隔离副本的全部原盘字节/字段/资源结构，交付 ISO 仍为修改版；不是运行游戏的恢复证据。297 项单元通过，包含低透明残影、错误边界、安装中途失败自动恢复、已有 INI 不覆盖、包损坏与撤销目标被用户修改等回归。16 组合运行指令夹具、1792 轴/角度及 50 存储案例仍通过。

实际安装命令如下；数据目录应以本机 profile 为准，而不是照抄程序路径。

```text
python -X utf8 tools/install_runtime_patches.py --package build/full-text/runtime --data-dir "C:/Users/noway/Documents/PCSX2" --receipt build/start-prompt-fix/runtime-installed --enable-patch 16比9宽屏 --allow-cheats
RUNTIME INSTALL PASS files=3 crc=634DBCA7 state=installed
EXIT_STATUS 0
```

手工下一步：冷启动新 ISO、不加载旧即时存档，检查 START 闪烁边缘与实际背景混色；到本游戏属性选择所需金手指。所有开关实际玩法效果仍待玩家验收。

### 干净重建、安装回读与清理

工程源码提交 **`d1f1ac2e05e1f7628b413a4748264a82a2ee75c3`**，分支 `master`。从该提交 `git archive` 到新目录，仅只读使用原盘和锁定字体；297 项单元、完整构建、整盘验证及运行指令夹具重跑通过。ISO、差分、manifest、两张字库预览、可执行回滚脚本及 5 件 runtime 输出全部同尺寸/同 SHA。

```text
REBUILD PASS files=11 iso=identical patch=identical manifest=identical previews=identical rollback_script=identical runtime=identical
EXIT_STATUS 0
INSTALLED READBACK PASS pnach=2 game_ini=1 crc=634DBCA7 wide=selected cheat_groups=0 global_ini=unchanged emulator=not-started
EXIT_STATUS 0
CLEANUP PASS files=388 bytes=6853855575 original=preserved modified=retained runtime_receipt=retained
EXIT_STATUS 0
```

清理前解析/限定绝对目标路径、拒绝重解析点，核对旧 ISO、隔离正反向副本和重建 ISO 的已知 SHA，并保存每个删除文件的路径、长度和 SHA。删除旧 `aae84a…` ISO、正反向副本和干净重建临时目录，共 388 文件、6,853,855,575 字节；保留原盘、当前修改版、研究/原样命令记录和实际安装 receipt。实际安装的三个文件逐一重新打开，其 hash 与生成包/本游戏 INI 一致；全局 PCSX2.ini 与安装前 hash 一致。README 保持原样。本小节和状态页是对已验证源码提交的纯文档收尾。

## 2026-11-05 全盘复核与运行补丁

以下是当前交付；后续章节保留历史哈希与当时统计。原盘保持不变，当前 `build/full-text/` 留存的是修改版。未启动游戏、模拟器，也未改动 PCSX2、BIOS、设置或存档。

### 修改范围和实装

- 原盘全部 1140 张唯一 TIM2 / 2634 个物理引用分类；187 张汉化纹理、343 个物理成员、492 项图字写入，2 项 D.I.A 标识保留。51 张新覆盖，4 张旧成稿修订，132 张旧成稿逐字节不变。全盘范围见 [ARTWORK_AUDIT.md](ARTWORK_AUDIT.md)。
- 补译 142 个 SCENEDEF 房间 ALIAS；正文 2178 条逻辑字段（2176 非空、2 源空白），加文档镜像和 38 个补充 ELF 共 2306 个物理字段。ROOM 键、占位符、换行数量及游戏数值保持。
- 91 条括号单句、4 页文档显式换行和 1 条网络引号行修订；RenderString `0x155EB0..0x155F40` 的 144 字节原位扩展阻止禁行首标点自动换行。22 个标点字码表位于 `SCKA_200.55@001522a0` 首个 NUL 后的已验证空余容量。
- 1433 个字形采用 BOX / 24 / 224 覆盖策略；原度量、CLUT 与 ASCII 保持。两个原生字库预览及最终 ISO 八张字库回读一致。
- 独立输出 16:9、水平轴反转、无限子弹、无限生命四组 PNACH，不把十处可选写入烘焙进 ISO。原版 CRC `2383B74A`、本中文版本 CRC `634DBCA7`；来源与关闭后冷启动方法见 [RUNTIME_PATCHES.md](RUNTIME_PATCHES.md)。

| 对象 | SHA-256 |
|---|---|
| 原盘 / 隔离回滚结果 | `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b` |
| Mystic-Nights-zh-CN-full-text.iso | `aae84a054389d481f1bf735038b532f9d81bb4558d49f3adc28696ed59ff4746` |
| DIFF_FILE.mnp.zip | `6292198955a1e501650b67d7b69199f63f3192b2e7ad04bd96ece81cb417244b` |
| manifest.json | `d34f50d62785f88695bc7839955d6585f7647f4a81f574d41d4b08e6841280e5` |
| ROLLBACK.sh | `307d0f2e92a2ce94a8697b5d2cc08ff99f291c817271488c7cb5e08a598044ae` |

四件交付：`build/full-text/Mystic-Nights-zh-CN-full-text.iso`、`build/full-text/DIFF_FILE.mnp.zip`、`build/full-text/VERIFICATION.txt`、`build/full-text/ROLLBACK.sh`。ISO 1,696,530,432 字节；差分 10,442,604 字节、23767 区间。完整本机绝对路径、未经改写的命令及输出保存在本地 VERIFICATION；公开记录将输出中的本机路径转为相对路径。

### BASELINE

```text
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

### MODIFIED

```text
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf
TEXT_LAYOUT_REPLAY PASS glyph_keys=1561 explicit_breaks=804 no_line_head_punctuation=pass
TEXT_LAYOUT PASS punctuation_codes=22 code_bytes=144 owner=SCKA_200.55@001522a0
GRAPHICS_SOURCE_REVIEW PASS unique=1140 physical=2634 member_name_variant_closure=complete
GRAPHICS PASS translated=494 installed=492 pending=0 texture_members=343 save_metadata=1
RAW_IMAGES PASS installed=1 resources=1
FULL_PATHS PASS names=113 references=698 network_strings=270 network_glyphs=293 agreement=1 extra_interface=38
FONT_RASTER PASS glyphs=1433 policy={'filter': 'box', 'edge_floor': 24, 'edge_ceiling': 224} original_metrics_cluts=unchanged
MODIFIED PASS strings=2306 glyphs=1433 changed_files=77 unchanged_files=647 lba=unchanged
SHA256 aae84a054389d481f1bf735038b532f9d81bb4558d49f3adc28696ed59ff4746
RUNTIME_PATCHES PASS files=5 groups=4 crc=634DBCA7 disc_features=optional
EXIT_STATUS 0
```

### ROLLBACK / 恢复状态

隔离正向应用先生成 `build/full-audit/applied.iso`，SHA 与交付相同，随后运行可执行回滚脚本；交付镜像本身没有被回滚。

```text
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/full-audit/delivery/DIFF_FILE.mnp.zip --output build/full-audit/applied.iso
{"mode": "apply", "output": "build/full-audit/applied.iso", "ranges": 23767, "sha256": "aae84a054389d481f1bf735038b532f9d81bb4558d49f3adc28696ed59ff4746", "size": 1696530432}
EXIT_STATUS 0
"C:/Program Files/Git/bin/bash.exe" -c "test -x build/full-text/ROLLBACK.sh && build/full-text/ROLLBACK.sh build/full-audit/applied.iso build/full-audit/release-restored.iso"
{"mode": "rollback", "output": "build/full-audit/release-restored.iso", "ranges": 23767, "sha256": "4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b", "size": 1696530432}
EXIT_STATUS 0
python -X utf8 tools/verify_build.py --kind baseline --iso build/full-audit/release-restored.iso
BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306
SHA256 4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
EXIT_STATUS 0
```

正向执行时路径为暂存 `delivery/`，核对哈希后整目录晋升到标准 `build/full-text/`；命令记录保留原执行路径。隔离正向结果与交付、隔离回滚结果与原盘均逐字节一致。原版全部 2306 字段及资源结构检查恢复；这证明文件恢复，不把它描述成运行游戏的行为测试。

### 单元、原生回读及开关夹具

286 项单元测试通过。最终 ISO 四张状态成员共 18 对：`ARTWORK STATES PASS members=4 pairs=18 installed=identical`。最终 ISO 的 187 对原生原图/中文回读、26 张无损 PNG 和主字体预览已打开核查；图片大小/调色板/区外像素及原文控制符纳入机器验证。

运行夹具 16 种组合正向后逐字节撤销；1792 组轴/角度输入、50 个实际 SB/SH/NOP 存储案例通过，宽屏投影水平 512→384、垂直乘积误差约 0.5ppm。它们属于有界指令及数据检查，不是 PCSX2 执行证据。

待玩家冷启动验收：按钮和加载的实际混色/动画、字体清晰度、房间名显示、全剧情换行、宽屏/HUD、三项金手指的所有玩法路径。模糊手稿及无法可靠辨认的装饰微字按既定要求保持。

### 干净源码重建与清理

验证源码提交 **`3cde79e4cc38bb767046aa5cad58cfd3d47c34ee`**，分支 `master`。使用 `git archive` 提取已提交源码，不复制当前工作区；只读使用玩家原盘和锁定字体，重新运行 286 项单元、完整构建、整盘验证及运行补丁夹具。六件基础输出与五件 runtime 输出的尺寸、SHA-256 全部一致。

```text
python -X utf8 -m unittest discover -s tests
Ran 286 tests in 4.147s
OK
EXIT_STATUS 0
python -X utf8 tools/build_locale.py --iso "[full2]미스틱 나이츠(K).iso" --font build/fonts/NotoSansCJKsc-Regular.otf --locale zh-CN --output build/full-text
BUILD profile=full-text strings=2306 glyphs=1433 changed_files=77
OUTPUT sha256=aae84a054389d481f1bf735038b532f9d81bb4558d49f3adc28696ed59ff4746 size=1696530432
EXIT_STATUS 0
REBUILD PASS files=11 iso=identical patch=identical manifest=identical previews=identical rollback_script=identical runtime=identical
EXIT_STATUS 0
CLEANUP PASS files=1825 bytes=13920222726 original=preserved modified=retained evidence=preserved
EXIT_STATUS 0
```

上述干净重建命令在临时源码根运行，原盘/字体参数实际使用主工作区绝对路径；完整 argv、原始输出、提交号与 11 件身份保存在本地 `build/full-audit/reproducibility.json` 及 VERIFICATION。隔离验证完成后清理 1825 个文件、13,920,222,726 字节；每个删除文件先记录路径/长度/SHA，递归目标先核验解析后的绝对路径、原盘/交付身份及重建完成状态，拒绝重解析点。旧 PoC、旧交付、两次否定构建、正反向副本、重建临时 checkout、创作临时依赖和两张否定图稿已移除；原盘、当前修改版及研究证据保留。

删除执行成功后，字节总数由预先保存的文件清单重新相加，原执行日志和汇总修订分别保留，不覆盖原始命令输出。`README.md` 保持不变；本节及状态页属于对已验证源码提交的纯文档收尾，不改变构建输入或产物。

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
