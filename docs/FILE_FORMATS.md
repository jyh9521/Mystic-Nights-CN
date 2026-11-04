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

`localization-catalogue` v1索引引用同一目录下的JSON文件。源ID、偏移、容量、控制符和上下文不可变；仅`draft`/`reviewed`进入partial构建。文档逻辑页携带强制镜像声明，同一target生成两份资源；原版92页与英文107页不按偏移混配。

## 辅助文本 — Verified编码，编辑路径未接入

NETGUICD.ELF现有270个UTF-8 NUL韩文候选，另有多语言段，配套NETGUI/KOREAN.PF。DATA/AGREE.TXT为8180字节CP949纯文本。`assets/auxiliary-text-sources.json`另锁定主ELF通关/商标文字两个NUL槽，提取时核对完整原字节；不把候选长度直接当已验证可扩展容量。

## 稀疏补丁 v1 — 本项目定义

ZIP内包含`manifest.json`与各区间before/after内容；不执行或解压其中任何路径。清单记录format/version、原/新全文件size及SHA-256、升序不重叠offset/size、before/after成员名和SHA-256。

应用前检查原盘和所有段，应用后检查新盘全哈希；reverse交换before/after角色。生成ZIP时间戳固定，源码相同输入产生相同补丁。拒绝路径穿越、未知ZIP成员、重复JSON键、重叠和越界。工具：`patch.py`、`tools/apply_patch.py`。
