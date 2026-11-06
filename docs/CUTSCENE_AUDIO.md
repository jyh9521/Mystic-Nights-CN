# 即时演算过场的语音与听审数据

## 当前证据等级

**Verified（原盘、脚本和离线解码）**：受支持韩版原盘有47个逻辑`C001.SCR`至`C047.SCR`过场脚本，分布在多个`RES/CUTSCENE/`容器。它们有172个`SOUND`节点：37个BGM、125个EFFECT、10个VOICE，没有原生`CAPTION`块。10个VOICE位于C005/C008/C012/C021/C027五个场景。此计数只覆盖即时演算过场，不冒充344个独立对话VAG或全游戏音效的完整听审。

所有172个节点闭合到138个唯一声音输入：32组MIH/MIB、10个独立VOICE VAG、96个资源内VAG（含常驻`SYSTEM.RES:EMPTYCARTRIDGE.VAG`）。同场景拆分资源中的声音按逻辑C编号关联，常驻音效采用明确的SYSTEM来源；缺失或不同hash的同名候选报错，不任选一个。源节点保留原成员偏移、原字节hash、原`FRAME`、类型与参数。

实际生成138个PCM16 WAV并逐一回读，通道、采样率和精确采样数均与原压缩数据布局相符；全音频时长合计约1182.392秒，包含音乐和特效。相同源码两次提取的373个文件（含清单）逐字节相同。解码成功和机器转录不等于实际听审，工具不启动游戏或模拟器。

**Verified（引擎静态研究）**：引擎侧还保留未被这些脚本使用的字幕读取入口，不能仅因游戏中未显示字幕就说整个引擎完全没有相关功能。绘制/编译/触发研究见[CUTSCENE_SUBTITLES.md](CUTSCENE_SUBTITLES.md)。本工具仅提取，不修改脚本或ELF。

## 格式核对

