# 可选宽屏与金手指

构建生成 `build/full-text/runtime/`，不改 PCSX2、BIOS、配置、存档，也不自动启动游戏。

普通构建只生成文件，**生成不等于已安装**。实际安装需显式运行以下命令，或按后面的手工步骤放置；不要把没有 portable 模式的程序目录误认为用户数据目录。

## 显式安装与撤销

```powershell
python -X utf8 tools/install_runtime_patches.py --package build/full-text/runtime --data-dir "PCSX2用户目录" --receipt build/runtime-install --enable-patch "16比9宽屏" --allow-cheats
python -X utf8 tools/install_runtime_patches.py --rollback --receipt build/runtime-install
```

`--data-dir` 必须是已有 `inis/PCSX2.ini` 的用户目录。安装器按该文件的 `[Folders] Patches/Cheats` 解析实际目录，并校验输出包 manifest 中的长度、SHA、序列号及 CRC。只安装选定原版/中文版的两份 PNACH；普通构建不调用安装器。

示例还创建本游戏独立 `gamesettings/SERIAL_CRC.ini`：仅勾选 16:9，开启本游戏金手指总开关，但三个金手指组默认均不勾选，可在游戏属性中自行选择。全局 PCSX2.ini、其他游戏设置、BIOS 和存档不改。已有不同的本游戏设置时拒绝覆盖，可去掉配置选项仅放置 PNACH 后在界面选择。

receipt 目录保存原文件备份、目标路径和安装后 hash。撤销前一次性核验全部目标与备份，再只还原原文件或删除此次新建的文件；用户后来改过目标时停止，不覆盖新改动。安装/撤销均不启动 PCSX2；隔离文件夹正反向验证不冒充游戏加载成功。

