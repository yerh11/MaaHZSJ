# CLAUDE.md

本文件是 **MaaHZSJ 这个仓库自己的**开发指引 —— 结构、命令、门禁、铁律。
工作区根目录那份 `../CLAUDE.md` 讲的是另一件事：**玩法与判据的来历**（用户教过的
流程、每条规则哪天为什么那么定、那一整张窟窿表）。**两份都要读**：动结构看这份，
动策略或查"这条判据到底哪来的"看那份。本文件不重复它。

## 这是什么

基于 **MaaPracticeBoilerplate** 模板的 **MaaFramework** 集成项目，目标是让脚本自己
跑完《魂坠深境》的整局循环：主界面开局 → 走地图 → 处理每个地点 → 打每场仗 →
走到结局 → 收尾回主界面 → 再开下一局，全程不用人点。

**真正在开发的是 `script/` 那套自驱脚本。** 它绕过 pipeline 的任务调度器，把 pipeline
节点当**识别探针**用（`Game.probe()` 走 `post_recognition` 快路径 —— 每轮只截一次图、
对全部候选节点复用）。`assets/resource/pipeline/` 只负责回答「每个界面长什么样」，
不负责流程。Pipeline 的 `next` 列表只能表达"顺序探测 + 超时"，写不了循环和状态机，
所以**复杂流程一律写在 `script/`，识别定义仍留在 JSON**（这样还能继续用 `save_draw`
可视化调试，改模板/阈值不必动代码）。

## 运行环境（实测，别猜）

