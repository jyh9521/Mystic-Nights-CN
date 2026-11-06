# 高清替换的CLUT16显式取样配置

## 已核对的来源

**Verified offline**：原盘`ST0101_905.TM2`的TEX0为`0x10000221310000`，PSMT8、CSM1、CPSM2（16位调色板）。256×256的字节索引按同一块内顺序进入XXH3；CLUT16先变为逻辑RGBA调色板再进入独立XXH3。

固定参考为PCSX2 **v2.9.155**：

- [GSClut.cpp](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/GS/GSClut.cpp)的`Expand16`（约812..845行）将RGB5直接左移3位，并从TEXA选择alpha。
- [GSTextureReplacements.cpp](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/GS/Renderers/HW/GSTextureReplacements.cpp)的`HashCacheKeyFromTextureName`及索引纹理命名路径不另添TEXA字段；实际展开的RGBA参与CLUT hash。

不能将RGB5按`*255/31`归一化或作bit复制为255。已核对的原盘贴图按`TA0=0,TA1=128,AEM=false`展开后，RGB5白为248，透明/不透明alpha为0/128。原纹理hash`a96bd077c53d25b4`、调色板hash`1b801200428cb3db`精确匹配所提供高清包中的`a96bd077c53d25b4-1b801200428cb3db-00002213.dds`。另外三种G293与CLUT16的G282也与所提供DDS的源键精确匹配，原样记录见本地`build/runtime-feedback-20261106/font/clut16-source-verification.json`。

这些源键对应和静态代码规则不是本机游戏加载观测；没有启动模拟器。

## 配方与拒绝规则

CLUT16图字行必须显式声明：

```json
"clut16_texa": {"ta0": 0, "ta1": 128, "aem": false}
```

`tim2_replacement_identity`和`raw_atlas`接收同名可选参数；图字构建器将该行配置同时用于最终原生图身份、无字基底解码及输出证明，避免一个环节错误沿用CLUT32假设。

- CLUT16缺省/空配置、额外键、布尔伪整数、超出字节的TA0/TA1或非布尔AEM均拒绝。
- 当前仅实现已核对的`AEM=false`分支；`AEM=true`明确拒绝，不猜未观察的零色透明行为。
- 只接收单mip、256项16位调色板、匹配尺寸的PSMT8、CSM1/CPSM2；长度、源身份或TEX0不符时拒绝。
- CLUT32原接口和产物身份规则不变；向CLUT32误传CLUT16配置也拒绝，不静默忽略。
- 同一个索引源在其他实际TEXA/调色板/区域下可能另有键，须有独立证据后再声明；不制造无CLUT的通配文件名。

## 回归

`tests/test_hd_palette.py`使用自创16×16索引TIM2、CSM1/线性CLUT和独立RES夹具验证RGB5左移、raw alpha、严格配置、头部拒绝和图字调用链。完整夹具包经过PNG回读、安装和独立撤销；没有提交原游戏资源。

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_hd_palette.py
python -B -X utf8 -m unittest discover -s tests -p test_hd_*.py
```

新增5项及全部32项HD测试通过；实际数量随后可随其他回归增加。完整底层覆盖检查与该配置独立，不能因支持CLUT16而跳过来源、范围、完整覆盖或正反向差分验证。
