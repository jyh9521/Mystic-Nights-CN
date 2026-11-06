# 构建《诡秘之夜》汉化测试版

## 当前运行画面修正

九张截图的取样边界、按钮 UV、同图异名漏译及尚待 GS 转储/字幕听审的边界见 [RUNTIME_IMAGE_FEEDBACK.md](docs/RUNTIME_IMAGE_FEEDBACK.md)。当前为 195 张 TIM2／365 成员／512 实装图字字段，HD 图字 15 张及主字库 8 页；下方 e97f 的 191／359／505／11 为历史数字。高清 ASCII 与字形留白取样修正见 [HD_FONT_SAMPLING.md](docs/HD_FONT_SAMPLING.md)。

即时演算字幕仅通过显式 `--subtitle-catalog` 启用；普通构建不启用当前未听审机器稿。完整接口、拒绝草稿、独立验证/回滚与听审网页重建见 [CUTSCENE_SUBTITLES.md](docs/CUTSCENE_SUBTITLES.md)、[CUTSCENE_AUDIO.md](docs/CUTSCENE_AUDIO.md)。

## 输入和环境

韩版 PS2 SCKA-20055，原盘 1,696,530,432 字节，SHA-256：
`4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`。
完整版本配方见 `assets/game-version.json`；未知版本拒绝写入。

Python 3.11+；依赖锁定在 `requirements.txt`。字体为按 revision、URL 和 SHA-256 锁定的 Noto Sans CJK SC Regular，不使用未记录的系统字体。正文构建不依赖上游英文资源。

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/fetch_font.py
$env:PYTHONPATH = 'src'
python -X utf8 -m unittest discover -s tests
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/validate_translations.py --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/build_locale.py --iso "[full2]미스틱 나이츠(K).iso" --locale zh-CN --output build/full-text
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json
python -X utf8 tools/verify_artwork_states.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --catalogue locales/zh-CN/graphics.json
python -X utf8 tools/verify_runtime_patches.py --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json
```

输出目录必须尚不存在。构建在新的同级事务目录中完成后才发布，不覆盖已有镜像。构建和修改版验证均支持 `--font` 指定同哈希字体；未指定时使用 `build/fonts/` 的锁定字体。

最新8张完整重绘见 `docs/IMAGE_FEEDBACK_E97F.md`；前次29项见 `docs/IMAGE_FEEDBACK_17E7.md`，28项见 `docs/IMAGE_FEEDBACK_E004.md`、91项见 `docs/IMAGE_FEEDBACK_C7.md`。本地左右图筛查网页与意见 JSON/CSV 回传见 `docs/IMAGE_REVIEW.md`。网页由 `tools/build_image_review.py` 从最终 ISO 重建，输出完整图片不提交 Git。

## 当前配置和输出

`full-text` 要求全部非空正文有译文：2176 条逻辑正文（含 142 个场景房间显示名）、2 条原始空白；文档镜像展开后 2268 槽，加 38 个补充 ELF 槽，共 2306。113 个道具名称的 698 处静态引用原子回填。270 条网络设置、完整服务协议和网络记忆卡标题同步构建。

主字库 1433 字形；保留文本保护 379 码位，从 2065 个候选分配。主字形采用 4 倍栅格、正面积 BOX 缩小与覆盖阈值，原 metrics、CLUT 和 ASCII 不变。PF 是独立字体域。此静态保护不证明所有动态输入均已验收。

图像采用与原文字节绑定的已重绘像素差分。原盘1140张唯一TIM2、2634个物理成员均有审查分类；505个可翻译文字项写入191张贴图、359个物理成员，另按意见恢复2张原图，保留2个D.I.A标识及模糊微字。`assets/graphics-source-review.json`的全盘闭包防止再次遗漏同名、调色及`_C`变体。NETGUI/BG.RGB的1个标题使用独立RGB24差分。旧方块覆盖方案不参与构建。`--release`仍关闭，完整流程和游戏内美术由玩家验收后再发布。

正文还构建源绑定的中文禁行首标点 lookahead；144 字节原指令块与 46 字节只读表均有精确锚点。只读表在一条已译 C 字符串的首个 NUL 之后，不扩展 ELF，不改变可见文本。修改版验证独立回放指令、所有实际字码、原生字体像素与全盘图片闭包。

| 文件 | 内容 |
|---|---|
| `Mystic-Nights-zh-CN-full-text.iso` | 独立测试镜像，保留原盘长度和全部文件 LBA |
| `DIFF_FILE.mnp.zip` | 可逆稀疏补丁，不是 xdelta 格式 |
| `manifest.json` | 源/新哈希、字段、字体、名称闭包和图片像素差分 |
| `font-preview.png` | 主字库实际 TIM2 回读预览 |
| `network-font-preview.png` | PF 实际字形回读预览 |
| `ROLLBACK.sh` | Git Bash 反向应用入口 |
| `runtime/original/` | 按本盘原 ELF CRC 生成的可选补丁及金手指 |
| `runtime/localized/` | 按本次中文 ELF CRC 生成的可选补丁及金手指 |

宽屏与三项金手指不烘焙进 ISO，也不自动安装。补丁、金手指各为独立 PNACH 文件，金手指有三个独立开关；使用见 [RUNTIME_PATCHES.md](docs/RUNTIME_PATCHES.md)。普通构建不需要图像生成服务、OpenCV 或本机创作中间文件；原风格成稿以可逆像素差分重放。

需要实际安装时，显式使用 `tools/install_runtime_patches.py --package build/full-text/runtime --data-dir 用户目录 --receipt 新记录目录`。安装器读取现有 `inis/PCSX2.ini` 的 Folders/Patches、Folders/Cheats，不假定程序目录就是用户目录。它不启动模拟器；可选创建本游戏 CRC 专属 INI，拒绝覆盖不同的既有游戏设置，并保存原 PNACH 的逐字节备份和可验证撤销记录。

手工验收不由工具执行。`pcsx2/`、BIOS、配置、记忆卡和存档均不属于构建或清理对象。

## 差分和回滚

所有输出参数必须指向新文件：

```powershell
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/full-text/DIFF_FILE.mnp.zip --output build/full-verification/applied.iso
```

```bash
build/full-text/ROLLBACK.sh build/full-verification/applied.iso build/full-verification/restored.iso
```

Windows PowerShell 如将 `bash` 解析为系统WSL入口，请显式使用实际Git Bash程序，不改全局PATH：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' build/full-text/ROLLBACK.sh build/full-verification/applied.iso build/full-verification/restored.iso
```

