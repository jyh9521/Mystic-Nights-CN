# 高清字库边界残墨与ASCII清晰度

## 2026-11-06玩家截图后的定位

**Verified offline**：旧高清字库只把1433个已分配中文矩形从轮廓重绘。95个ASCII（空格、数字、大小写、标点）仍从原生位图最近邻放大。因此同一句中的`L2`和插槽`1/2`不是同一清晰度路径，之前仅选中文样句的预览没有覆盖这个差异。

**Verified offline**：FNT含2539记录，`LoadFont`对Y加1、高度减1。`RenderString`的`0x1563DC..0x156520`读取运行时X/Y/W/H，起点为`x<<4,y<<4`，终点为`(x+w)<<4,(y+h)<<4`；没有把UV内缩半个原生纹素。该范围在原盘和当前汉化ELF逐字节相同。

旧高清流程把所有未分配像素原样放大，包括**不属于任何实际FNT取样矩形**的间隔残墨。在当前8页包中，这些位置共有133664个非透明高清像素（8354个原生纹素）。例如“记”的左右间隔原alpha为15，“插”的下方间隔原alpha达70；整数UV边界的线性取样有机会读到这些像素。该路径与截图中的小点/竖线吻合，属于高置信根因；工具没有执行真实GS渲染。

## 修复

- 按全部2539个`[x,y+1,w,h-1]`实际取样矩形建立占用图，不仅按本地中文分配表。
- 每页中**不属于任何字形取样矩形**的纹素变为alpha0，覆盖水平间隔、原FNT首行间隔及未引用尾区。没有对中文轮廓做阈值删点，也没有重新画1433个中文字形。
- 1011个未重新绘制的保留字形，其实际UV范围逐像素保持；FNT、字码、字宽、原生TIM2、CLUT和精确替换键均不改变。
- CLI显式开启95个ASCII轮廓。原ASCII有效核心给出字号/基线/位置；同一锁定Noto字体以高分轮廓生成，再正面积BOX适配其原核心，避免`L2`和数字继续最近邻放大。输出抗锯齿不做阈值截断。空格仍为空白。
- 通用函数的`ascii_outlines`是显式布尔选项；关闭时保留ASCII实际UV，供其他使用者兼容旧行为。普通主字库构建工具开启此选项。
- 预览追加实际混合文字字段，如`RES/SUBSYS.RES:EVENT.SCR@000399c5`的“【提示】 再按一次L2键，即可显示持有的其他恢复药。”，不再只展示纯中文。

## 回归与实际包复核

以下命令工作目录均为仓库根目录，不启动游戏或模拟器：

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_hd_font.py
```

首次加入`test_unsampled_padding_cannot_leak_into_bilinear_glyph_boundaries`后，旧代码真实失败：`AssertionError: 128 != 0`；修复后12项通过。合成夹具故意在未引用间隔保留原色，检查清除该具体残墨，同时逐字节检查保留字形实际UV不变；ASCII测试用自创斜边轮廓证明不是最近邻旧位图，并验证覆盖和布尔参数拒绝。

```powershell
$env:PYTHONPATH=(Resolve-Path build/dependencies/hd).Path
python -B -X utf8 tools/build_hd_font.py --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --font build/fonts/NotoSansCJKsc-Regular.otf --output build/runtime-feedback-20261106/font/modified-pack
```

实际输出：`HD_FONT PASS pages=8 glyphs=1433 ascii=95 scale=4 padding=transparent native_mapping=exact png_readback=exact runtime=user-test`，退出码0。独立再次打开8页PNG，原133664个间隔非透明像素变为0；1011个保留实际UV保持；原生FNT不变。数据见本地`sampling-verification.json`，真实图集读回对比见`font-readback-comparison.png`。CPU边界滤波探针仅为有界诊断图，不冒充游戏截图。

该修复属于可选高清包。原生字体构建不在此项改写，网络PF和图片烘焙字也不属于这8页。真实替换加载、GS滤波和全部页面运行显示仍由玩家验收；原生/高清的来源身份和安装清单必须随最终ISO重新生成。
