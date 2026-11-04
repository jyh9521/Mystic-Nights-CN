# 构建《诡秘之夜》分批汉化版

## 输入版本

- 平台：PlayStation 2；韩版 SCKA-20055；SYSTEM.CNF 的 VER=1.00、VMODE=NTSC。
- ISO：1,696,530,432 字节。
- SHA-256：`4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`。
- ELF/资源哈希：`assets/game-version.json`；未知版本在写输出前报错。

完整游戏文件由本地提供；英文补丁不是构建依赖。输入 ISO 不会被就地修改。

## 环境与字体

Python 3.11+，依赖固定在 `requirements.txt`。本轮 Windows 验证环境是 Python 3.14.2、Pillow 12.2.0、fontTools 4.63.0。

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/fetch_font.py
```

字体为 Noto Sans CJK SC Regular，来源 revision、下载 URL 和 SHA-256 均在 `assets/font-source.json`。下载后位于 `build/fonts/`；已有文件也重新核对哈希。可用 `--font` 指定相同哈希的文件。系统自带字体不作为隐式依赖。

## 构建与检查

以下命令在仓库根目录执行，ISO 名称可替换为实际路径。

```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 tools/verify_build.py --kind baseline --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/validate_translations.py --iso "[full2]미스틱 나이츠(K).iso"
python -X utf8 tools/build_locale.py --iso "[full2]미스틱 나이츠(K).iso" --locale zh-CN --output build/partial
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/partial/Mystic-Nights-zh-CN-partial.iso --manifest build/partial/manifest.json
```

输出目录必须尚不存在；构建先在独立临时目录完成，成功后再发布目录。重复构建请指定另一个新的 `--output`，不要覆盖仍在验收的镜像。

当前默认配置为`partial`：328条逻辑译文展开为340个物理正文槽，使用646个中文字符/标点。未译条目保留原文；113个已拟定关联译名尚未安装。`--release`仍报错，不把分批版包成完整版。

字体从原有2444个双字节槽中分配：完整SCR（含注释）、纯文本、RES名称及两个ELF加载段的CP949 NUL字符串/后缀候选共保护1356码位，剩余1088候选。646字映射与保护集互斥；ASCII、FNT坐标/指标、调色板均不改。候选只是本次静态文本调查未见使用，不等于所有动态/输入文字路径绝对闲置；见`TECHNICAL.md`。

输出：

| 文件 | 内容 |
|---|---|
| `Mystic-Nights-zh-CN-partial.iso` | 独立测试镜像，不上传完整镜像 |
| `DIFF_FILE.mnp.zip` | 可校验、可逆的稀疏差分；不是 xdelta 格式 |
| `manifest.json` | 原/新哈希、修改成员、译文与字码映射 |
| `font-preview.png` | 从实际生成的 TIM2 字形读取的离线预览 |

全部文件LBA和长度保持原值。当前改动6个ISO文件：主ELF、SYSTEM、SUBSYS、NETSUB、UI/ITEM和UI/DOCUMENT；其他718个文件逐字节不变。字体保护集在修改版验证时从原盘独立重算。此检查不代替开机、显示、存读档或通关测试。

## 差分应用与恢复

所有输出路径必须是新文件：

```powershell
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/partial/DIFF_FILE.mnp.zip --output build/applied.iso
python -X utf8 tools/apply_patch.py --reverse --input build/applied.iso --patch build/partial/DIFF_FILE.mnp.zip --output build/restored.iso
```

Git Bash 同等恢复入口：

```bash
bash tools/rollback.sh build/applied.iso build/partial/DIFF_FILE.mnp.zip build/restored.iso
```

程序校验全文件 SHA-256、每段原字节/新字节、区间边界和恢复后的 SHA-256；失败时删除仅由本次创建的部分输出。原盘仍在时也可直接重新选原盘运行，不涉及模拟器存档回退。

## 提取和调查

```powershell
python -X utf8 tools/extract_strings.py --iso "[full2]미스틱 나이츠(K).iso" --output build/catalogue
python -X utf8 tools/inspect_font.py --iso "[full2]미스틱 나이츠(K).iso" --output build/font-inspection.json
python -X utf8 tools/inspect_links.py --iso "[full2]미스틱 나이츠(K).iso" --output build/links
python -X utf8 tools/prepare_translation.py --iso "[full2]미스틱 나이츠(K).iso" --output build/text-template
python -X utf8 tools/inspect_name_links.py --iso "[full2]미스틱 나이츠(K).iso" --output build/name-links
python -X utf8 tools/inspect_font_usage.py --iso "[full2]미스틱 나이츠(K).iso" --output build/font-usage.json
python -X utf8 tools/extract_auxiliary_text.py --iso "[full2]미스틱 나이츠(K).iso" --output build/auxiliary
```

`inspect_links.py`可额外传`--upstream <上游检出目录>`，比对锁定版本的英文资料；正常构建不依赖它。文档按ITEM块配对，避免英文增页引起的偏移错配。全文待译模板和译文属于结构化源数据；完整商业资源不加入源码树。

## 交付与清理

本轮交付另外记录 `VERIFICATION.txt` 和可执行 `ROLLBACK.sh`；完整命令、输入、输出和退出状态写入验证记录。收尾保留原盘、当前测试镜像、差分、字体依赖和验证报告，清理重复提取、重复镜像和临时对比目录。

`pcsx2/` 属于本地模拟器、BIOS、存档和配置区域，Git 忽略；构建和清理脚本都不操作该目录。游戏仅由玩家手动启动验收。
