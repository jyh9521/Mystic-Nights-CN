# NETGUI 网络字体

## 结论与证据等级

**Verified（静态文件、指令与回读）**：网络模块使用独立的 Sony
`libpfont` 位图字体，不是主程序的 `FONT.FNT` / TIM2 字库，也不是
TrueType / OpenType 文件。`NETGUICD.ELF` 的 UTF-8 回调解码 Unicode
码点，再查询 PF 的范围表和字形索引。当前实现无需修改此回调或 PF
结构；中文经显式映射编码到保留的 Hangul 码位，只替换这些码位的像素。

对应实现：

- `src/mysticnights/network_font.py`：严格解析、码位分配、编码/解码、字形生成和回读。
- `tools/inspect_network_font.py`：验证原盘、两个 PF 与八处指令锚点；可生成单独字体副本和实际字形预览。
- `tests/test_network_font.py`：合成 PF、合成 TTF、物理别名保护、完整构建、失败清理等测试，不依赖游戏资产。

本页的 Verified 不代表网络功能、输入法、用户名、存档、换行、纹理缓存或
游戏画面经过实际运行验收。调查没有启动游戏或模拟器。

## 原始资源身份

支持的原盘 SHA-256 为
`4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`，
大小为 `1696530432` 字节。构建入口先验证整盘身份，不接受仅文件名相同的其他版本。

| ISO 路径 | 字节数 | SHA-256 |
|---|---:|---|
| `NETGUI/KOREAN.PF` | 4251264 | `845cf99db8ae8df6b475ad8cc3e7f52cbba2d59a316b9c01d04142001613415a` |
| `NETGUI/EUROPEAN.PF` | 637456 | `d5457e8df9ab75d406eca52c2e07adaad06ecbef4cbc7dc29026296193562bae` |
| `NETGUICD.ELF` | 4080440 | `ca08a4638d883d8f3216a04a3b1fc28ad14c58643671407420de03f5264ea5d1` |
| `NETGUI/JIS2UCS.BIN` | 131072 | `d1c0f65ac91bc52cb58dcba7d5d7b21452301b18106ecb2e10f8c26e88f3bdfb` |
| `NETGUI/UCS2JIS.BIN` | 131072 | `349e34b8841c6429a4c973c43545ac32496a50cf08a5ad5fd03b3cd27c1e11b0` |

两个转换表各含 65536 个小端 u16，ASCII 范围为恒等映射；当前字形覆盖不改这些表。
`NETGUI/BG.RGB` 是背景数据，`EFF.BD` / `EFF.HD` 是音频资源，不将其归为字体。

ELF 文件偏移 `0x3b37a8` 有恰好 16 字节 `PsIIlibpfont1200`，**其后没有 NUL**；
`0x3b37b8` 开始的回调表前三项小端 u32 为 `0x11c7f0`、`0x11c890`、`0x11b690`。
其中 `0x11c7f0` 是已检查的 UTF-8 解码路径，`0x11b690` 是字形绘制入口。
文件偏移 `0x3cd098` 的路径是 `cdrom0:\NETGUI\KOREAN.PF;1`；
调用方还包含 `scePFontAttachData(sw.fd,pfont_data) failed` 字符串。

## PF 外层头

以下整数均为小端；偏移相对整个 PF 文件。解析器只支持两个原文件实际使用的配置，
不声称支持压缩、其他像素深度或所有版本的 Sony PF。

| 偏移 | 类型/长度 | 已确认内容 |
|---|---|---|
| `0x00` | u32 | 0，版本字段 |
| `0x04` | u32 | 0，版本字段 |
| `0x08` | u32 | PF 总字节数，必须与实际长度相等 |
| `0x0c` | u32 | 0 |
| `0x10` | 32 字节 | ASCII 名称，NUL 结束，余下为零 |
| `0x30` | 32 字节 | ASCII 样式名，NUL 结束，余下为零 |
| `0x50` | 4 × s16 | ascent、descent、最大 advance、0 |
| `0x58` | u32 | 子字体数量 |
| `0x5c` | 数量 × u32 | 各子字体相对 PF 起点的偏移 |

子字体偏移表后对齐到 16 字节；该对齐区必须为零。子字体按文件顺序查找，
相同码点以首次命中为准，不能把后来的重复项覆盖前项。

