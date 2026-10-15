"""跨屏复用的几个动作 —— 「其他块通用，作为 api 被调用」那块。

**这里只放真正重复的**。写这个文件的时候把候选逐个回去对过一遍，四条里
只有两条够格，另外两条**看着像、其实各干各的**，硬并会改语义（那是新 bug
的入口），所以留原地，来历写在各自的调用点上：

| 候选 | 实情 | 结论 |
|---|---|---|
| 停车留证 `snap + log + return` | 24 处逐行同构 | **并** → `park()` |
| 「离开地点」之后清确认弹窗 | 6 处同一个两行套路 | **并** → `Game.leave_after()`（它是原语，放 `core/auto.py`） |
| 「点一下再确认」4 处 | `campfire._confirm`（点确认键等它退场）/ `grid.confirm`（点确定等屏走）/ `fork._wait_rows`（**等 OCR 读出选项行**，根本不是点确认）/ `event._click_option`（**双击**同一格；「只单击」那档由事件集的 `tap` 指定）| **不并** —— 四个语义各不相同 |
| 战斗模态框 5 个方法 | 只有 `nightwatch_option` / `armor_option` / `last_chance` 三个真同构；`assimilate` 是"从右到左试一排"的循环 | **并那三个** → `Game._modal_click()`（放 `core/auto.py`） |

还有 `log()` —— 全脚本**唯一**的输出口（2026-10-08 加）。从前各处直接 `print`，
现在一律走它：一行一个 `[HH:MM:SS]` 前缀，日志按时间读得动。它只依赖标准库
`time`，不 import 任何项目模块（更不 import 屏模块 —— 环在 import 期就炸）。
原先这里有一条 `from shared.reasons import NEED_STRATEGY`，注释说是"方便
`from shared.kit import *`"——全仓库没有任何一处那么写，2026-10-04 删掉。

**2026-10-15 加：停车记录文件（`report()`）。** 用户那天说「为停下等人逻辑,
专门编写一个文件, 记录当前环境与截图等」—— 从前一次停车只落两样东西：现场图
（`Game.snap()`）和滚屏里的几行日志；**脚本自己不写任何日志文件**（`README.md`
里那条 `> debug/run_*.log` 是人在 shell 里做的重定向）。于是事后回看一次停车，
要同时对着现场图、终端日志（多半已经滚出去了）、外加"这一屏是哪一屏"得靠人
看图认。现在每次停车多落一份 `debug/parks/<名字>.md`：**名字跟现场图同名**
（用户当天选的形态 —— 看到日志里的 `snap` 名就知道去哪儿找），内容是当时那一
刻的自拍照：理由、现场图、停在哪一屏、命中了哪些节点、屏上证据、第几步、
分辨率、环境、启动时刻，外加最近 30 行日志。

记录**由 `battle.py` 的停车点写**（用户当天选的：`park()` 那 95 处调用点一个
都不动）—— 只有那里 `hit` 在手边，写得出"停在哪一屏"。所以本模块只提供
`report()` 这个口子，以及它要用的三样东西：`snapshot()`（最近一次 `park()` 存的
现场图名）、`recent()`（日志尾巴）、加上 `log()` 本身顺手记的那一圈缓冲。

⚠️ **`report()` 永不抛异常**：记录写不动绝不能把停车理由本身吞掉（那才是要看的
东西）—— 整段包 `try/except`，失败只多打一行日志。
"""

import os
import platform
import sys
import time
from collections import deque
from pathlib import Path

# 停车记录的落点：`<仓库根>/debug/parks/`。
#
# ⚠️ **不能写成 `from core.auto import ROOT`** —— `core/auto.py` 反过来
# `from shared.kit import log`，那边才是上家，这么写 import 期就成环。
# 所以路径自己算：`script/shared/kit.py` → `script/` → `MaaHZSJ/`。
# 它和 `core/auto.py` 的 `SHOT`（`debug/screenshots/`）是**同一个 `debug/` 下的
# 两个目录** —— 哪天改 `debug/` 的布局，**这两处要一起改**，机器管不着。
PARKS = Path(__file__).resolve().parent.parent.parent / "debug" / "parks"