分组选择来自 `[Patches] Enable` 与 `[Cheats] Enable`，金手指还需 EnableCheats；依据 [PCSX2 v2.9.155 的加载实现](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/Patch.cpp#L539) 独立实现 INI 输出，不复制模拟器源码。

## 使用

1. 中文镜像使用 `runtime/localized/`，原盘使用 `runtime/original/`；不要混用。
2. 将对应 `patches/` 内 PNACH 放入你实际使用的 PCSX2 **补丁目录**，将 `cheats/` 内 PNACH 放入其 **金手指目录**。目录位置以模拟器自己的设置为准，不假定安装目录就是用户目录。
3. 游戏属性的补丁页仅有“16比9宽屏”；金手指页有“反转右摇杆水平视角”“无限子弹”“无限生命”三个独立开关，启用所需项目及金手指总开关。
4. 完全停止后打开新 ISO 冷启动，不加载旧即时存档。只把输出画面强拉到 16:9 不等同于宽屏补丁；PNACH 中包含 `gsaspectratio=16:9`。
5. 撤销时关闭对应项目后冷启动。PNACH 每帧写指令，关闭开关不会自动把当前运行内存里的旧写入反写回来；不要用“暂停/继续”代替冷启动。

这套输出遵循 PCSX2 的补丁/金手指目录区分、`SERIAL_CRC.pnach` 命名及分组开关语义。[PCSX2 官方补丁文档](https://pcsx2.net/docs/advanced/writing-patches/)

## 身份

原盘 ELF：`a8662cb99c7dd8abc66c6766d27e0fc15ff83fb3a04d2837001b87f88cf899c4`，本盘 PCSX2 CRC **2383B74A**。

中文 ELF 的 CRC 每次构建重算，见 `runtime/manifest.json` 的 `localized` 项。当前禁行首/字码配置对应 **634DBCA7**。不要把网络常见的原盘 `83B9AE36` 文件名直接用于本盘，或把旧汉化 CRC 用于新构建。

此 CRC 是整个 ELF 的小端 32 位字 XOR，不是 ZIP/ISO CRC-32，也不是 SHA-256 的前八位。[PCSX2 ElfObject::GetCRC 源码](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Elfheader.cpp)

## 指令配方与验证

以下是 EE 虚拟地址，文件偏移通过 ELF PT_LOAD 映射计算；并非盲目按地址写文件。所有组先验证原 ELF 长度、SHA-256、CRC、本盘原指令，以及中文 ELF 中这些指令仍未改变。

| 开关 | 地址 | 原字 → 新字 | 作用 |
|---|---|---|---|
| 16:9 | `0016AA5C` | `3C024400 → 3C0243C0` | InitCamera 水平焦距 512 → 384 |
| 16:9 | `0016AA74` | `3C023F08 → 3C023F36` | 垂直补偿常量高半部 |
| 16:9 | `0016AA78` | `3442F5C3 → 34429CFE` | 垂直补偿常量低半部 |
| 右摇杆水平反转 | `0016871C` | `3C02BD4C → 3C023D4C` | 正向轴分支的 yaw 步进改号 |
| 右摇杆水平反转 | `00168CAC` | `3C023D4C → 3C02BD4C` | 负向轴分支的 yaw 步进改号 |
| 无限子弹 | `001F7F94` | `A6E20030 → 00000000` | 不执行射击扣弹匣子弹的 SH |
| 无限子弹 | `001F8824` | `A0830004 → 00000000` | 不执行装填扣备用弹匣的 SB |
| 无限子弹 | `001F884C` | `A4C30002 → 00000000` | 不执行装填扣备用子弹的 SH，原为延迟槽 |
| 无限生命 | `001F98F4` | `A4C30012 → 00000000` | 不执行 SetPlayerDamage 的 HP 存储 |
| 无限生命 | `001FA54C` | `A6420012 → 00000000` | 不执行 PreUpdatePlayer 周期伤害的 HP 存储 |

宽屏三项数值参考 **Arapapa** 的公开补丁，并核对了本盘三处原指令；不包含去交错、其他比例或附加修改。[锁定的上游文件与作者](https://github.com/PCSX2/pcsx2_patches/blob/93300862caa6498bfbadcd21a5857e458828360d/patches/SCKA-20055_83B9AE36.pnach)

其余三组依据本盘函数独立定位：

- 水平轴：`UpdateCamera` 从角色数据 `+0x85E` 读取轴值，两个分支阈值为 -90、90，步进绝对值 0.05。水平两个分支交换符号，死区、转速和角度归一化分支不改。上下轴另在分支之前对输入反号，保留原非对称上下限与门控。
- 子弹：保留开火效果、弹匣容量和装填动作。不发放武器；空弹匣先正常装填，已持有弹药不再因射击/装填减少。
- 生命：阻止普通受伤及周期伤害扣 HP，保留护甲损耗、受击动作、治疗和剧情事件。开关不是复活指令，不据此声称剧情强制死亡已被绕过。

**Verified offline**：全部 16 组开关组合都在内存副本正向应用后逐字节撤销；1792 个水平轴值/角度组合、10752 个上下输入/高度/限位/门控组合、50 个实际 SB/SH/NOP 存储夹具和投影系数关系通过。原水平比例缩为 0.75，垂直投影乘积误差约 0.5ppm。

**待玩家验收**：宽屏场景/过场/HUD、普通/瞄准状态的视角操作、所有武器和伤害来源。上述静态及有界指令夹具不等同于运行游戏、模拟器执行或通关测试。

```powershell
python -X utf8 tools/verify_runtime_patches.py --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json
```

构建的默认 ISO 不含这十三处可选改动，因此镜像差分回滚与 PNACH 开关撤销是两件事：前者恢复原盘文件，后者需关闭开关并冷启动。

## 上下轴补充与保留玩家勾选

旧组 ID `right-stick-horizontal` 和显示名“反转右摇杆水平视角”保留，以兼容已保存的勾选；组说明注明现在同时反转上下。实际包有13个可选指令字，其中视角5字、三个金手指合计10字。

| EE VA | 原字 → 新字 | 作用 |
|---|---|---|
| `0016A2C8` | `2862FFA6 → 00031823` | `subu v1,zero,v1`，先反转 player+0x860 的有符号纵轴 |
| `0016A2CC` | `1440011D → 2862FFA6` | 搬移原 -90 阈值判断 |
| `0016A2D0` | `00000000 → 1440011C` | 搬移并重定位原分支，目标仍是0x16A744 |

只翻转±0.5常量会走错非对称限位分支，未采用。10752个有界指令夹具核对方向反转及原限位/门控；16种功能组合正反向字节一致。这不是模拟器执行验收。

本次新 ELF SHA 已改变，但整个 ELF 的32位XOR CRC仍为634DBCA7，不能用CRC相同推断文件没更新。实际安装只替换对应两份PNACH，保留玩家已勾选的三个金手指和宽屏，不再重建或覆盖这个游戏INI。