| 文件 | 名称/样式 | 全局 metrics | 子字体 | 物理字形 | 有效码点键 | 后续被遮蔽的键 |
|---|---|---|---:|---:|---:|---:|
| KOREAN | `unknown` / `unknown` | `25,-2,25,0` | 47 | 11965 | 11964 | 1 |
| EUROPEAN | `Adachi font ver0.1` / 空 | `33,-7,30,0` | 4 | 1322 | 1104 | 218 |

KOREAN 的前三子字体分别有 95、63、635 字形，随后 44 块覆盖
U+AC00..U+D7A3 的全部 11172 个 Hangul 音节（43 × 256 + 164）。
所有 KOREAN 单元为 26 × 26。EUROPEAN 首块有 529 个 32 × 40 字形，
其余三块与上述 95/63/635 字形配置对应。

## 子字体头、Unicode 查找与 metrics

每块头长 `0x60` 字节。下表中的数据偏移均**相对该子字体起点**，不是 PF 起点。

| 偏移 | 类型/长度 | 内容 |
|---|---|---|
| `0x00..0x0f` | 4 × u32 | `0,0,子字体总字节数,0` |
| `0x10` | u32 | flags，原盘仅 0 或 8 |
| `0x14` / `0x18` | float32 | 横/纵缩放，均 1.0 |
| `0x1c` / `0x1e` | u16 | 单元宽 / 高 |
| `0x20..0x27` | 4 × s16 | ascent、descent、最大 advance、0 |
| `0x28` / `0x2c` | u32 / u32 | 字形数 / 位图偏移，后者为 `0x60` |
| `0x30` / `0x34` | u32 / u32 | Unicode 范围记录数 / 范围表偏移 |
| `0x38` / `0x3c` | u32 / u32 | u16 映射项数 / 映射表偏移 |
| `0x40` / `0x44` | u32 / u32 | metrics 记录数 / metrics 表偏移 |
| `0x48` / `0x4c` | u32 / u32 | 未解释辅助表数量为 0；偏移与调色板起点相同 |
| `0x50` / `0x54` | u32 / u32 | 调色板项数 16 / 调色板偏移 |
| `0x58` / `0x5c` | u32 / u32 | 均为 0 |

flags 低三位为零时像素深度为 4bpp；bit 3 为 1 时，每个字形有一条 metrics，
为 0 时共享一条 metrics。其他 flags/profile 均被当前解析器拒绝。

范围记录为 16 字节的四个 u32：`first, last, map_base, glyph_base`。
`first..last` 是包含两端的 UCS-2 键范围，各范围升序、不重叠。
索引计算为：

```text
relative = u16_map[map_base + code_unit - first]
relative == 0xffff  → 本子字体缺字，继续查后续子字体
glyph_index = glyph_base + relative
```

范围映射连续占用 u16 表；位图后立即是范围表、映射表，映射表尾补零到
16 字节后是 metrics，最后是 16 项 RGBA 调色板。所有数量、边界、邻接关系、
索引和保留字段均被检查。原盘还有落在 surrogate 范围内的自定义符号键，
解析器保留其原始 UCS-2 键；目标 UTF-8 编码器仍拒绝 surrogate 和非 BMP 字符。

metrics 每条 16 字节，按 8 个 s16 原样保存。已从代码确认 `+0x0c` 是 advance。
Hangul 通常是 `(1,24,-1,26,24,-2,25,0x4001)`，最后一块末字段为 0。
除 advance 外，不给尚未完整解释的字段强行命名；中文覆盖保持整张 metrics 表不变。

## 位图与调色板

每个字形是独立的线性 4bpp 单元，不是 TIM2 图集；每字节先低 nibble、后高 nibble，
对应相邻两个像素。单元长度向上对齐到 16 字节：

- 26 × 26：338 字节像素 + 14 字节对齐区，stride = 352。
- 32 × 40：640 字节像素，stride = 640。

低 nibble 先读可还原原盘 ASCII 和 Hangul 字形；反向 nibble 会产生相邻像素错位。
覆盖只写 338 字节的有效像素，保留 14 字节对齐区。宽高、子字体顺序、映射和查找键均不变。

原盘调色板的 16 项 RGBA 十六进制字节为：

```text
00000000 00000019 00000032 0000004b
00000064 33333332 3333334b 33333364
3333337d 6666664b 66666664 6666667d
99999964 9999997d cccccc7d ffffff7d
```