| 项 | 值 |
|---|---|
| 游戏包名 | `com.chillyroom.containerofsoul.yw`（凉屋游戏，v1.1.1） |
| 启动 Activity | `com.chillyroomsdk.sdkbridge.BasePlayerActivity` |
| 模拟器 | MuMu 12，装在 `D:\Program Files\MuMuPlayer\` |
| 截图分辨率 | **1280x720**，恰等于 `display_short_side: 720` ⇒ **零缩放**，模板 1:1 裁剪 |
| adb | 由 `Toolkit.find_adb_devices()` 自动探测，会选中 MuMu 自带 adb；截图走 EmulatorExtras（最快且无损），无需手工配置 |

⚠️ **MuMu 不能提权跑** —— 提权起模拟器（或让脚本去连一个提权起的 MuMu）会让引擎
认不出设备（`未找到 MuMu 设备`）。要么 MuMu 非提权起，要么脚本提权跑。

⚠️ **非 16:9 不支持**：全部坐标按 **1280x720** 写、收在 `script/shared/coords.py`，
靠框架的 `display_short_side: 720` 归一兑现 16:9 的全分辨率自适应。`Game.connect()`
检测到帧不是 1280x720 会打一行警告；**不在 Python 侧缩放** —— 那会与框架叠加、
在同一帧上造出两个坐标系，是新的假判据来源。

## 目录：四层 + 一个操作小类层

| 层 | 位置 | 职责 |
|---|---|---|
| **识别定义** | `assets/resource/pipeline/*.json` | "每个界面长什么样" —— 模板图、OCR 词、roi |
| **流程逻辑** | `script/battle.py` + `recognizer.py` + 四个屏包 `nav/ nodes/ combat/ system/` | "按什么顺序做、遇到分支怎么办" |
| **操作小类** | `script/ops/` | 一个卡牌操作一个模块（copy / remove / upgrade / destroy），互不 import |
| **原语层** | `script/core/auto.py` | `Game` 类：截图 / 识别 / 点击 / 等待 / 战斗 / 退局 |
| **公共层** | `script/shared/` | `kit`（停车留证 `park` + 唯一日志口 `log`）· `reasons`（全部停车理由 + 两个协议值）· `coords`（**全部固化坐标**）· `cards`（保留卡名单）· `gridstate`（**全脚本唯一一处跨屏状态**）· `grid`（卡牌网格机制） |

```
script/
├── strings.py      「脚本 ↔ 游戏」字典 —— 脚本里不许出现游戏里的字，一律走它的常量
├── events.json     事件集（改事件策略的地方）
├── recognizer.py   **唯一**一张认屏表：每屏一行（判据 + handler + 顺序 note）
├── battle.py       入口 / 跨局主循环
├── core/  shared/  ops/  nav/  nodes/  combat/  system/
```

**`assets/resource/pipeline/` 按操作分族，11 个文件**（2026-10-12 归位，纯搬家）：
选择族 · 卡牌族 · 战斗族 · 游艺族 · 地点族 · 凝视族 · 地图族 · 启动族 · 仪式族 ·
结算族 · 系统族。族名闭集由 `tools/check_strings.py` 的 `FAMILIES` 钉着（防将来
随手加一个 `新东西.json`）。

**依赖方向**：`nav/nodes/combat/system` 与 `ops/` 都是**叶子**，屏与屏之间不许互相
import（唯一例外 `nav/map_view.py → nav/map.py`）；它们由 `recognizer.py` 按屏分发调用。
这条禁令由 `tools/check_screens.py` 机器核 —— 谁 import 谁都会在将来某天变成环，
环在 import 期就炸。完整依据见 `docs/zh_cn/架构与流程图.md`。

## 常用命令

```bash
# —— 跑脚本（入口：一局接一局地打，Ctrl-C 停）——
python script/battle.py 噩梦9层
python debug/play.py 40            # 从当前界面接着跑一局（不重启、不开新局）

# —— 迭代 pipeline 节点：截图 → ocr_screen.py 摸特征 → 写节点 → test_reco.py 验证 ——
python debug/ocr_screen.py             # 截当前屏幕，列出全部 OCR 文字+坐标
python debug/test_reco.py <节点名>      # 跑单个节点，只识别不点击（安全无副作用）
python debug/test_reco.py <节点名> --run

# —— 资源校验（CI 同款，先装依赖）——
npm ci && npx @nekosu/maa-tools check
python tools/validate_schema.py --schema-dir deps/tools \
  --resource-dirs assets/resource --interface-files assets/interface.json
python tools/check_strings.py      # 字符集自检
python tools/check_screens.py      # 结构自检

# —— 打包 / 补模型 ——
python tools/install.py v1.0.0 win x86_64
python tools/configure.py          # 补 OCR 模型（仅在 model/ocr/ 不存在时才复制，不覆盖）
```

运行调试也可以走通用 UI / MaaPiCli（`deps/bin/MaaPiCli.exe`）。**本项目不自建 UI** ——
模板自带 CI 会把 MFAAvalonia 一起打包发布，`assets/interface.json` 就是给那个 UI 读的。

## 门禁：改完必跑

**CI 不跑下面这些，得手动跑。** 全绿才算改完：

| 命令 | 盯什么 |
|---|---|
| `python -m py_compile <改动的 .py>` | 语法 |
| `python tools/validate_schema.py ...` | pipeline / interface 的 JSON Schema（本来就 `rglob`，整棵都扫） |
| `python tools/check_strings.py` | 节点名在管线里真存在、难度/词条有对应、脚本里没有漏网的裸字符串、常量都 import 过、没有没人引用的死名字 |
| `python tools/check_screens.py` | 认屏表与屏模块一一对上、四个叶包无环 import、`ops/` 互不 import、表序断言、`RECHECK_EXPECT` 三行 |
| `python debug/_negtest_strings.py` | 上面那条 check_strings 的反例自测（改过它才需要） |
| `python debug/test_*.py` | **16 个单测**（假 Game 量时序 / 帧回放），其中 **13 个纯离线、全绿**；`test_fight` / `test_reco` / `test_wheel` **要开模拟器** |

⚠️ 这些脚本会往控制台打 `✅` / `❌`。Windows 控制台是 GBK，直接跑可能 `UnicodeEncodeError` ——
先 `export PYTHONIOENCODING=utf-8` 再看退出码。

**要开 MuMu 才能跑的**（模拟器关着就跑不了，别当成失败）：`debug/screen_baseline.py check`
（认屏基线，几十例）、`python debug/*_probe.py`（存档帧语料回放）、上面那三个单测。

## 铁律

- **测试断言一个都不许改。** 只有 import 路径可以跟着搬家。**哪条断言需要改，就说明
  动了行为 —— 停下来报给用户，不许顺手改绿。**
- **不新增、不删除、不重命名任何 pipeline 节点。** 节点名**跨文件全局唯一**，
  重名 = 整个资源加载直接 abort（引擎不覆盖、不排序）。
- **不动 `assets/resource/image/` 一个字节。** `template` 按相对路径**精确解析**，
  挪一张 png 就认不出（与 pipeline 递归读文件不同）。
- **不动 `deps/`** —— 那是下载好的引擎成品（dll/exe/lib/schema），由 `tools/install.py`
  与 CI 管理。
- **不动任何判据参数**：`events.json` 的策略、`reasons.py` 里理由的文字、认屏表顺序、
  `strings.py` 的常量值、各屏的阈值常量。要改先去根 CLAUDE.md 查来历、再问用户。
- **脚本里不写游戏里的字**，一律走 `script/strings.py` 的常量（`g.click_node(离开地点)`）。
  改了名只改那一行，打错字 import 当场报。
- **不把 `Game` 继续加大** —— 新共性一律进 `shared/`（或 `ops/`）。
- **改动留在工作区不提交**，用户点名要提交时才提交。

## 约定与陷阱

- `assets/**/*.json` 实际按 **JSONC** 处理（`.vscode/settings.json` 把
  `**/assets/**/*.json` 映射成 `jsonc`），所以可以写 `//` 注释。缩进统一 **4 空格**。
