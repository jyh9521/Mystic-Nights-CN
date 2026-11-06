# 即时演算过场字幕

## 当前状态

**新增、离线验证的可选引擎及编译链；未安装到当前默认测试ISO。** 原盘47个过场没有任何`CAPTION`节点。语音转录、中文译文、声学边界与游戏内绘制验收分别记录，不以机器转录、引擎原型或指令夹具代替完整字幕交付。

`tools/inspect_cutscene_subtitles.py`可从受支持原盘重新核验结构并生成独立原型。普通构建不隐式启用字幕，也不加载机器转录稿。`src/mysticnights/cutscene_subtitles.py`提供可复用的同尺寸脚本注入、守卫式ELF补丁、反向恢复和有界指令回放接口。

`tools/build_locale.py --subtitle-catalog 目录.json`是唯一显式启用入口；只支持`full-text`。它在任何字体生成/输出之前核验全部来源及每条`reviewed`、有效结束帧，零条可用字幕也拒绝启用。`locales/zh-CN/subtitles.json`保留尚未听审的草稿；默认配置不引用它，传入时应被门控拒绝，而不是偷偷把机器稿标成认可。

## 原盘已有但未完成的脚手架 — Verified offline

原ELF：`SCKA_200.55`，3,428,048字节，SHA-256：
`a8662cb99c7dd8abc66c6766d27e0fc15ff83fb3a04d2837001b87f88cf899c4`。

嵌入DWARF1保留`CUTSCENE.C`的函数/结构名。下列结论由原始结构成员、源字节及标准标量指令核对，不是运行观测：

| 地址 | 原生行为 |
|---|---|
| `ReadCutsceneCaption 0x13AAB0..0x13ACFC` | 分配/填充24字节字幕记录，解析`FRAME`、`POSITION`、`CONTENTS`、`NAME` |
| `ReadCutsceneInitData 0x13B7B0..0x13BF50` | 读`CAPTION_COUNT`并按24字节分配、清零记录；字幕数量计入统一节点分配 |
| `LoadCutscene 0x13BF50..0x13C478` | 注册字幕token并在`0x13C384`调用字幕读取器 |
| `StartNode 0x138CD0..0x139084` | 跳转表`0x24D3C0`的type 2字幕项指向`0x138FF4`，直接走共同返回路径，没有字幕激活逻辑 |
| `RenderCutscene 0x1388E0..0x138B18` | 原分支绘制3D对象/效果，没有字幕绘字调用 |
| `UpdateCutscene 0x139090..0x1393FC` | 按原`iFrame`匹配节点后递增帧号；之后才绘制，所以字幕使用`iFrame-1` |
| `RunCutscene 0x1596C0..0x1597F0` | `RenderCutscene`、`FadeScreen`、`Flip`、声音更新的原顺序 |

因此实际缺少的是字幕执行/绘制及其数据，不是需要从零另造资源解析器。原盘没有字幕的观察成立，不能因为存在一个`ReadCutsceneCaption`名字就声称字幕功能已可用。

`g_Cutscene`位于`0x29FB30`，DWARF大小1136字节。相关字段：`iFrame+0x02`、`bSkip+0x3F0`、`iNumNode+0x3F6`、`pNodeList+0x3F8`、`iNumCaption+0x414`、`pCaptionList+0x41C`。统一节点是三个little-endian signed short：`type,index,frame`，共6字节。字幕记录包含`iPosX+2`、`iPosY+4`、`strContents+8`和`iDuration+12`；原读取器实际把后者写成`start_frame + duration - 1`的包含式结束帧，不可把该字段再当剩余时长倒数。

## 帧驱动原型 — Verified offline / 待游戏测试

原型只把`RunCutscene@0x159748`的原`jal Flip`改为`jal`字幕绘制包裹函数。包裹函数：

