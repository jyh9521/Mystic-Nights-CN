# 图像文字与纹理调查

## 当前美术决定

- 所有有可靠原文依据的可见图字均纳入译文和定位清单。
- 用户明确要求：**很模糊的文字保持原状，不猜字。** 模糊手稿及装饰性微字的保留区与可读标签分别记录。
- 用户已否定黑／红底矩形遮盖、平面字体直接替代原字的做法。当前 `reviewed-solid-panel` 预览仅保留为已否定方案的研究证据，**不是待发布美术成品**。
- 后续重绘应恢复原字后的背景，匹配原图描边、发光、阴影、材质、颜色和字重。字区外的图像、图标、按钮边框、连线和各状态对应关系须保留。
- 原盘、游戏和模拟器均未由图像调查步骤启动或修改。离线预览不是游戏内验收。

## 已验证的资源范围

支持原盘 SHA-256：

```text
4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b
```

原盘 209 个 RES 中共有 2,634 个 TM2 物理引用、1,140 个唯一 SHA-256 纹理；其中 UI 范围为 230 个唯一纹理。全部纹理均完成解码，生成 4 张 UI 联系表、15 张场景联系表及原分辨率 PNG。联系表检查与逐字转录是不同阶段，解码成功不代表微小字迹已被识读。

已观察到的唯一纹理 profile：

| 图像类型 | CLUT 类型 | 唯一纹理数 | 解码 |
|---|---:|---:|---|
| 8-bit indexed（5） | RGB5A1（1） | 631 | 已验证 |
| 8-bit indexed（5） | RGBA32（3） | 494 | 已验证 |
| RGBA32（3） | 无（0） | 15 | 已验证；当前文字回填器仅写 indexed |

TIM2 文件头为 16 字节，单图片头为 48 字节；本盘使用 TIM2 v4、1 张图片、`picture_format=0`、`mipmaps=1`。像素索引为线性排列，256 色 CLUT 的逻辑索引需交换 bit 3 与 bit 4。32 位调色板和直接色图片的 alpha 按 PS2 0..128 转为预览 0..255；RGB5A1 的最高位为 alpha。文件总长、像素长、CLUT 长与尺寸均由解码器一致性检查。

### 上游对比

上游：`jeremydecola/Mystic-Nights-Translation`，提交 `d58734cccf29b702330d131ea981de45512d3b76`。

逐 RES / TM2 字节比较只发现 6 个修改的纹理 payload：

- `RES/UI/COMPANY.RES:WARNING.TM2` ↔ `GRAPHICS/COMPANY/0003.tm2`。
- `RES/UI/ITEM.RES:U335.TM2`～`U339.TM2` ↔ `GRAPHICS/ITEM/0011.tm2`～`0015.tm2`。

上游 GRAPHICS 中的截图、封面图与资源 payload 分开统计。六图修改量不构成标题、联机菜单、职员表、场景标牌及画廊文字的完整覆盖。

## 译文与定位数据

- `assets/graphics-text-slots.json`：原纹理 / 原 RES hash、成员偏移和长度、原像素矩形 hash、profile、文字区及保护区。
- `locales/zh-CN/graphics.json`：独立译文、状态、锁定字体 hash。
- `build/full-translation/graphics-text-inventory.json`：本机完整调查索引、转录、保留区、载体检查和交接状态。
- `tools/inspect_graphics_text.py`：原盘版本校验、全部 TM2 解码、上游比较、可重放前后对照和结构验证。

当前数据为 136 个纹理记录、404 项文字记录。402 项以原风格像素差分安装到全部 136 张纹理、246 个物理成员；待重绘 0 项，2 个 D.I.A 技术标识保留。旧自动矩形覆盖从构建中撤下。G334 微小标语的推断已移除，只回填可辨识公司名，微字原图不改。99 张场景／物品／画廊图的 213 项文字与前 37 张界面图分别记录；修正过程与提示词见 [ARTWORK_REVIEW.md](ARTWORK_REVIEW.md)。

术语与保留原则：

- `MYSTIC NIGHTS` → **诡秘之夜**；`GALLERY` → **画廊**；`매크로` → **快捷语**。
- `VITAL CREATIONS` → **生命创造**，不与正文其他公司混同。
- 门卡 `CP` / `MEL` 保留原缩写，使用“2层CP通行证”“2层MEL通行证”，不自行推定缩写展开。
- `D.I.A`、未证实展开的技术代码、楼层 / 门号、谜题数字 `46559`、按键图标和 `L1` / `R1` 等按原用途保留。
- MN 图形徽记、DNAS 与系统 / 公司标志、版权信息另作品牌与系统标识处理，不当作漏译自然语言。
- 职员表中的人名汉字为音译草稿，不等同于已证实的本人正式汉字姓名；源韩文逐项保留在定位数据中。

## 七张优先重绘图与拼接关系

完整源路径、hash、每个文字矩形及对应译文见：

```text
build/full-translation/style-redraw-handoff/handoff.json
```

| 成员 | 原尺寸 | CLUT | 原分辨率 PNG 索引 |
|---|---:|---:|---|
| L001_004.TM2 | 512×256 | 32-bit | 0084 |
| L001_006.TM2 | 256×256 | 32-bit | 0085 |
| WARNING.TM2 | 512×512 | 16-bit | 1047 |
| U335.TM2 | 256×256 | 32-bit | 1095 |
| U336.TM2 | 256×256 | 32-bit | 1096 |
| U337.TM2 | 256×256 | 32-bit | 1097 |
| U338.TM2 | 256×256 | 32-bit | 1098 |

