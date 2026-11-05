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

以下是实际使用的可复用提示词；每张输入须使用原盘导出的原图，而不是以失败预览作为美术基准。

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

`recipe.json` 结构：`{"allowed_rectangles":[[x,y,width,height]],"targets":{"slot-id":"localized text"}}`；可选 `state_checks` 按 FILE_FORMATS 中的规则声明成对状态回归检查，导入器在写文件前执行并保存到差分。导入前 PNG 必须已经完成原生尺寸、字形、背景和文字区域审校。

```powershell
python -X utf8 tools/import_artwork.py --source original.TM2 --source-sha256 SOURCE_SHA256 --png reviewed-native.png --recipe recipe.json --output new-artwork-delta.json
```

导入器不排字、不新建调色板；逐像素预乘 alpha 距离量化，保留未变像素的原索引和等效透明 RGB，拒绝越区变化及错误尺寸／来源。读回差分并正反向验证。普通构建始终走固定差分，不重新量化高分辨率生成稿。

## 场景、物品与画廊：99 张 / 213 项

2026-11-05，剩余 99 张唯一 TIM2 的 213 项可读文字按原图逐张重绘，覆盖 169 个物理成员。每个光照／颜色变体独立绑定源 hash 和 CLUT，不拿同名另一版本直接覆盖。已有 37 张界面差分逐一同哈希保留。

- 场景标牌保留金属锈斑、薄字／模板字、暗刻字和终端扫描线；大面积无字材质及模糊微字仍用原像素。
- 两种 G362 的倒置“注意 / 请勿靠近 / 设备正在运行”及侧边旋转标牌按原 UV 方向写回；按用户反馈去掉逗号，不以新底板遮盖。
- G341 的 alpha 本身携带旧字，恢复新笔画须按原 CLUT 的黑底可见颜色反求索引，不能把旧字 alpha 套在新字上。两种变体分别处理，D.I.A、GID 和不可读微字保持。
- G293 移除生成稿上额外的青色底条，字直接落在原深色材质上；G397 仅回填明确读出的主标签，不猜测小标语。
- 卡片的姓名、等级及安保／研究职务按原衬线、印刷磨损与不同底材回填；CP/MEL 等代码保留。
- 画廊标题、正／后／侧／顶视图及已确认注释局部重绘。GALLERY_03 的斜排副标题使用逐行窄带掩码，清除原拉丁笔画两端并保留 MN 主徽记；不使用包含主图的大矩形覆盖。
- 5 张模糊手稿与其他不可读微字不猜补。缩窄可读字区时同时保留邻近微字；原生回读逐图复查，而不是将生成稿直接视作结果。

NETGUI/BG.RGB 另有 1 个淡黄斜体标题，以 640×448 RGB24 原格式写回。`raw_images.py` 和 `import_raw_artwork.py` 为 locale-neutral 工具，使用来源、尺寸、允许矩形和译文绑定，不复用 TIM2 的 CLUT 假设。

```powershell
python -X utf8 tools/import_raw_artwork.py --source original.rgb --source-sha256 SOURCE_SHA256 --png reviewed-native.png --recipe raw-recipe.json --output new-raw-delta.json
```

`raw-recipe.json` 示例：`{"profile":[640,448,3],"allowed_rectangles":[[7,195,225,29]],"targets":{"NETGUI/BG.RGB/title":"诡秘之夜"}}`。

本机创作提示词、选择记录、注册坐标与哈希保存在 `build/artwork-completion/provenance.json`；最终原尺寸对照在其 `native/`。这些完整图片不提交；已提交差分足以从原盘重建，不依赖创作缓存。

## 当前范围

### 主菜单选中态反馈修订

2026-11-05，用户游戏截图揭示选中态字形过小及白色下划线。旧 ISO 的 L001_004 SHA 为 `8e956ca33df0b3ae3473390c3adb12f9b8f8ec25d1a2f4c02f8f51a1ba178f5e`，与当时已提交差分一致：属于实装素材问题。原版稳态缩放对照见 TECHNICAL。

保留既有字体风格，从原生成稿重新界定四个字形范围，排除胶囊框线。另试的透明字稿浮雕过重，未安装。清理完整旧字床后按四个未选中标签的宽高对齐；字形注册尺寸为 53×16、63×16、63×16、39×16，仍使用原调色板。四个选中矩形内更改 3119 个索引，普通态、标题、START、MN、版权、框外图案和其他 135 张重绘纹理不变。

修正后 L001_004 SHA 为 `46209d66a054791c2dda965c8e5846118a0cb146127134bc024d55ed34e889c6`。原生回读检查的亮色字高为普通态 14/12/13/13、选中态 14/13/13/13（像素阈值下的笔画核心，不是排版字号），四条 59 像素白线均为 0。机器检查和视觉复查均从 TIM2/ISO 解码，不拿生成稿作为已安装证据。局部底纹是美术修复，不声称找回了不可见的原文字下方精确像素。

复用提示词补充：`Isolate ONLY the lettering. Exclude capsule frames, highlights, underline-like bars and background from glyph bounds. Match paired state dimensions after native CLUT quantization, not merely high-resolution crop dimensions.`

累计 402 项可翻译 TIM2 文字全部安装，136 张唯一纹理、246 个物理成员；待重绘 0 项，2 项 D.I.A 标识保留。联网背景标题另计 1 项。模糊字迹保持原图；实际游戏混色与玩家美术验收仍单独记录。版本、哈希、实测命令与回滚结果见 VERIFICATION。

## 反馈修正：保留已采用字稿，不另换风格

玩家否定了中途的独立粗体与二值化轮廓候选，均未写入 ISO。最终主菜单沿用原生成稿 SHA `5722e3435eb105fcf4b05b69a0b15b1d48b39b4ac8dcaeee684503f72aadf826` 的字形、配色方向、浮雕和抗锯齿；同一个游/戏用于所有菜单词。每字统一16px格，量化后核心对齐按钮中心，原生坐标误差不超过0.5px。标题只取四个独立原字形，整个旧标题和普通态字床清空 alpha，不带邻字碎片或旧字光晕。

选中态仅用原拉丁字笔画/阴影掩码修复自己的原材质，不把整张生成稿或不透明矩形粘到按钮上。原材质的钢边/火光不计入字形测量。正常构建只重放已提交差分；可选高清菜单由同风格自创字形 RLE 加本地源材质重建，见 `locales/zh-CN/hd-artwork.json`。

其余反馈补充：8 张确定/返回图覆盖27引用；两个 NoSignal 和一个 G329 按原连续光照修复；新补6张 EXIT /12字段/18引用。当前总量 193 张唯一 TIM2、361成员、504安装字段及2保留标识。模糊微字不猜译，真实混色仍由玩家验收。