1. 检查跳过状态、有效节点/字幕数量及指针。
2. 读取当前原生帧号减一，扫描type 2节点及字幕记录，仅在原始闭区间内选择字幕。
3. 保存完整32字节`fontEnv@0x2C4000`，调用原字体初始化，绘制黑色偏移阴影和白色正文。
4. 使用原`RenderString`而非printf封装，字幕里的`%`不会被当成格式参数。
5. 恢复字体环境与全部被使用的128位callee-saved寄存器，原`Flip`恰好调用一次。

无需常驻“当前字幕”指针，不改原type 2 no-op，也不改原节点激活顺序；下一场景、清空、跳过、字幕区间之外均没有继承上一个字幕的状态。Cues禁止重叠；同一帧的原节点保持原相对顺序，新增字幕排在该帧原节点之后。

代码按确定顺序链接到**已译ELF C字符串首NUL之后、经原范围hash及当前译文前缀验证的全零余量**；每块用显式jump和delay-slot连接，不拆开分支及其delay-slot。已有折行表或任何非零余量不会被占用。没有借用未证明安全的大块零区：原ELF中的约67KB连续零区属于嵌入式IOP模块区域，不当成代码洞。ELF长度、头、PT_LOAD、BSS、堆及原字符串首NUL之前的字节保持。

两条原来只影响未启用字幕记录的默认位置立即数改为`40,350`（`0x13AAEC`、`0x13AAF4`），使受容量约束的SCR不必为每句重复`POSITION 40 350`。原生字体换行宽度550像素。可见字幕布局/GS状态仍需实际游戏检查，离线回放仅记录对原绘字函数的参数调用。

所有写入记录包含前后字节、原/新完整ELF哈希及所属字符串槽。反向函数只接受完全匹配的新ELF并逐项核验，恢复的是**字幕钩子之前的汉化ELF**，不是撤销其他汉化。

## 脚本/相机格式 — Verified offline

过场脚本在47个`C001.SCR..C047.SCR`，与几何/相机可能分置不同的RES，例如某些`C014_*.RES`。库存按场景ID关联，不假定同名资源总在同一RES。

相机`Cxxx.BIN`头为五个u16LE：`magic=1001, frame_count, position_count, direction_count, up_direction_count`；其后是三段12字节向量数组。严格长度为`10+12*(position_count+direction_count+up_direction_count)`。`LoadBinary@0x1F4B40`调用`LoadCutsceneCamera`时在delay-slot给数据指针加2，确实跳过magic；不能把首个1001误读成场景帧数。C005为1700帧，C008为1300帧。

**GetToken按CRLF逐行读取命令，不是任意空白token流。** `GetToken@0x153118/0x153220/0x153250`核对了CR终止、整行复制及跳过CRLF；`GetNextWord@0x152FA0`只消费该行参数。脚本注入只能去缩进、空行及分号注释，保留每条原命令行与参数；压成单行即使Python分词相同也会被游戏错误解析。该错误路线在开发中被原指令审查识别并由回归拒绝，没有写入测试ISO。

注入形式：

```text
INIT_DATA {
原有计数与参数逐行保留
CAPTION_COUNT 1
}
...
CAPTION {
FRAME 720
CONTENTS 260 "经过声音复核并编码后的译文"
}
```

上例帧区间为`[720,980)`，不是实际对白译稿。所有原`SOUND/OBJECT/FADE/...`命令参数和相对顺序均逐行回读对照；新增节点稳定归并到原时间轴。新文本行限定原GetToken的512字节缓冲范围。输出补空格至原成员长度；余量不足明确报错，不截译文、不挪LBA、不暗改资源格式。47场景各一条明确标注的短合成cue容量夹具均通过，但这不证明每场完整听译都一定能放入现有容量。

## 结构化字幕接口与听审门控

目录格式`cutscene-subtitle-catalogue` v1：