alpha 使用 PS2 的 0..128 约定；这两文件实际最大值为 125。生成器用原调色板量化
白色笔画与黑色外缘，不新增颜色或改变调色板。Noto 按 23px、4 倍超采样绘制，
保留单元边缘余量，拒绝越界和空白非空格字形。

## ELF 指令锚点

此 ELF 相应文件映射满足 `文件偏移 = VA - 0xff000`。下表是重新检查的原始字节，
不是反编译器输出的猜测。工具在认可解释前检查完整 ELF 哈希及这些字节。

| 名称 / VA | 原始字节 hex | 对应结论 |
|---|---|---|
| AttachData `0x11c3ec` | `0000a28c040040140000bfff0400a28c03004010` | 拒绝 PF `+0/+4` 非零版本字段；函数入口 `0x11c3e8` |
| 子字体 `0x11c438` | `5800828c0800e0032d1000002a10a200fcff401080180500211883005c00628c0800e003` | PF `+0x58` 数量、`+0x5c` 相对偏移表；函数入口 `0x11c430` |
| Unicode 查找 `0x11a4b4` | `0000e48c0800e28c232024013c00038e2110440021180302401002002110430000004394250065102d2000020c00e28cda71040c21884300` | 范围首值/map_base、subfont `+0x3c` u16 索引、FFFF 缺字及 glyph_base；查找函数 `0x11a3f8` |
| metrics 模式 `0x11a534` | `1000028ec21002000100423005004010001911004400028e2110020203000010211043004400028e21100202` | flags bit 3 选择逐字 metrics 或共享记录 |
| 像素深度 `0x11c768` | `1000828c0400032407004230c01002000800e0030a106200` | flags 低三位为 0 对应 4bpp |
| UTF-8 三字节 `0x11c830` | `f000a22c030040100f00a3300700001002000724` | E0..EF 保留低四位，再读取两个续字节；回调入口 `0x11c7f0` |
| UTF-8 续字节 `0x11c85c` | `800008240000c590c000a230f9ff48140100c624801903003f00a230ffffe724f8ffe01425186200` | 检查 80..BF，左移六位并合入低六位 |
| advance `0x11bcd8` | `0c00438406004684002883446029804608004484` | 从 metrics `+0x0c` 读取 s16 并转浮点参与 advance |

REA 已绑定并识别该 MIPS ELF；当时 Windows 原生分析通道未提供可用的 MIPS 反编译。
上述解释来自原字节与标准 MIPS 指令局部核对。通用 MIPS 解码器会误解部分 R5900
专用指令，因此没有把其他未知指令或全函数伪代码当成已验证证据。

## 中文映射、保护与容量

`collect_protected_codepoints` 扫描 NETGUICD 所有 PT_LOAD 段的完整、可打印、
NUL 结束 UTF-8 字符串，得到 **579 个非 ASCII 码点**，其中 257 个 Hangul。
当前 270 条网络源文的 259 个非 ASCII 字符全部在此保护集中。

2026-11-04 的 270 条中文目标需要 **293 个非 ASCII 字符**：

- 9 个原生符号保持原码点和像素：U+201C、U+201D、U+25B3、U+3002、
  U+FF08、U+FF09、U+FF0C、U+FF1A、U+FF1F。
- 284 个缺失字符分配到未保护的 Hangul 码位，并生成 Noto 字形。
- 已存在的目标原生字符也参与物理槽保护；多个码点指向同一字形时，不重复分配，
  也不覆盖受保护码点共享的像素。

主程序和网络模块必须分别使用自己的字码映射。网络目标必须由
`network_font.encode_text(target, mapping)` 编码，验证由对应 `decode_text` 还原。
直接写入原始中文 UTF-8 不会自动访问生成的 Hangul 别名字形。

当前目标的所有非 ASCII 编码均为三个 UTF-8 字节；ASCII 控制符、printf 和换行
保持原字节。最终写入器仍以实际编码结果检查每个源槽的原字节容量，并保留原 NUL；
不借用对齐区，不移动后续数据。码位映射、Noto 哈希、像素尺寸、每个像素变更范围的
before/after 哈希保存在构建 manifest 中。