- **Schema 是补全与校验的共同来源**：pipeline 对应 `deps/tools/pipeline.schema.json`，
  interface 对应 `deps/tools/interface.schema.json`。改字段时保持与 schema 一致。
- **OCR 模型不入库**：`assets/resource/model/ocr/` 被 `.gitignore` 忽略，靠
  `tools/configure.py` 或 CI 恢复。别提交它，也别以为丢了要重下。
- **`debug/` 整个被 `.gitignore` 忽略**（`install/` 也是）—— `debug/maafw.log` 是
  **唯一运行日志**，排查问题先看它。
- **`StartApp` 对已运行的进程只是切到前台**，不重启游戏 —— 所以 `next` 列表要同时
  覆盖"冷启动先到标题界面"和"热启动直接在主界面"两种起点，否则热启动会空等到超时、
  任务静默结束。
- **新增 pipeline 节点后 UI 上不会自动出现任务** —— 必须在 `assets/interface.json`
  的 `task[].entry` 里指向入口节点。
- **`Agent` 层本项目没有用**，脚手架已删（模板自带的 `agent/` 是死代码 —— 没有
  `"Custom"` 节点、`interface.json` 也没有 `agent` 字段，永远不会被拉起）。将来真要用，
  见根 CLAUDE.md 那节"Agent 层（原语扩展）"。

## 排查

1. **先看 `debug/maafw.log`**（唯一运行日志）与 `debug/screenshots/` 里那次停车的现场图。
2. 脚本"停下等人"时打的理由来自 `script/shared/reasons.py` —— 那里是"一共有哪些停车
   理由"的唯一答案。
3. 认不出界面 = 认屏表那一轮整表落空。**认屏表的真源是 `script/recognizer.py` 的
   `SCREENS`**（现 31 行），别信任何手抄的副本。
4. 只读侦察用 `debug/reco_image.py`（对一张存档帧跑指定节点的识别）—— 它不改游戏状态。

## 详细文档

- `docs/zh_cn/使用文档.md` —— **写给"跑脚本的人"**：怎么起、脚本自己会做哪些决定、
  什么时候会停、停了怎么办、想改哪条规则
- `docs/zh_cn/架构与流程图.md` —— **写给"改脚本的人"**：目录怎么分、每层能依赖谁、
  认屏表的落点、一局的流程图、屏模块 `handle()` 要守的四条契约（`ops/` 的 `run` 同款）
- `docs/zh_cn/develop/` —— 模板自带的开发 / FAQ / PR 规范
- 工作区根 `../CLAUDE.md` —— 玩法规则与判据来历（权威，且持续更新）
- `CHANGELOG.md` · `README.md`（模板自带）
