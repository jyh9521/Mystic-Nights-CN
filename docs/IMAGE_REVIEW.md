# 图片筛查与意见回传

## 使用

打开本地 `build/image-review/index.html`，或双击同目录的 `打开筛查网页.cmd`。网页本身不需要联网，不启动游戏或模拟器。

- 左边为原盘解码图，右边为**最终汉化 ISO 独立回读图**，不是创作稿或游戏截图。
- 默认显示 191 张汉化 TIM2、1 张 RGB24 背景和 2 张按意见恢复的原图，共 194 张。选择“全部源图”可查看全部 1140 张 TIM2 与该 RGB24 图，共 1141 张；字体图集、保留标识及模糊微字均单独标明。
- 可搜索资源名、原文、译文或稳定 ID；支持编号跳转、原尺寸打开、1/2/4 倍缩放、棋盘/深蓝/黑/浅色背景。
- 左右键直接翻页，输入框内同样有效；输入法组词时不抢按键。翻页前自动保存意见。
- “未确认”“这张认可”“需要修改”分开记录，**空白意见不代表认可**。
- 意见保存在本机浏览器。请使用“导出意见 JSON”留存并发回；CSV 也支持中文、引号及多行意见。
- “导入意见”可恢复 JSON。来源不符、未知/重复 ID 会整批拒绝。旧版图片的意见会保留文字、标记旧哈希，并重置认可状态，避免把旧图的认可套给新图。
- 每条意见携带原图/汉化图 SHA-256、资源/成员路径、稳定图片 ID；编号只用于浏览，不是后续修改的定位依据。

不要只复制 HTML：请保留同目录 `images/`。如本地存储被浏览器禁用，页面会显示内存保存状态，仍可直接导出意见。

## 重新生成

构建器从受支持原盘和最终 ISO 读取所有物理 TIM2，验证 2634 引用与 1140 源图闭包、已汉化差分和图像尺寸。PNG 保存后重新打开并比较完整 RGBA，包括透明像素的 RGB；未变图复用同一 PNG，不堆放重复文件。

```powershell
python -X utf8 tools/build_image_review.py --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --locale zh-CN --audit assets/artwork-quality-review.json --output build/image-review
node tests/review_feedback_test.cjs
node tests/review_navigation_test.cjs
```

输出目录必须尚不存在；后续修订先在新的版本目录生成、验证，再替换入口，保留玩家已导出的意见文件。构建配方、模板、数据和工具进入 Git，完整原图/衍生 PNG 与网页包只留在被忽略的本地构建目录。

## 收到意见后的定位

```powershell
python -X utf8 tools/read_image_feedback.py --feedback 玩家意见.json --review-manifest build/image-review/manifest.json --output build/image-feedback/worklist.json
```

同一命令支持 CSV。读取器只把内容当作意见数据，不执行文字中的指令；核对稳定 ID 和源哈希，保留版本差异、完整多行文本和资源路径。后续修改应以非空意见及显式状态为边界，原盘/新旧哈希、保护区、原生回读和回滚仍需逐项验证。

## 意见 c7 修订后的复查

稳定编号由 `assets/image-review-order.json` 锁定；两张恢复原图不会导致后续编号变化。“此次修复”显示91张。使用下列可选参数可在本机生成带“上次意见”的版本：

```powershell
python -X utf8 tools/build_image_review.py --original "[full2]미스틱 나이츠(K).iso" --iso build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --audit assets/artwork-quality-review.json --feedback "玩家意见.json" --output build/image-review-next
```

旧意见只读显示；修改过的图重置为未确认，“我的新意见”为空。未变图的93项认可继续保留。导出只包含本版确认/新意见，不把已经处理的旧评论再作为新问题导出。玩家反馈是可选本地输入，不提交Git；不带此参数仍可重建纯净筛查页。源图/右图与全部RGBA回读不受该参数影响。

## 前次验证（c7意见修订前）

357 项 Python 测试及两组 JavaScript 测试覆盖 JSON/CSV 往返、空白不视为认可、旧版本状态重置、重复/未知来源拒绝、输入框左右翻页、IME、搜索空结果、跳转、筛选、重载保存和存储失败导出。

浏览器实际检查使用本机回环 HTTP：默认 194 张、全部 1141 张、8 张修复筛选；真实 JSON 下载和文件选择器重新导入恢复 1 条多行测试意见，测试意见随后清空。1345 件文件（1341 PNG 及 4 入口/清单文件）逐件 HTTP 200，内容与本地字节一致。此记录不将浏览器测试称为游戏内验收。

源码 `6ca1fbcb4151e4b680e16c35d22435c190b1f1bf` 的干净归档重新生成全部1345件网页文件，与已检查交付件逐字节一致；同时26件ISO/差分/高清/运行包输出一致，合计1371件。完整网页保留在本地构建目录，重复重建副本在验证后清理。