四张操作图组成 512×512 整图：

```text
U335 (0,0)     U336 (256,0)
U337 (0,256)   U338 (256,256)
```

原图拼接：`build/full-translation/style-redraw-handoff/controller-original-512.png`。控制器、引导线及“快捷语仅在联机模式中使用”的底部脚注跨分块延续，应整图审校后再精确切成四块。七张源图各有一个物理 TM2 引用。

## 模糊字迹：明确保持原图

独立原像素复核记录：`build/research/gallery-handwriting/report.json`。原盘解码与审查 PNG 逐像素一致，五张手稿原始尺寸均为 512×512，每张只找到一个相同 hash 的物理引用。

| 画廊成员 | 保留对象 |
|---|---|
| GALLERY_16 | 右上脚部 / 截面草图旁小字 |
| GALLERY_17 | 左下箭头前拉丁式短词、下方头部草图旁小标注 |
| GALLERY_19 | 右上小标注及剪影下方手写行 |
| GALLERY_20 | 左侧两处手写说明及其他未确认短标记 |
| GALLERY_21 | 底部手写说明及未确认短标记 |

报告保存 9 个未转录区域的原坐标和最近邻放大证据；另外 2 处为已识读的 `BACK VIEW` / `FRONT VIEW`，与模糊区域分开处理。可辨认的 FRONT / BACK / REAR / SIDE / TOP VIEW 等标签可局部翻译，不覆盖其他笔迹。

同源高清检索见 `build/full-translation/gallery-source-research/report.json`。已检查上游、作者资料站文件树、公司 Portfolio PDF、2005 官网图像及宣传原画，未找到五张同幅手写草图的更高清版本。相似怪物外观不作为转录依据。

场景纹理中也有原分辨率微字，特别是 G370、G376、G397 和 G206 的非 WEAPONS 变体。缩略图初判已撤回：G370 不保留猜测的“FOOD”转录，G397 不保留猜测的“LOCKED”转录。此类字迹按用户决定保持原像素，而不是填入泛化或猜测文字。

## 非 TM2 载体

### NETGUI/BG.RGB

已验证文件长度 860,160 字节，SHA-256：

```text
b23b8757334972d171fac4bc49d0550003150dca177322d8400007a754536eb8
```

按 640×448 的线性 RGB24 解码得到完整、连贯的网络背景，左侧含 `MYSTIC NIGHTS`。标题 `[7,195,225,29]` 已按原淡黄斜体风格重绘为“诡秘之夜”，仅该区域改变。配方在 `assets/raw-image-slots.json`，译文与差分由 locale 的 `raw-images.json` 绑定；新 SHA-256 为 `af7469b9f697ad2728ba7669a1e43d146115d403e4bb29ff638b860088fc1aec`。已实现独立 RGB24 导入、构建、回读与反向恢复；不混入 TIM2 数量。运行时读取路径尚未做反汇编绑定，图像解释／文件写入与调用链证据分别表述。

### PS2 存档图标

`CNF/SYS_NET.ICO`（33,688 字节）及 `DATA/LIST.ICO`（73,072 字节）的末 32,768 字节按 128×128 RGB5A1 解码，分别得到 PS2 / 网络标志和怪物眼睛贴图。该纹理解释为高置信度推导；完整 ICO 几何 / 动画格式尚未实现。解码区未发现新增自然语言，系统标志保持原样。

## 可重放调查与验证

```powershell
python tools/inspect_graphics_text.py --iso '[full2]미스틱 나이츠(K).iso' --upstream build/research/upstream --output build/graphics-census
python tools/inspect_graphics_text.py --iso '[full2]미스틱 나이츠(K).iso' --preview-only --manifest assets/graphics-text-slots.json --locale locales/zh-CN/graphics.json --font build/fonts/NotoSansCJKsc-Regular.otf --output build/graphics-preview
python -m unittest discover -s tests -p test_graphics.py -v
```

输出目录必须是新目录。PNG、原始纹理和完整游戏资源只放在忽略的 build 目录。

防御检查包含：源文件 / 源像素 hash、尺寸、成员位置、矩形边界和重叠、调色板与头部不变、缺字、空译文、NUL、文本放不下、保护区覆盖、已有资源补丁冲突。字体只读取和校验一次，TTFont 与 Pillow 均从同一份已校验 bytes 构建，避免路径二次读取产生 TOCTOU。

透明颜色的量化按预乘 alpha 比较；直接按 straight-alpha RGB 距离会把很低覆盖率的边缘错选成高亮不透明色，形成发亮毛边。该失败路径已通过原图前后预览定位并修正。

交接时 12 个纯合成测试通过；最后一个成功的阶段性预览为 334 槽、179 个物理 TM2 成员，但其矩形底板美术已被否定。后续重绘须重新验证源绑定、像素变化范围和实际美术效果。跨纹理记录重复同一 `(resource, member)` 的全局冲突检查另由集成审查提出，真实交接配方未发现该重复，框架仍应显式拒绝。