`cutscene_audio.py`是独立实现的读取器，未复制上游源码。MIH字段解释参考并核对[vgmstream的mib_mih.c](https://github.com/vgmstream/vgmstream/blob/6802153425adde134e49394fc653455166d7d2f2/src/meta/mib_mih.c)，固定提交`6802153425adde134e49394fc653455166d7d2f2`。

- 本盘VAG为48字节`VAGp`头、big-endian `version=0x20`、数据长度及采样率。数据按16字节PS-ADPCM块组织，每块28个采样。必须与完整文件长度相符。头内调试名称可能含非ASCII字节，保留十六进制，不猜名字编码，也不把名称误当解码参数。
- MIH恰为64字节。u32LE@0为64，u32LE@4低8位为32，高24位为最后一块每声道有效字节数；@8为通道数，@12为采样率，@16为每声道交错块字节数，@20为块数。
- MIB没有MIH文件头；声道按完整交错块拆分，只截取最后一块的声明有效字节。拒绝越界、非16字节块、缺少明确块数以及文件长度不符。解码临时声道使用标准VAG包装，交给显式指定的FFmpeg，不使用MIB的PS-ADPCM标志猜循环点。
- WAV时长以`样本数/采样率`有理数保存。原`FRAME`是游戏内调度单位；提取器不假定30/60fps，不把外部墙钟时间直接写回脚本。

## 重建提取

普通汉化构建不依赖FFmpeg或语音识别库。提取为只读操作，源盘先按`assets/game-version.json`完整校验；输出必须是新目录。生成的游戏音频及模型均不提交Git。

```powershell
$ffmpeg = (Get-Command ffmpeg).Source
python -B -X utf8 tools/extract_cutscene_audio.py --iso "[full2]미스틱 나이츠(K).iso" --output build/cutscene-audio --ffmpeg $ffmpeg
```

省略`--ffmpeg`仍可提取源绑定调度、原压缩数据及格式元数据；只有显式传入已存在的解码程序才生成WAV。已验证本机解码器为FFmpeg 9.0.2。清单记录其版本、每次解码参数、原样输出和退出码。参数使用相对于提取事务目录的路径，不把随机临时目录名写进可复现清单。

## 机器转录与听审门控

`tools/transcribe_cutscene_audio.py`只接受源绑定提取清单和hash匹配的WAV，显式使用本地模型目录并禁止自动下载。其可选依赖的已验证版本为`faster-whisper==1.2.1`和`ctranslate2==4.8.1`；模型目录内各文件hash与运行版本写入输出清单。核心提取/构建不导入这些可选库。

```powershell
python -B -X utf8 tools/transcribe_cutscene_audio.py --manifest build/cutscene-audio/manifest.json --model-path MODEL_DIRECTORY --selection scene --device cpu --output build/cutscene-asr
```

`--selection voice`只处理10个明确VOICE输入，`scene`增加18个专用Cxxx背景音轨，`all`处理全部138输入。输出始终为`asr-draft`且`human_listening_verified=false`；不会改locale、写字幕或将空检测结果当作“没有对白”。

本次采用本地small/medium/large-v3缓存对10条VOICE交叉转录，large-v3另筛检全部138输入。18个专用Cxxx混音的VAD没有检出语音，但该结果不是人工无对白确认。全量机器筛检在部分音乐/效果上生成了“感谢观看”“请订阅点赞”等典型幻觉，明确不采用。机器转录后的文本校审和实际原声听审分别记录。

### 初次机器筛检时尚需听审的短音节（历史记录）

- `007_001.VAG`：原C012 FRAME380，模型/能量裁剪只恢复`신!`，词概率约0.52。EVENT163确有简（`제인2_03`）及V004，属于呼喊简的上下文支持，不是确定听证。
- `016_001.VAG`：原C021 FRAME335，有效波形约0–0.84秒；无VAD/裁剪转录为孤立辅音和`Gah!`，支持非词呻吟，不编造成句。
- `016_002.VAG`：原C021 FRAME410。无VAD整段和裁剪均恢复两次`브루스!`，第二词概率约0.978/0.979。EVENT454的既有原文描述布鲁斯突然倒下，与“布鲁斯！布鲁斯！”候选相符；保留不同模型最初误识结果，不伪装为已听原音。
- `021_003.VAG`：原C027 FRAME1405。VAD无输出但不是静音：峰值约0.988，有效波形约0–0.74秒；有界强制转录恢复喊叫`흐아악!/Ah!`，无可靠实词，不造台词。

本地`build/runtime-feedback-20261106/audio/`保留原始三模型结果、全量筛检、四段无VAD/裁剪对照、原声WAV和初次听审网页。玩家随后确认九条译文并委托C012消歧，三条指定修订已回填；当前新页面在`build/subtitle-listening-20261106/listening-review.html`，显示既有文本确认与独立待验收的推导时间轴，详见[本次记录](SUBTITLE_LISTENING_20261106.md)。历史ASR数组不改写为人工听证。`tools/build_cutscene_audio_review.py`以完整`locales/zh-CN/subtitles.json`和提取清单重建页面，按`source_audio_id`动态匹配并核验WAV，不依赖机器草稿中的旧本机路径。

```powershell
python -B -X utf8 tools/build_cutscene_audio_review.py --catalogue locales/zh-CN/subtitles.json --audio-manifest build/cutscene-audio/manifest.json --output build/cutscene-audio/listening-review.html
node tests/cutscene_audio_review_test.cjs build/cutscene-audio/listening-review.html
```

网页可以播放原声、填写韩文/译文/结束帧并导出完整`cutscene-subtitle-catalogue`，可直接供`--subtitle-catalog`读取。47个源SCR与camera身份、原cue ID/音频hash/模型证据完整保留；42个空场景保持未认可，`all_speech_transcribed`仍为false。音频路径只在网页映射元数据中，不添加到导出目录。初始认可数为0，旧保存的勾选也不自动恢复；明确听审确认、合法译文和不超出下一字幕/camera上界的结束帧是导出`reviewed`的必要条件，编辑文字或时间会撤销确认。

真实生成JS已离线往返到原生目录验证器：未勾选草稿仍拒绝；10次明确模拟确认的**测试夹具**匹配47份真实源身份并通过schema。模拟点击不是真实听审，夹具不安装。页面逻辑已离线测试，不代表浏览器视觉或游戏显示验收。

## 回归

```powershell
$env:PYTHONPATH = 'src'
python -B -X utf8 -m unittest discover -s tests -p test_cutscene_audio.py
```

17项测试覆盖VAG字节序/完整帧/opaque名称、MIH最后块/交错边界、注释过滤、源FRAME保持，以及ASR输入的未知来源、重复ID、hash错误和路径越界拒绝。原版音频保持，机器草稿不进入ISO。
