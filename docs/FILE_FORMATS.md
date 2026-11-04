# 文件格式

本文件的 Verified 均限定于 `assets/game-version.json` 中的韩版原盘。

## ISO9660 — Verified

2048字节扇区，Primary Volume标识`MN`；724文件、51目录（含根）。目录记录中的LBA、长度和卷号双端副本须一致。解析器拒绝越界、多extent、交错文件、重复路径、目录环和文件/元数据重叠。

构建仅把同长度payload写入原LBA，整盘目录/日期/路径表不变。

| 文件 | LBA | 字节长度 |
|---|---:|---:|
| SCKA_200.55 | 826685 | 3428048 |
| RES/SYSTEM.RES | 798908 | 2363779 |

工具：`src/mysticnights/iso9660.py`。

## RES 1.30 — Verified

Header：12字节`31 2e 33 30 00 00 00 00 42 75 69 6c`（`1.30\0\0\0\0Buil`）。随后恰有8组，组号在代码中从0起算。

每组：u32LE成员数；每成员：

| 相对成员头偏移 | 长度 | 字段 |
|---|---:|---|
| 0x00 | 32 | CP949/ASCII名称，NUL终止 |
| 0x20 | 4 | payload字节数，u32LE |
| 0x24 | 上述字节数 | 原样payload |

成员之间不加对齐。209个原版RES均按此结构恰好消耗到文件末尾。第5组包含SCR；已调查场景的第7组包含SCN，其他组语义不猜测。

| 资源/成员 | payload文件偏移 | 长度 |
|---|---|---:|
| SUBSYS / EVENT.SCR | 0x22BE34 | 237606 |
| SUBSYS / ITEM.SCR | 0x265E7E | 33754 |
| SUBSYS / VAMPIRE.SCR | 0x26E27C | 10034 |
| UI/ITEM / DOCUMENT.SCR | 0x18D2E0 | 28777 |
| UI/DOCUMENT / DOCUMENT.SCR | 0x71B04 | 28777 |
| NETSUB / ITEM.SCR | 0x7F93E | 6324 |

工具：`resources.py`；只接受等长度替换，保留未知字段和所有未改字节。

## SCR — Verified

以`SCR_TYPE `开头，ASCII命令与CP949引号字段混排。引号外`;`开始注释。字段容量不含两侧引号。上游存在字段内NUL补齐；原版当前提取的字段不含NUL。解析器容许已确认的NUL后NUL/空格填充，不容许NUL后任意新文本。

稳定ID为`MEMBER.SCR@成员内8位十六进制偏移`；跨容器前加`RES/path:`。PoC剧情：`EVENT.SCR@00000c77`，17字节，EVENT_ID=10，第133行，`처음 있는 일이다.`→`这还是头一回。`。

`TEXT`/提示/描述是显示字段；`NAME`等同时作键的字段独立分类，默认禁止写。标签`<BR>`、按键符号、printf等按顺序保护。无改动提取/回填在全部179个SCR上逐字节一致。

## FONT.FNT — Verified

在SYSTEM.RES中的payload起点`0x19fc18`，长度35550。开头u32LE=2539，之后2539条14字节记录：

| 相对记录偏移 | 类型 | 含义 |
|---|---|---|
| 0x00 | u32LE | 纹理文件名djb2哈希 |
| 0x04 | u16LE | 字形键，按数值严格递增 |
| 0x06 | u16LE | x |
| 0x08 | u16LE | y |
| 0x0A | u16LE | width |
| 0x0C | u16LE | height |

95 ASCII、94 Jamo（A4A1..A4FE）、2350韩文音节。非ASCII宽13、高14；LoadFont运行逻辑Y+1/H-1，可见高度13。查找代码写死2539条，扩FNT不是独立可用的方案。

## 字体TIM2配置 — Verified，仅限字体

8张`FONT_1.TM2`..`FONT_8.TM2`，各66624字节，256×256、8bit索引、单图。通用图片TIM2可能采用其他格式，当前解析器不声称支持所有纹理。

- Magic/版本：`TIM2 04 00 01 00`。
- 文件头16字节，picture header48字节；pixels从0x40开始，共65536字节，线性布局。
- 后接1024字节RGBA CLUT，共256色；clut type=3使用CSM1的bit3/bit4交换。
- PS2 alpha范围按0..128解读；生成器保留原CLUT，只量化字形覆盖率。
- 字体名顺序与字符顺序相反：FONT_8含ASCII/早期字码，FONT_1含末尾韩文。

工具：`font.py`、`tools/inspect_font.py`。

## SCN局部道具结构 — Verified模式，完整格式未验证

已发现99个`68 00 + name[32] + GEO名称[32]`模式，名称均在113个规范道具名中。匹配必须核对完整NUL终止名称、前缀及后继GEO字段；原NUL后的旧填充值保持。最小可改容量以原字符串长度为准，不扩成32字节。

## 关联名清单与正文目录 — 本项目定义