# 记录里那份"日志尾巴"留多少行
RECENT_LINES = 30

# ---- 三样模块状态：给停车记录当料 ----

# 最近的日志行（`log()` 顺手记）。**环形**：只留最后 `RECENT_LINES` 行。
_recent = deque(maxlen=RECENT_LINES)

# 脚本起跑的时刻（记录里写"已跑多久"）。**用 time.time() 不用 monotonic** ——
# 记录是给人看的，要和日志里的 `[HH:MM:SS]` 对得上。
_started = time.time()

# `park()` 最近一次存的现场图名（`battle.py` 拿它当记录的文件名）。
# `park(g, …, snap=None)` 时**会被清成 None** —— 那一次确实没图，别拿上一张顶包。
_last_snap = None


def log(msg):
    """打印一行带 `[HH:MM:SS]` 前缀的日志 —— 脚本里**所有**给人看的输出都走它。

    消息先 `strip()`：**前后空白一律去掉**（含历史写法里那套 2/4/6 格的缩进，
    以及 `"\\n[3] …"` 那种开头换行）。从前那套缩进是随手写的、深浅不一，打出来
    一列里 0/2/6 格混着；开头换行还会多打一行只有时间戳的空行 —— 2026-10-08
    用户报的「有多余的回车与空格」就是这两样。现在每行都是
    `[HH:MM:SS] 正文`，正文顶格。整条空白（strip 后为空）的直接不打印。

    顺手把这一行塞进 `_recent`（环形，只留最后 `RECENT_LINES` 行）——
    停车记录的那份"日志尾巴"就是它，**不用去读 stdout**（那是重定向的活儿，
    脚本自己看不见）。
    """
    msg = msg.strip()
    if not msg:
        return
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    _recent.append(line)
    print(line)


def park(g, reason, snap=None, *lines):
    """停下等人：存现场图 → 打印现场描述 → 把理由原样交回去。

    调用点原来长这样（三行）：

        g.snap("arcade_stuck")
        log("    结果面板在，但「拒绝并触发战斗」没认出来 —— 不猜，停下等人"
            "（已存 arcade_stuck.png）")
        return "等待游艺"

    现在：

        return park(g, WAIT_ARCADE, "arcade_stuck",
                    "    结果面板在，但「拒绝并触发战斗」没认出来 —— 不猜，停下等人"
                    "（已存 arcade_stuck.png）")

    `snap=None` = **这条路径不存图**（本来就有的选择，比如 `forge._leave`
    打了日志就返回；还有 `cardpick.handle` 那条"接着 python debug/cards.py …"
    的提示路径）。

    `reason` 一律传 `shared.reasons` 里的常量：**理由本身一个字都不改**
    （`debug/_reason_dump.py` 迁移前后要逐行相同），这里只是不再让每个
    调用点自己抄一遍字符串。

    `lines` 走 `log()` —— 和别处一样带 `[HH:MM:SS]` 时间戳。

    顺手记下这次存的图名（`_last_snap`），`battle.py` 的 `report()` 拿它当
    记录的文件名 —— **跟现场图同名**，这是用户 2026-10-15 选的形态。
    """
    global _last_snap
    _last_snap = snap
    if snap:
        g.snap(snap)
    for line in lines:
        log(line)
    return reason


def snapshot():
    """`park()` 最近一次存的现场图名（没存过就是 None）。

    给 `battle.py` 的停车记录当文件名用。**只有 `park()` 写它** ——
    `battle.py` 自己那几记 `g.snap(...)`（`battle_unknown_<时刻>` /
    `battle_end` / `loop_notmain` / `battle_norun`）由调用点**显式传名字**进去，
    因为 `battle_end` 是每轮都存、会互相覆盖的，当文件名没意义。
    """
    return _last_snap


def recent(n=RECENT_LINES):
    """最近 `n` 行日志（`log()` 记下的那一圈）。停车记录用它当"日志尾巴"。"""
    if n is None or n >= len(_recent):
        return list(_recent)
    return list(_recent)[-n:]


# ---------------- 停车记录文件 ----------------


