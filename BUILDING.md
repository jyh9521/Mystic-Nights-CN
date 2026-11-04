# 构建《诡秘之夜》汉化验证版

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
python -X utf8 tools/build_locale.py --iso "[full2]미스틱 나이츠(K).iso" --locale zh-CN --output build/poc
python -X utf8 tools/verify_build.py --kind modified --original "[full2]미스틱 나이츠(K).iso" --iso build/poc/Mystic-Nights-zh-CN-poc.iso --manifest build/poc/manifest.json
```

输出目录必须尚不存在；构建先在独立临时目录完成，成功后再发布目录。重复构建请指定另一个新的 `--output`，不要覆盖仍在验收的镜像。

当前只实现 `poc`：13 条可执行文件提示/标签与 1 条剧情对白，47 个中文字符。`--release` 明确报错，避免把验证版误包成完整版。字体先占用原字库中未被已提取原文使用的 Jamo 槽；韩文音节、ASCII 和未分配字形保持不变。不能跳过字体覆盖/字节容量/原文校验强制生成。

输出：

| 文件 | 内容 |
|---|---|
| `Mystic-Nights-zh-CN-poc.iso` | 独立测试镜像，不上传完整镜像 |
| `DIFF_FILE.mnp.zip` | 可校验、可逆的稀疏差分；不是 xdelta 格式 |
| `manifest.json` | 原/新哈希、修改成员、译文与字码映射 |
| `font-preview.png` | 从实际生成的 TIM2 字形读取的离线预览 |

全部文件 LBA 和长度保持原值。只改 `SCKA_200.55`、`RES/SYSTEM.RES`、`RES/SUBSYS.RES`；其余 721 个 ISO 文件逐字节不变。此检查不能代替开机、显示、存读档或通关测试。

## 差分应用与恢复

所有输出路径必须是新文件：

```powershell
python -X utf8 tools/apply_patch.py --input "[full2]미스틱 나이츠(K).iso" --patch build/poc/DIFF_FILE.mnp.zip --output build/applied.iso
python -X utf8 tools/apply_patch.py --reverse --input build/applied.iso --patch build/poc/DIFF_FILE.mnp.zip --output build/restored.iso
```

Git Bash 同等恢复入口：

```bash
bash tools/rollback.sh build/applied.iso build/poc/DIFF_FILE.mnp.zip build/restored.iso
```

程序校验全文件 SHA-256、每段原字节/新字节、区间边界和恢复后的 SHA-256；失败时删除仅由本次创建的部分输出。原盘仍在时也可直接重新选原盘运行，不涉及模拟器存档回退。

## 提取和调查

```powershell
python -X utf8 tools/extract_strings.py --iso "[full2]미스틱 나이츠(K).iso" --output build/catalogue
python -X utf8 tools/inspect_font.py --iso "[full2]미스틱 나이츠(K).iso" --output build/font-inspection.json
python -X utf8 tools/inspect_links.py --iso "[full2]미스틱 나이츠(K).iso" --output build/links
```

`inspect_links.py` 可额外传 `--upstream <上游检出目录>`，比对锁定版本的英文资料；正常构建不依赖它。文档按 ITEM 块配对，避免英文增页引起的偏移错配。提取结果只在本地输出，完整商业资源不加入源码树。

## 交付与清理

本轮交付另外记录 `VERIFICATION.txt` 和可执行 `ROLLBACK.sh`；完整命令、输入、输出和退出状态写入验证记录。收尾保留原盘、当前测试镜像、差分、字体依赖和验证报告，清理重复提取、重复镜像和临时对比目录。

`pcsx2/` 属于本地模拟器、BIOS、存档和配置区域，Git 忽略；构建和清理脚本都不操作该目录。游戏仅由玩家手动启动验收。
