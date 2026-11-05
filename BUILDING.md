# 构建《诡秘之夜》汉化测试版

## 输入和环境

韩版 PS2 SCKA-20055，原盘 1,696,530,432 字节，SHA-256：
`4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`。
完整版本配方见 `assets/game-version.json`；未知版本拒绝写入。

Python 3.11+；依赖锁定在 `requirements.txt`。字体为按 revision、URL 和 SHA-256 锁定的 Noto Sans CJK SC Regular，不使用未记录的系统字体。正文构建不依赖上游英文资源。

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/fetch_font.py
python -X utf8 -m unittest discover -s tests
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/validate_translations.py --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/build_locale.py --iso "[full2]미스틱 나이츠(K).iso" --locale zh-CN --output build/full-text
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json
python -X utf8 tools/verify_artwork_states.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --catalogue locales/zh-CN/graphics.json
python -X utf8 tools/verify_runtime_patches.py --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json
```

输出目录必须尚不存在。构建在新的同级事务目录中完成后才发布，不覆盖已有镜像。构建和修改版验证均支持 `--font` 指定同哈希字体；未指定时使用 `build/fonts/` 的锁定字体。

## 当前配置和输出

`full-text` 要求全部非空正文有译文：2176 条逻辑正文（含 142 个场景房间显示名）、2 条原始空白；文档镜像展开后 2268 槽，加 38 个补充 ELF 槽，共 2306。113 个道具名称的 698 处静态引用原子回填。270 条网络设置、完整服务协议和网络记忆卡标题同步构建。

主字库 1433 字形；保留文本保护 379 码位，从 2065 个候选分配。主字形采用 4 倍栅格、正面积 BOX 缩小与覆盖阈值，原 metrics、CLUT 和 ASCII 不变。PF 是独立字体域。此静态保护不证明所有动态输入均已验收。

图像采用与原文字节绑定的已重绘像素差分。原盘 1140 张唯一 TIM2、2634 个物理成员均有审查分类；492 个可翻译文字项写入 187 张贴图、343 个物理成员，另保留 2 个 D.I.A 标识及模糊微字。`assets/graphics-source-review.json` 的全盘闭包防止再次遗漏同名、调色及 `_C` 变体。NETGUI/BG.RGB 的 1 个标题使用独立 RGB24 差分。旧方块覆盖方案不参与构建。`--release` 仍关闭，完整流程和游戏内美术由玩家验收后再发布。

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

手工验收不由工具执行。`pcsx2/`、BIOS、配置、记忆卡和存档均不属于构建或清理对象。

## 差分和回滚

所有输出参数必须指向新文件：

```powershell
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/full-text/DIFF_FILE.mnp.zip --output build/full-verification/applied.iso
```

```bash
build/full-text/ROLLBACK.sh build/full-verification/applied.iso build/full-verification/restored.iso
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

无头 RGB24 图像使用 `tools/import_raw_artwork.py`，参数同上，recipe 另外声明 `profile=[width,height,3]`，PNG 必须为原尺寸 RGB。原图格式清单位于 `assets/raw-image-slots.json`；目标文字与像素差分放在 `locales/<locale>/raw-images.json` 和 `artwork/`。该路径不经过 TIM2 或字体渲染器，源 hash、允许区域、译文绑定和反向恢复均独立验证。

## 验证记录与清理

本地交付另附 `VERIFICATION.txt`，保存原样命令、输入、stdout/stderr、退出码和回滚结果。保留当前测试镜像、原盘、已收到反馈的 PoC、可重建依赖和必要研究证据；删除本轮重复验证镜像和已否定版本的输出。不向 Git 提交完整游戏文件或原始贴图。