**未验证边界**：源静态调查没出现的 Hangul 仍可能由用户名、保存的昵称、输入法、
运行时拼接或外部资源产生。此类动态输入可能显示为对应中文别名字形；不能将
“静态未引用”写成“全局空闲”。PF 回读预览使用固定单元网格，不模拟网络 UI 排版或字形缓存。

## 重建与验证

准备仓库要求的 Python/Pillow/fontTools 和哈希锁定的 Noto，见 `BUILDING.md`、
`assets/font-source.json` 与 `tools/fetch_font.py`。以下命令在仓库根目录执行，
不需要旧的研究目录。输出目录必须不存在。

```powershell
python -X utf8 -m unittest discover -s tests -p test_network_font.py -v
python -X utf8 tools/inspect_network_font.py --iso '[full2]미스틱 나이츠(K).iso' --catalogue locales/zh-CN/network.json --output build/network-font-inspection
```

输出包括同长 `MODIFIED_FILE.PF`、`report.json` 和从新 PF 像素解码的
`glyph-preview.png`。只给 `--iso` 和 `--output` 时执行原始资源/指令检查，不生成字体覆盖。
源不匹配、容量不足或预览阶段失败时，新建的临时目录会清理；已有输出拒绝覆盖。

以下可从原盘重新生成局部 PF 差分并验证正反向应用，不保留完整原字体或恢复副本：

```powershell
@'
from pathlib import Path
import sys, tempfile
sys.path.insert(0, "src")
from mysticnights.versions import load_version, verify_original
from mysticnights.patch import build_patch, apply_patch
out = Path("build/network-font-inspection")
image = verify_original(Path("[full2]미스틱 나이츠(K).iso"), load_version(Path("assets/game-version.json")))
raw = image.read("NETGUI/KOREAN.PF")
with tempfile.TemporaryDirectory(prefix=".pf-check-", dir=out) as directory:
    work = Path(directory)
    source, applied, restored = (work / name for name in ("source.pf", "applied.pf", "restored.pf"))
    source.write_bytes(raw)
    build_patch(source, out / "MODIFIED_FILE.PF", out / "DIFF_FILE.zip")
    apply_patch(source, out / "DIFF_FILE.zip", applied)
    assert applied.read_bytes() == (out / "MODIFIED_FILE.PF").read_bytes()
    result = apply_patch(applied, out / "DIFF_FILE.zip", restored, reverse=True)
    assert restored.read_bytes() == raw
    print("PF ROLLBACK PASS", result["sha256"])
'@ | python -X utf8 -
```

局部资源重建仍不等于已经写入网络文本；完整 ISO 必须由 `tools/build_locale.py`
联合安装 PF 和别名编码后的 NETGUICD 字段，再用 `tools/verify_build.py` 回读。
原盘、完整字体、修改 ISO 及生成目录均不提交到仓库。

## 已执行的局部构建与回滚记录

2026-11-04，源目录 `network.json` SHA-256 为
`c347d9b69335e0e0b3bc17a0c682a992ed4ccfee0643c07541cb9ffaf19af2e1`，
Noto SHA-256 为 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`。
这一记录绑定当时目标集，不要求后续译文增加后仍产生同一修改哈希。

- BASELINE：47 子字体、11964 有效键、579 保护码点；源 PF 身份与上表一致。
- MODIFIED：270 字段、293 字符、284 覆盖；大小仍为 4251264；
  SHA-256 `5e2610ab0970b2c8d937d1890f9fc19a078d90cfef54e1f43417f081d647f6f0`。
- 两次独立重建字节一致；原头、索引、范围、metrics、调色板、对齐区及所有非目标像素保持。
- 局部差分为 99773 字节、24 ranges；SHA-256
  `ff12078d3a45bd786f03a3319b267198b61400e124a38f923ae9f1393ef7d896`。
- 正向应用产生与修改 PF 一致的新副本；真实 Git Bash 执行 `ROLLBACK.sh` 成功，
  exit 0，恢复 SHA-256 `845cf99db8ae8df6b475ad8cc3e7f52cbba2d59a316b9c01d04142001613415a`。
  恢复副本与原资源逐字节相同，检查后删除；修改 PF 保持修改状态。
- 20 个无原盘依赖的合成测试通过，包括后期失败清理、原有输出保护、物理共享槽保护和
  合成 TTF 到 PF 的确定性构建。构建记录和预览是离线证据，不是游戏截图。