反向工具验证全文件哈希、各段原/新字节和最终恢复哈希。恢复输出与原盘逐字节一致，原测试镜像保持修改状态。也可用 `tools/apply_patch.py --reverse` 显式指定补丁。存档不随镜像回滚。

## 可重放调查

```powershell
python -X utf8 tools/prepare_translation.py --iso "原版.iso" --output build/text-template
python -X utf8 tools/extract_auxiliary_text.py --iso "原版.iso" --output build/auxiliary
python -X utf8 tools/inspect_name_links.py --iso "原版.iso" --output build/name-links
python -X utf8 tools/inspect_graphics_text.py --iso "原版.iso" --output build/image-inventory
python -X utf8 tools/inspect_graphics_text.py --iso "原版.iso" --preview-only --manifest assets/graphics-text-slots.json --locale locales/zh-CN/graphics.json --font build/fonts/NotoSansCJKsc-Regular.otf --output build/art-review
```

字体和格式细节见 `TECHNICAL.md`、`docs/FILE_FORMATS.md`、`docs/NETWORK_FONT.md`。图片重绘不在普通构建时重新调用生成模型：已审核的逐像素差分在 `locales/zh-CN/artwork/`，相同源码和原盘会生成相同文件。

已完成原分辨率排版和美术复核的 RGBA PNG 可用 `tools/import_artwork.py` 转为差分；该工具不生成或排版文字。`--source` 为原 TIM2，`--source-sha256` 为配方中的原哈希，`--recipe` 提供 `allowed_rectangles` 和 `targets`，`--output` 必须是新 JSON 路径。导入只量化到原 CLUT，并立即正反向验证；没有修改的像素保留原索引。示例见 `docs/ARTWORK_REVIEW.md`。

已声明 `state_checks` 的像素差分在正向重放时额外检查成对状态的笔画核心尺寸及不应出现的连续横线；参数属于 locale 美术数据，不硬编码中文字体。上述独立回读命令核对实装哈希后执行同一规则。规则只覆盖明确声明的错误类型，不替代实际美术审校。

透明精灵还可声明 `clear_regions`（id、rect、max_alpha），在导入、普通构建和实际 ISO 回读时检查完整字区外缘。START 提示四个透明槽边要求 alpha 全为 0；不是只检查亮色文字尺寸，也不复用原英文的阴影/光晕。`ROLLBACK.sh` 输出在构建时设为可执行。

无头 RGB24 图像使用 `tools/import_raw_artwork.py`，参数同上，recipe 另外声明 `profile=[width,height,3]`，PNG 必须为原尺寸 RGB。原图格式清单位于 `assets/raw-image-slots.json`；目标文字与像素差分放在 `locales/<locale>/raw-images.json` 和 `artwork/`。该路径不经过 TIM2 或字体渲染器，源 hash、允许区域、译文绑定和反向恢复均独立验证。

## 验证记录与清理

本地交付另附`VERIFICATION.txt`，保存原样命令、输入、stdout/stderr、退出码和回滚结果。按2026-11-06当前定稿重建后，仅保留原盘和最新测试ISO两份镜像；旧PoC/合成夹具/回滚镜像及重复提取、预览输出清理。当前画稿、依赖、真实安装撤销收据保留，旧技术记录与可逆差分压缩归档，详见[BUILD_STORAGE.md](docs/BUILD_STORAGE.md)。不向Git提交完整游戏文件或原始贴图。

## 可选高清显示

原生 ISO 与可选 PCSX2 高清包分开。主字库从锁定轮廓重新栅格 4×；当前11张图字配方中，8张意见涉及的菜单/门板采用新完整构图，不复用被否定的字稿。两种包的源绑定重建、真实 Textures 目录安装、独立回滚及运行时边界见 [HD_TEXTURES.md](docs/HD_TEXTURES.md)。

`install_runtime_patches.py --settings-from` 可显式把同一 profile、同一 serial 的旧 CRC 游戏 INI 原字节迁移到尚无不同设置的新 CRC。该选项与新建偏好标志互斥，不静默覆盖玩家选择。当前交付 CRC 与前版恰巧相同，不需要迁移；实际安装只更新两份 PNACH，已有三项勾选保持。
