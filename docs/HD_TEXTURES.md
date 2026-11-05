# 可选 4× 字库与菜单贴图

## 用途和边界

提高 PCSX2 的内部 3D 分辨率，不会重新生成原本约 13px 的正文字形。这里提供两套独立、可重建的 PNG 替换包：

- `hd-font/`：8 页主字库，1433 个映射字形从锁定的 Noto 轮廓以 48ppem 重新栅格，不是放大旧位图。FNT、字码、字宽、基线和原 UV 不改；未分配像素保留。
- `hd-artwork/`：1 张主菜单。复用此前已采用的字稿、配色与浮雕，保留抗锯齿；原材质来自本地 ISO。没有采用后来被否定的扁平粗块字体。只对已有字形做尺寸与位置注册，不重新设计菜单。

离线已核对 hash 算法、PNG、原生对应与受保护区域。**真实 GS 使用的区域/调色板、替换加载与画面仍由玩家测试**；没有启动模拟器。仅生成 full-region、单 mip、精确源 CLUT 的键；其他运行时键需实际观察后另补。包不覆盖 PF 网络字体、其他所有烘焙图字或影片。

## 重建

先按 BUILDING 完成原生 ISO 构建，然后在独立依赖目录安装可选的锁定依赖；不影响基础构建：

```powershell
python -m pip install --no-deps --target build/hd-deps -r requirements-hd.txt
$env:PYTHONPATH=(Resolve-Path build/hd-deps).Path
python -X utf8 tools/build_hd_font.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf --output build/hd-font
python -X utf8 tools/build_hd_artwork.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --recipe locales/zh-CN/hd-artwork.json --output build/hd-artwork
```

输出目录必须不存在。两个包各自持有一个清单，不能混放两个清单后安装。菜单配方只包含源绑定差分及自创中文字形图层的 RLE，不包含完整原贴图、不依赖本机创作 PNG。

## 安装和撤销

```powershell
python -X utf8 tools/install_texture_pack.py --package build/hd-font --data-dir "PCSX2用户目录" --receipt build/hd-font-install
python -X utf8 tools/install_texture_pack.py --package build/hd-artwork --data-dir "PCSX2用户目录" --receipt build/hd-artwork-install
python -X utf8 tools/install_texture_pack.py --rollback --receipt build/hd-artwork-install
python -X utf8 tools/install_texture_pack.py --rollback --receipt build/hd-font-install
```

安装器只读取现有 `inis/PCSX2.ini` 的 `[Folders] Textures`，支持相对于用户目录的外部目录，拒绝链接/重解析点。目录按 **SERIAL/replacements/**，不是 CRC。只写入清单拥有的文件，并保存逐字节备份与收据。全局 INI、其他游戏、BIOS、记忆卡和存档不改，也不代替玩家启用纹理替换设置。回滚先检查全部目标、备份和完整清单；已被玩家修改的文件不会被强行覆盖。

## Verified：PCSX2 v2.9.155 的兼容事实

- PSMT8 块内排列按 `GSTables.cpp` 的 256 项 `columnTable8` 独立核对；hash 输入是逻辑块行序的 256 字节块，不是 TIM2 的简单线性像素序。
- XXH3-64 使用默认 secret；对原生纹理及逻辑 RGBA CLUT 分别计算。文件名包含精确 CLUT hash；**CLUT-less 可解析不代表加载器支持通配替换**。
- 256×256 字库 packed bits 为 `00002213`，512×256 菜单为 `00002253`。
- PNG 使用原始 PS2 RGBA 语义，不把 alpha 乘二。主字体白色峰值为页1..7的 `(148,148,148,106)` 和页8的 `(170,170,170,110)`。预览合成才采用 PS2 显示 alpha；预览不冒充游戏截图。

依据固定版本的 [替换加载与导出](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/GS/Renderers/HW/GSTextureReplacements.cpp)、[纹理 hash](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/GS/Renderers/HW/GSTextureCache.cpp)、[排列查表](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/GS/GSTables.cpp)。代码独立实现，不复制模拟器源文件。

### 后续完整内床修正

主菜单前景12层保持旧字稿不变，完整119×16内床恢复为无字玻璃。新原生索引产生新的texture hash，因此必须安装新菜单PNG；只替换预览不够。旧菜单PNG由此前安装收据做受保护撤销，再安装新键；8页主字库与其他游戏贴图不动。
