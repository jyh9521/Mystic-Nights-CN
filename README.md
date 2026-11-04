# 《诡秘之夜》简体中文汉化

PlayStation 2《Mystic Nights》（미스틱 나이츠）的简体中文汉化项目，适用于韩版 **SCKA-20055**。

**汉化内容已写入测试版，尚未正式发布。** 正文与可读图片文字已完成翻译和原风格重绘，等待玩家手动进行游戏内验收。

## 汉化内容

已覆盖全部已提取剧情与动画字幕、菜单和系统提示、道具名称与说明、文档、联网设置，以及界面、场景标牌和画廊中的可读图片文字。模糊且读不清的原画注释保留原状。

- [测试说明](docs/TESTING.md)
- [开发状态](docs/STATUS.md) · [已知问题](docs/KNOWN_ISSUES.md)
- [发布列表](https://github.com/jyh9521/Mystic-Nights-CN/releases)

## 从源码构建

需要匹配的原版 ISO、Python 3.11+ 和按哈希锁定的开源字体。

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/fetch_font.py
python -X utf8 tools/build_locale.py --iso "原版游戏.iso" --locale zh-CN
```

验证镜像生成到 `build/full-text/`，原版 ISO 保持不变。工具不会启动游戏，也不会修改模拟器配置或存档。完整输入校验、恢复和重建说明见 [BUILDING.md](BUILDING.md)。

## 项目文档

- [翻译规范](TRANSLATING.md) · [简体中文风格](locales/zh-CN/STYLE.md)
- [技术说明](TECHNICAL.md) · [文件格式](docs/FILE_FORMATS.md) · [技术陷阱](docs/PITFALLS.md)

## 来源与许可

感谢 **Jeremy DeCola** 的 [Mystic Nights 英文化项目](https://github.com/jeremydecola/Mystic-Nights-Translation) 提供资源定位与关联关系研究，以及 Noto 字体项目。

自编工具采用 MIT，原创译文采用 CC BY-SA 4.0；原游戏和第三方内容各归其权利人所有。详见 [LICENSING.md](LICENSING.md)。
