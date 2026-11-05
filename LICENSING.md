# 来源与许可

## 项目自编内容

- `src/`、`tools/`、`tests/` 中本项目新编代码：MIT，见 `LICENSE`。
- 原创简体中文译文：CC BY-SA 4.0，见 `LICENSE-translations.md`。
- 译文表中的韩文来源、原游戏文本与资产仍归原权利人所有；译文许可不覆盖原文、商标或游戏资源。

## 上游研究

| 项目 | 作者 | 参考版本 | 使用方式 |
|---|---|---|---|
| [Mystic Nights Translation](https://github.com/jeremydecola/Mystic-Nights-Translation) | Jeremy DeCola 及其翻译协作者 | `d58734cccf29b702330d131ea981de45512d3b76` | 参考资源定位、原英对照、道具关联及文档分页陷阱；不把完整英文资源作为构建输入 |

该仓库没有发现覆盖全部内容的显式开源许可证，不把上游商业二进制、图片或第三方工具重新标为 MIT。当前代码独立实现，关键格式和字体结论从本地韩版字节再次核验。现有 Git 分叉历史保留；当前源码树移除完整游戏二进制及旧工具打包材料，避免继续分发或修改提交这些完整资产。

## 字体和依赖

### 可选运行补丁研究

16:9 的三个地址/常量参考 Arapapa 的公开结果，来源为 [PCSX2 patches 锁定文件](https://github.com/PCSX2/pcsx2_patches/blob/93300862caa6498bfbadcd21a5857e458828360d/patches/SCKA-20055_83B9AE36.pnach)。该参考仓库根目录未见显式 LICENSE，不把上游补丁内容重标为本项目 MIT；保留作者与固定提交，逐条独立核验本盘原指令。分组工具、版本校验、CRC 计算实现和其余三项金手指由本项目独立编写；不复制上游完整补丁合集或模拟器代码。CRC 算法依据 [PCSX2 官方实现](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Elfheader.cpp) 的公开行为独立实现。

| 组件 | 许可/来源 | 分发方式 |
|---|---|---|
| Noto Sans CJK SC Regular | SIL OFL 1.1；[noto-cjk](https://github.com/notofonts/noto-cjk) | 按 `assets/font-source.json` 下载并校验，原许可随下载保留 |
| Pillow | HPND；[Pillow](https://github.com/python-pillow/Pillow) | 通过固定依赖安装，不捆绑二进制 |
| fontTools | MIT；[fonttools](https://github.com/fonttools/fonttools) | 通过固定依赖安装，不捆绑二进制 |

构建输出的字体图集仍遵循字体许可，其他未改像素来自本地原盘。当前仅发布重建方法/差分，不提交完整图集或 RES。

## 游戏资源

《Mystic Nights》原游戏由 N-Log Soft 开发、Sony Computer Entertainment Korea 发行。ISO、ELF、RES、视频、音频、模型及原字体不作为本项目自有内容授权。原始/测试镜像和提取目录只保存在被 Git 忽略的本地区域；PCSX2、BIOS、配置和存档也不加入仓库。

### 可选高清显示研究

PSMT8 地址/hash/精确 CLUT 文件名及 PNG 原始 alpha 行为依据 PCSX2 **v2.9.155** 的 `GSTables.cpp`、`GSTextureCache.cpp`、`GSTextureReplacements.cpp`、`GSXXH.cpp` 公开接口独立实现。未提交或复制 GPL 模拟器源文件。可选 `xxhash==3.6.0` 的 Python 包采用 BSD-2-Clause，底层 xxHash 为 BSD-2-Clause；通过固定依赖安装，不捆绑二进制。高清包含本地源素材的未改像素，不提交完整包或纹理；菜单配方只提交自创中文字形与源绑定差分，字体许可与原资产边界不改变。