```json
{
  "format": "cutscene-subtitle-catalogue",
  "version": 1,
  "locale": "zh-CN",
  "source_iso_sha256": "原盘SHA256",
  "resources": [
    {
      "scene": "C005",
      "resource": "原SCR所在RES路径",
      "member": "C005.SCR",
      "source_sha256": "原SCR哈希",
      "source_size": 0,
      "camera_resource": "相机所在RES路径",
      "camera_member": "C005.BIN",
      "camera_sha256": "相机哈希",
      "camera_frames": 1700,
      "cues": [
        {
          "id": "稳定字幕ID",
          "start_frame": 720,
          "end_frame_exclusive": 980,
          "text": "经声音复核的译文",
          "status": "reviewed",
          "source_audio_sha256": "实际声音哈希",
          "source_transcript": "经声音复核的来源转录"
        }
      ]
    }
  ]
}
```

实际输入必须列全47个来源身份，示例只展示一项结构，不是可直接构建的数据。空`cues`表示尚无字幕数据，不能当作“无台词”或“已完成”。`status=asr-draft`、缺少声音哈希/来源转录、未知字形、重叠、无效帧、未知源、重复ID、超容量均拒绝。新字幕字符须在生成主字库前并入locale的所需字符集合，不能先生成字体再塞入未分配字码。

帧号是游戏自己的时间轴；未经过验证的每秒帧数不参与编译器。音轨长度与相机帧数接近60帧/秒是**High-confidence deduction**，不是已经由运行实测证实的固定帧率；音频秒数转成字幕帧需要另行对时。

主要接口：

- `inventory(original_image)`：完整47场景SCR/相机身份。
- `validate_catalogue(image,catalogue,locale=...)`：在生成字体前核验完整来源、locale及全部字幕门控；没有reviewed cue也拒绝启用。
- `validate_cues(cues,camera_frames=...)`：音审/帧/区间/文本门控。
- `inject_script(script,cues,encode,camera_frames=...)`：保留原生行语义的同尺寸脚本。
- `build_script_edits(image,catalogue,mapping)`：按`resource -> (group,index) -> bytes`返回成员改动；调用者与图像成员改动合并后重建RES。
- `build_engine_patch(original_elf,current_elf,entries,mapping)`：在其他汉化ELF编辑之后生成代码；返回修改ELF和守卫式receipt。
- `reverse_engine_patch(elf,receipt)`：独立副本逐字节恢复。
- `replay_engine_hook(elf,receipt,frame=...,nodes=...,captions=...,skip=...)`：有界原生指令夹具，原字体/Flip调用使用明确的合同桩。

## 复现命令

```powershell
$env:PYTHONPATH='src'
python -B -X utf8 -m unittest discover -s tests -p test_cutscene_subtitles.py -v
python -B -X utf8 tools/inspect_cutscene_subtitles.py --iso "[full2]미스틱 나이츠(K).iso" --output build/subtitle-inventory
python -B -X utf8 tools/inspect_cutscene_subtitles.py --iso "[full2]미스틱 나이츠(K).iso" --localized build/full-text/Mystic-Nights-zh-CN-full-text.iso --manifest build/full-text/manifest.json --output build/subtitle-engine-prototype
```

输出目录必须不存在。原型目录的`MODIFIED_FILE.elf/DIFF_FILE.json/VERIFICATION.txt/ROLLBACK.sh`是独立ELF研究产物，不是已经安装或包含完整对白的游戏镜像。使用Git Bash执行该`ROLLBACK.sh 修改ELF 新恢复ELF`；它只写新文件，拒绝覆盖。

显式字幕构建会先把所有已审核字幕并入`localized_resources(...,additional_font_texts=...)`，然后使用同一完整字码表生成正文/字库/字幕；字幕SCR成员改动与其他RES改动按原字节守卫合并。字幕ELF钩子在折行补丁之后生成，再按最终ELF生成运行补丁CRC。构建清单的`full_text.cutscene_subtitles`嵌入原字幕目录、目录哈希、独立脚本报告和ELF正反向写入清单。

`tools/verify_build.py --kind modified`会自动独立重建清单中声明的字幕，不依赖原输出目录；可加`--subtitle-catalog 同一目录.json`强制校验输入文件身份。验证器还对每条实际字幕执行开始前/首帧/末帧/结束后/跳过五种原生指令夹具，核对全部脚本行语义、code-padding所有权和字库真实回读。未声明字幕的旧ISO不接受显式字幕验收参数。

