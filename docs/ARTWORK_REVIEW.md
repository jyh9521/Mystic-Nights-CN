# 原风格重绘与背景残影修正

## 首批七图

用户点名的七图：L001_004、L001_006、WARNING、U335、U336、U337、U338。使用内置 image_gen 生成匹配原图的中文字形与清洁底纹；不使用 API/CLI 模型调用。生成整图仅作为字形/局部修复素材，不整张覆盖游戏原图。

- 标题和菜单：暖金/橙色文字、金属明暗及描边，保留原 MN 徽记、激光、版权、胶囊框及高光。
- 难度/人物：蓝色状态银白字、橙色状态金色字；文字背后恢复原样式机械底纹。
- 警告：破损、磨蚀白字，旧文字下的原画纹理局部修复；没有黑底条。
- 操作图：粗白字和原橙色强调，手柄和指示线保持原像素，整体审校后切回 4 个 256×256 块。

首次导入只擦亮色原字，遗漏旧英文黑描边和阴影，用户反馈后已撤回。当前菜单修正完整重建旧文字底纹；普通菜单的旧 alpha 字层和旧字光晕整体移除，不把它们留在新汉字周围。此失败方式同时记录在 PITFALLS。

## 重建和校验

`locales/zh-CN/artwork/*.json` 保存源纹理 SHA、原/新长度、原生 profile、逐像素 before/after 稀疏差分、允许的文字矩形和精确译文绑定。不存完整原游戏图片；普通构建不重新生成图片，像素差分可重复应用和反向恢复。

`artwork.py` 拒绝源hash变化、未知尺寸/CLUT、越区写入、范围重叠、译文改变、空差分及结果hash不符。`graphics.py` 拒绝不同记录重复写同一物理纹理；`source-style-only` 不接受旧自动排字路径。

预览从最终 TIM2 的实际调色板索引解码，不把高分辨率生成稿当作游戏中的最终显示。七图均保持原文件长度、头部、CLUT 和文字区外像素；最终游戏混色仍由玩家验收。

## 可复用重绘提示词

以下是本轮实际约束的可复用提示词；每张输入须使用原盘导出的原图，而不是以失败预览作为美术基准。

```text
Edit the supplied original game texture. Localize ONLY its lettering into the
provided exact Simplified Chinese text. Match the original stroke weight,
condensation, bevel, outline, glow, shadow, material and palette. Remove all old
letter strokes INCLUDING dark outlines and shadows. Reconstruct the complete
old text bed with a seamless continuation of its original textured material.
Never add flat color rectangles, black backing panels, new frames or banners.
Keep the original atlas geometry, frame edges, artwork, lines, endpoints and
transparency. Do not redesign or move the underlying art. Output no comparison.
```

按图附加：

- L001_004：`诡秘之夜 / 新游戏 / 读取游戏 / 联机游戏 / 画廊 / 按START键`。普通态暖橙金，高亮态银白金属，上方 MN 与版权保持。
- L001_006：两列各 8 行，`简单 / 普通 / 困难 / 詹妮弗 / 布鲁斯 / 艾伦 / 亨利 / 弗兰克`，左银白、右暖金。
- WARNING：`警告`；`本游戏含有较强的暴力内容，`；`不适合老年人、体弱者及孕妇。`。磨蚀破损白字，背景透过笔画间隙。
- Controller：按原位置使用 `选择道具 / 重置视角 / 地图 / 菜单 / 选择武器 / 瞄准 / 变身 / 使用道具 / 操作、交谈 / 快捷语 / 取消 / 攻击（瞄准时） / 移动 / 视角`；脚注 `（快捷语仅在联机模式中使用）`，只有“快捷语”为原橙色。蓝色手柄与所有连线不可改动。

## 界面续批：30 张 / 146 项

在首批七图之上增加 30 张界面贴图，实际写入 70 个物理成员。累计 37 张、189 项、77 个成员。正文、名称、PF、主字库和已有七图差分不变。

- L001_007：剩余五名角色的蓝／橙两态，沿用同系列胶囊的机械底纹和银白／金色字形。
- U120、U339、U340：保留眼睛和载入横向模糊、设置滑杆和复选框；文字分别匹配细白、粗白、微小蓝／红字。
- UIGAL、U403：窄粗画廊字形、蓝色金属游戏结束文字与两套选择状态。
- U317 两种、U516 两种、U204、U208、U528、U538：保留各自图案／CLUT、精细衬线字和按键图标；身份卡的格纹与编码保持。
- U548、U549：原图是扁平青色 HUD 字，不采用模型最初生成的立体浮雕／发光版本；每张六行全部按原单元回填。
- U508、U555、U560：淡黄斜体标题、蓝色随机选择和红色破损印章。U555 的四个照片象限取自原 U552/U554/U551/U553，而不是替换成生成模型重画的房间；允许文字区内局部修复，其外原像素保持。
- NLOGSOFT、SCEK、THEEND、U801～U807：原品牌字标不改，译制标语／呈献和结尾；职员表沿用窄粗字、红色职位／白色姓名与原行高。姓名仍是已记录的音译稿，不冒充本人正式汉字。

U317 底部四条灰色文字是独立的暗淡／模糊状态，不是垃圾残留。其 RGB 近似常量而 alpha 携带字形；须在黑底合成后辨认，并保持原状态亮度。U508 仅按亮色擦字会将生成背景的差异留成旧字轮廓，已改为整段清理和边缘衔接。所有这些检查均基于最终原生 TIM2，而非高分辨率生成稿。

本地创作素材、逐图提示词及哈希：`build/artwork-continuation/provenance.json`。原尺寸比较图：`build/artwork-continuation/native/`。这些完整图片不提交 Git；重建只读取已提交像素差分，不依赖素材目录或模型服务。

### 可复用原生导入

`recipe.json` 结构：`{"allowed_rectangles":[[x,y,width,height]],"targets":{"slot-id":"localized text"}}`。导入前 PNG 必须已经完成原生尺寸、字形、背景和文字区域审校。

```powershell
python -X utf8 tools/import_artwork.py --source original.TM2 --source-sha256 SOURCE_SHA256 --png reviewed-native.png --recipe recipe.json --output new-artwork-delta.json
```

导入器不排字、不新建调色板；逐像素预乘 alpha 距离量化，保留未变像素的原索引和等效透明 RGB，拒绝越区变化及错误尺寸／来源。读回差分并正反向验证。普通构建始终走固定差分，不重新量化高分辨率生成稿。

## 当前范围

累计 189 项对应 37 张界面图。其他图片的旧方块覆盖输出全部撤下，213 项场景／画廊稿件及 NETGUI 背景标题等待同标准重绘；不因为文字已翻译就把未完成的图片算作已安装。模糊微字保持原图。版本、哈希、实测命令与回滚结果记录在 VERIFICATION。