def report(g, reason, snapshot=None, screen=None, matched=(), evidence=None, steps=None):
    """把这一次停车写成 `debug/parks/<名字>.md`。返回路径；写不动返回 None。

    **文件名跟现场图同名**（用户 2026-10-15 定：「每次停车一份，跟现场图同名」）：
    这次存了图就是 `<现场图名>.md`（`cardpick_add_noconfirm.md`），**和现场图
    一样会被下一次同名停车覆盖**；这次没存图（只有 `达到步数上限` 那一条）就
    用理由当名字（中文文件名 —— 本工程已有先例，现场图里就有
    `event_park_真龙现身_noclick.png`）。

    ⚠️ **永不抛异常**：记录写不动绝不能把停车理由本身吞掉（那才是要看的
    东西）—— 整段包 `try/except`，失败只多打一行日志，停车照旧。

    `screen` / `matched` / `evidence` 只有 `battle.py` 的 `play()` 那条路给得出
    （`hit` 在手边）；`battle.py` 自己那几处（未知界面 / 步数上限 / 收尾没回主界面…）
    **本来就没认出来**，传 None 就是"没认出来"，别去补一次识别（那是三四秒）。
    `evidence` **只印出来看** —— `recognizer.py` 顶上写着它"只给日志和 describe
    用，handler 不许拿它做动作"，记录是日志的延伸，不违反这一条。
    """
    try:
        os.makedirs(PARKS, exist_ok=True)
        path = PARKS / f"{snapshot or reason}.md"
        with open(path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(_render(g, reason, snapshot, screen, matched, evidence, steps))
        return path
    except Exception as exc:                      # noqa: BLE001 —— 见 docstring
        log(f"  ! 停车记录写不动（{exc}）—— 现场图与日志照旧")
        return None


def _render(g, reason, snap, screen, matched, evidence, steps):
    """记录正文。纯拼字符串，不碰磁盘 —— 写盘那件事在 `report()` 里。"""
    out = [f"# 停下等人 · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    out.append(f"- **理由**：{reason}")
    out.append(f"- **现场图**：debug/screenshots/{snap}.png" if snap
               else "- **现场图**：（这一次没存）")
    out.append(f"- **停在哪一屏**：{screen or '（没认出来）'}")
    out.append(f"- **命中的节点**：{'、'.join(matched) if matched else '（没有）'}")
    out.append(f"- **屏上证据**：{_evidence(evidence)}")
    if steps is not None:
        out.append(f"- **第几步**：{steps}")
    out.append(f"- **分辨率**：{_resolution(g)}")
    out.append(f"- **环境**：{platform.platform()} · Python {sys.version.split()[0]}"
               f" · PID {os.getpid()}")
    out.append(f"- **脚本启动**：{time.strftime('%H:%M:%S', time.localtime(_started))}"
               f"（{_elapsed()}）")
    out.append("")
    out.append(f"## 最近 {len(recent())} 行日志")
    out.append("")
    out.append("```")
    out.extend(recent())
    out.append("```")
    out.append("")
    return "\n".join(out)


def _evidence(evidence):
    """证据 dict 印成一行（`标题=困兽或囚徒、options=[…]`）。空/没有就是"（没有）"。"""
    if not evidence:
        return "（没有）"
    return "、".join(f"{k}={v}" for k, v in evidence.items())


def _resolution(g):
    """分辨率。取 `Game` 连上时存下的那一帧尺寸（`core/auto.py` 的 `_frame_shape`）。

    **不额外截图** —— 记录是在停车那一刻写的，`capture()` 又要 0.01s、还要
    在对的时机，不值得；那帧尺寸连接时就定了，一次都不变。
    FakeGame 上没有这个字段（单测用）⇒ 「（未知）」，不是错误。
    """
    shape = getattr(g, "_frame_shape", None)
    if not shape or len(shape) < 2:
        return "（未知）"
    return f"{shape[1]}x{shape[0]}"


def _elapsed():
    """脚本起跑到现在的时长，印成「2 小时 11 分」/「37 分」/「12 秒」。"""
    secs = int(time.time() - _started)
    if secs >= 3600:
        return f"已跑 {secs // 3600} 小时 {secs % 3600 // 60} 分"
    if secs >= 60:
        return f"已跑 {secs // 60} 分"
    return f"已跑 {secs} 秒"