`mystic-nights-linked-names` v1保存源范围hash、113组规范ID和698引用；字段`capacity`是写入span，SCN/ELF含原NUL，SCR不含引号；`max_encoded_bytes`统一不含终止符。核心清单重建后必须完全相同，删掉一处引用也会拒绝修改。脚本/SCN/ELF的引用数组是静态闭包，不意味着所有计算型引用已证实。

`localization-catalogue` v1索引引用同一目录下的JSON文件。源ID、偏移、容量、控制符和上下文不可变；仅`draft`/`reviewed`进入构建。`partial`允许显式未译项，`full-text`要求全部非空字段有译文。文档逻辑页携带强制镜像声明，同一target生成两份资源；原版92页与英文107页不按偏移混配。

## 辅助文本 — Verified

NETGUICD.ELF有270个UTF-8 NUL韩文槽，另有多语言段，配套NETGUI/KOREAN.PF。DATA/AGREE.TXT为8180字节CP949纯文本，行尾是CR CR LF，`<END>`终止读取。辅助目录的`source_bytes`/`source_sha256`不含NUL，主ELF构建行的`capacity`/`source_sha256`包含完整写入span。

`assets/auxiliary-text-sources.json`锁定主ELF38个补充槽：通关/商标两个漏项，以及渲染调用链核实的36个原始英文界面/角色名。默认只用原字符串+NUL；6个角色名配方显式增加最小`padding_bytes`，表示原终止符后已核对为零的对齐字节（1或2）。提取/构建验证原文、全部NUL、原盘hash；未声明padding时仍按原长度拒绝溢出。每项静态引用扫描证据记录在该配方中，不代表可任意借用其他对齐空间。

## NETGUI PF — Verified 只读结构与等长字形覆盖

PF不是TTF。KOREAN.PF为4,251,264字节，47个子字体；韩文部分为26×26、4bpp、352字节字形步长，低半字节先出，原16色调色板不变。中文用显式Unicode别名映射到未被已调查原文使用的韩文字形槽，再按该映射编码为UTF-8。ASCII、原生符号、范围表、索引、metrics和对齐填充保持。完整偏移表、源hash和8组读取器锚点见[网络字体格式](NETWORK_FONT.md)。

## PS2 icon.sys — Verified 网络配置元数据

`CNF/ICON_EN.SYS`为964字节、`PS2D`标识。`u16LE@0x06`是标题内的换行**字节偏移**；CP932标题在`0xC0`，容量68字节含NUL填充，后继三个图标文件名在`0x104/0x144/0x184`。网络标题译为“通信配置”，换行偏移24→8，其他字节保持。`SYS_NET.ICO`、网络配置目录和协议键不变。

主游戏存档标题`Mystic Nights`走`CopyIconFile`→`AsciiString2Sjis`，保留该ASCII品牌字符串。它是固件字体路径，不使用游戏中文图集；直接写入游戏别名字码会被错误再次转换。源锚点与配方见`assets/save-metadata-slots.json`。

## 图像文字 — Verified 配方限定

游戏贴图由三种已观察到的单图、线性TIM2配置组成：RGBA32，以及8bit索引配16bit/32bit CLUT。`graphics.py`只对配方明确支持的配置回填；每张原纹理和每个编辑矩形均绑定hash。清单保存所有物理副本，等长重建保留原尺寸、头部、调色板及矩形外像素。完整图像覆盖与背景处理方式见[图像文字](GRAPHICS_TEXT.md)。

## NETGUI 原始背景与 RGB24 图像差分 — Verified / 本项目定义

`NETGUI/BG.RGB` 为 640×448、逐行 RGB24，无文件头，860160 字节；原 SHA-256 为 `b23b8757334972d171fac4bc49d0550003150dca177322d8400007a754536eb8`。像素 `(x,y)` 的 RGB 位于 `(y*640+x)*3`。离线按该布局解码得到完整联网背景；标题位置 `[7,195,225,29]`，不是 TIM2，也不经过 CLUT。

`assets/raw-image-slots.json` 保存来源、尺寸、文字 ID 与允许矩形；`locales/<locale>/raw-images.json` 保存目标文字和差分文件。`rgb24-artwork-delta` v1 保存完整源/新 SHA、长度、`profile=[width,height,3]`、译文绑定和升序不重叠的 `byte_offset/before/after` 数组。工具拒绝改写矩形外字节、未知来源、越界/重叠、译文漂移、空差分和错误输出哈希。反向交换 before/after 并复验原哈希。

普通构建重放已提交差分，不读取本机创作 PNG；修改版验证从原盘独立重放，并检查所有其他像素、文件长度及 ISO LBA。与 U508 系列图像的亮度/缩放关系仅为近似观察，不作为精确背景重建依据。

## 整盘稀疏补丁 v1 — 本项目定义

ZIP内包含`manifest.json`与各区间before/after内容；不执行或解压其中任何路径。清单记录format/version、原/新全文件size及SHA-256、升序不重叠offset/size、before/after成员名和SHA-256。

应用前检查原盘和所有段，应用后检查新盘全哈希；reverse交换before/after角色。生成ZIP时间戳固定，源码相同输入产生相同补丁。拒绝路径穿越、未知ZIP成员、重复JSON键、重叠和越界。工具：`patch.py`、`tools/apply_patch.py`。