## 验证与未完成项

21项新单测包括：原生CRLF、稳定同帧顺序、相邻字幕、短整型边界、跳过、清空、坏索引、百分号字面值、阴影与正文参数、128位callee-saved/字体状态恢复、离散代码桥接、越界/脏余量/未知来源拒绝、完整反向恢复、默认不开启、ASR前置拒绝和通用字体追加输入。实际原盘/当前汉化ELF上额外检查47场景、14处机器字节锚点与8组生成代码回放；当时需要11块字符串余量，代码/钩子/默认位置共556字节。

有界回放器独立实现了本补丁使用的指令子集，没有复制模拟器源码。EE的`LQ/SQ`为128位传送，`ADDIU`为32位相加后符号扩展到寄存器低64位；编码表与这些语义额外对照固定版本的[PCSX2 v2.9.155实现](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/R5900OpcodeImpl.cpp)和[指令表](https://github.com/PCSX2/pcsx2/blob/v2.9.155/pcsx2/R5900OpcodeTables.cpp)。生成代码的全部`LQ/SQ`有效地址均16字节对齐；该夹具仅用于生成代码的合同验证，不是完整EE模拟器或GS绘制器。

### 源码隔离的端到端重建

`build/runtime-feedback-20261106/subtitles/integration-final/integration-result.json`记录了基础源码归档的提交/哈希、八个实际覆盖源码的哈希，以及完整命令记录目录。该测试在独立源码目录中执行，合成字幕只用于开发验证，未安装或替代默认测试ISO：

| 检查 | 实际结果 |
|---|---|
| 默认构建，无`--subtitle-catalog` | 1,433字形；SHA-256 `d8db7a92b894bc6c20a4e6f5dcf1e9ec08fc066c321fa5d8edb1e8377f4cec0e`，与修改前默认ISO逐字节一致 |
| 未审目录 | 构建返回1，且输出目录未创建 |
| 完整47场景身份、C005一条合成`reviewed` cue | 额外字形“鹫”在主字库分配阶段并入，总1,434字形；合成夹具ISO哈希 `205ff214a0a166f1f30d28fd46afbf38ac6e710d92e6b1baa5df779e2e2ac002` |
| 独立验证器 | `CUTSCENE_SUBTITLES PASS scenes=47 captioned=1 reviewed_cues=1 replay_cases=5 source_bound=pass game_executed=false`；最终ELF运行补丁CRC `C940895F` |
| 实际生成的ISO `ROLLBACK.sh` | 对独立夹具恢复1,696,530,432字节，哈希 `4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b`，与原盘一致 |
| 恢复后重新验原盘 | `BASELINE PASS files=724 resources=209 scripts=179 source_slots=2306` |

各步骤的精确argv、工作目录、标准输出和退出状态保留在`integration-final/commands/stage-*.json`，聚合到该目录`VERIFICATION.txt`。合成cue的文字和“reviewed”仅用于明确标记的开发夹具，既非原声转录，也不计入正式字幕完成数量。当前`locales/zh-CN/subtitles.json`保留47场景、10条ASR候选、0条听审认可；全部结束帧仍待对时。直接传入该真实草稿的门控记录为`subtitles/actual-draft-gate.json`。

Windows REA当前Ghidra配置仅接受PE，Hopper不支持Windows/MIPS，IDA无已验证MIPS通道；原MIPS ELF反编译调用明确返回`capability_unavailable`。没有把该调用当成成功分析；本实现依据原DWARF、逐字节锚点及独立指令读取/回放。

剩余：全部实际语音的声音复核和准确译文/声学对时；正式字幕目录完整性；游戏内GS混色、换行、帧同步、切换/跳过/存取场景与全流程验收。默认构建不启用未审目录，不能把当前ISO称为“过场已全部加字幕”。
