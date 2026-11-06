# 可选 4× 字库与菜单贴图

## 用途和边界

提高 PCSX2 的内部 3D 分辨率，不会重新生成原本约 13px 的正文字形。这里提供两套独立、可重建的 PNG 替换包：

- `hd-font/`：8 页主字库，1433 个映射字形从锁定的 Noto 轮廓以 48ppem 重新栅格，不是放大旧位图。FNT、字码、字宽、基线和原 UV 不改；未分配像素保留。
- `hd-artwork/`：9 张图字载体，包含主菜单、难度/人物按钮、电源提示、红色注意门、幼虫实验室两种CLUT32照明和摄像机标签。保留主菜单此前采用的字稿、配色、浮雕及12个前景层，新增小字使用完整4×轮廓，不放大原生字面；原材质来自本地 ISO。没有采用后来被否定的扁平粗块字体。编号及CLUT16边界见 [IMAGE_FEEDBACK_17E7.md](IMAGE_FEEDBACK_17E7.md)。

离线已核对 hash 算法、PNG、原生对应与受保护区域。**真实 GS 使用的区域/调色板、替换加载与画面仍由玩家测试**；没有启动模拟器。仅生成受支持CLUT32、full-region、单 mip、精确源 CLUT 的键；CLUT16及其他运行时键需独立核验后另补。包不覆盖 PF 网络字体、其他所有烘焙图字或影片，也不自动合并下载的整套高清材质。

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

### 意见c7的菜单字格与新键

八个词沿用已采用字稿，统一14px原生字格（4×层56px高），普通态恢复原半透明红底；标题仍为原彩色浮雕字稿。主菜单新精确键`169a7046184c6930-28b27f92b46f3d61-00002253.png`已替换旧键，其余8字体页保持。原始PNG的alpha按PS2语义保存，alpha0下隐藏RGB不表示会显示整片红色；检查显示预览时才将alpha归一化并合成底色。完整字节及真实载入须分开验证。
### 意见 e004 的新菜单键

当前主菜单键为 `de1430d7758e480-28b27f92b46f3d61-00002253.png`；上段 c7 键已按原安装收据撤销。源绑定配方保留同一12层前景，仅更新无字玻璃底纹和 native hash。隔离安装按旧→新→旧恢复 PNG 原字节后，才更新真实 Textures 目录；8页主字体、两份 PNACH 和当前 INI 均不变，不启动模拟器。

### 意见17e7的当前包

上段e004键已退休。当前主菜单键为 `411ded3ef93c39c7-28b27f92b46f3d61-00002253.png`；图字包共9张、48个自创前景层，与当前原生ISO绑定。隔离安装已验证旧1张→新9张→旧1张逐字节恢复，再更新真实Textures目录；合计17张PNG（9图字+8字库）。主菜单12层前景、8页字库、两份PNACH和玩家当前INI/勾选保持，不运行模拟器。当前安装收据保存在本地`build/feedback-17e7/installed-menu/`。
