# 当前定稿构建与本地存储

## 当前运行反馈版

最新标准 ISO 为 `820af76e83fdeddf79d067f53b604f0c67c08178bcec0a10afc564c01d2fd89a`；下方 d8db7a92 冻结重建是前版。当前修改源码 `ea8e4290b79ec3cdfa4888c5a613881e6dd3ce5a` 的干净归档和标准输出共 1387 件字节一致，标准回滚脚本在独立副本实际恢复全部原盘字节。

完整预检、归档逐成员 SHA/CRC 核对后，PowerShell 按明确绝对路径清理 4563 件、19,031,814,380 字节，其中 11 份旧/验证/合成字幕 ISO。226,214,254 字节技术/输出证据归档保留于 `build/runtime-feedback-20261106/retired-output-evidence.zip`，SHA256 `c16edc23a1d4f67b9859cb05949eaea3a468328b615c66193917b6a344005216`；净回收 18,805,600,126 字节。逐文件预检与执行汇总分存 `cleanup-plan.json`、`storage-report.json`，不由命令日志覆盖。

保留原盘与最新 ISO 两份、当前筛查页、锁定字体/依赖、138 输入的音频提取及机器候选、九张截图和 GS 待查证据。实际安装收据 `build/runtime-feedback-20261106/installed-font/`、`installed-artwork/` 与恢复旧 19 张 PNG 所需的 `previous-pack/` 保持原位置；原旧包收据链及前版可逆补丁也保留。合成字幕 ISO 已清理，不发布；字幕研究命令、脚本、差分/回滚及旧清单仍保留。

不删除 PCSX2、BIOS、存档、外部下载的高清材质或其他项目。最新实际 Textures 仅更新本游戏自有 15 图字＋8 字库、退休 4 个旧键，未整包合并下载 DDS。原 INI/PNACH/README 字节保持，不启动游戏。

## 2026-11-06定稿重建

用户指示“就先这样”，因此冻结当前译文、图像、字体和补丁数据，不再重新生成图片或修改选项。以提交`324c36471ab801d18082098ebc55d584199e76d5`的干净源码和锁定原盘重新构建，正文/图字/高清配方/运行补丁均不依赖旧创作目录。

新ISO沿用`build/full-text/Mystic-Nights-zh-CN-full-text.iso`。原盘SHA-256为`4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`，重建ISO为`d8db7a92b894bc6c20a4e6f5dcf1e9ec08fc066c321fa5d8edb1e8377f4cec0e`。内容冻结且构建可复现，故新旧ISO哈希相同，不为了更换哈希而修改游戏字节。

385项测试、两个JS套件及整盘验证通过；36件交付输出、1343件筛查输出共1379件与此前定稿逐字节一致。目录切换使用串行同卷原子重命名；新交付的实际`ROLLBACK.sh`在独立副本测试，恢复全部原盘字节并重新通过基线。工具不启动游戏。

## 保留与清理

- 保留根目录原盘与`build/full-text/`最新ISO，两份游戏镜像；不保留历史PoC、合成夹具、独立回滚测试ISO。
- 保留源码/结构化译文/差分/格式研究文档及Git历史，`build/fonts/`锁定字体，当前筛查网页、高清包和可选运行补丁。
- 当前e97f画稿、意见与保护样本继续位于`build/feedback-e97f/`。外部真实PCSX2 profile关联的安装收据及其before备份链保持原路径，避免破坏撤销能力。
- 可选`xxhash==3.6.0`本机依赖从旧实验目录复制并逐字节验证至`build/dependencies/hd/`；正常重建仍可按`requirements-hd.txt`安装，不依赖旧目录名。
- 旧提取RES/ELF/TIM2、重复字体、旧预览和可重建二进制输出删除。技术报告、脚本、未知研究格式、手册及历史可逆MNP差分先压缩至`build/evidence-archive/retired-builds-20261106.zip`，每个成员按原hash重新打开验证后再清理散文件。
- `pcsx2/`、BIOS、配置、记忆卡、存档及其他项目均不是清理对象。23项实际已安装文件/INI的hash在操作前后核对；当前高清包、宽屏/金手指及玩家开关不改。

清理在PowerShell内完成绝对路径、reparse、完整文件集及删除前再次hash预检；遇到新增/改变文件或未知ISO即停止，不使用宽泛`git clean`。本地实际命令、输入、输出、回滚和存储统计见`build/full-text/VERIFICATION.txt`与`build/rebuild-20261106/storage-report.json`。生成文件和证据归档不提交GitHub，README保持。

## 实际存储复核

清除13,141个旧输出/验证文件，7,375,899,949字节；其中2628份报告/脚本/手册/历史差分压缩保留为87,328,642字节，扣除归档后回收7,288,571,307字节。此总数包含新建的独立验证副本；原有build目录自身从约4.03GB降至约2.04GB。原盘与最新测试ISO恰为两份，hash均复核；23项实际安装文件/INI保持，README和源码/译文/图字数据不变。

归档SHA-256：`fdab819b305b7c521279e5590f12ee382d8ccae39df6ee511b220f1524f5d091`。清理后再次打开、完整CRC检查通过。清理成功后，旧命令记录器的同名`cleanup.json`覆盖了详细逐文件hash报告；没有伪造补回该报告。保留已成功执行的PowerShell脚本、原样stdout、清理前文件尺寸清单及归档内容；汇总由实际stdout恢复，归档/两份ISO/玩家文件另行复核。后续记录器统一使用`stage-`前缀，结构化存储报告独立命名；没有重复执行删除。
