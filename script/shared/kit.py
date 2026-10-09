"""跨屏复用的几个动作 —— 「其他块通用，作为 api 被调用」那块。

**这里只放真正重复的**。写这个文件的时候把候选逐个回去对过一遍，四条里
只有两条够格，另外两条**看着像、其实各干各的**，硬并会改语义（那是新 bug
的入口），所以留原地，来历写在各自的调用点上：

| 候选 | 实情 | 结论 |
|---|---|---|
| 停车留证 `snap + log + return` | 24 处逐行同构 | **并** → `park()` |
| 「离开地点」之后清确认弹窗 | 6 处同一个两行套路 | **并** → `Game.leave_after()`（它是原语，放 `core/auto.py`） |
| 「点一下再确认」4 处 | `campfire._confirm`（点确认键等它退场）/ `cardpick.confirm`（点确定等屏走）/ `fork._wait_rows`（**等 OCR 读出选项行**，根本不是点确认）/ `event._click_option`（**双击**同一格；「只单击」那档由事件集的 `tap` 指定）| **不并** —— 四个语义各不相同 |
| 战斗模态框 5 个方法 | 只有 `nightwatch_option` / `armor_option` / `last_chance` 三个真同构；`assimilate` 是"从右到左试一排"的循环 | **并那三个** → `Game._modal_click()`（放 `core/auto.py`） |

还有 `log()` —— 全脚本**唯一**的输出口（2026-10-08 加）。从前各处直接 `print`，
现在一律走它：一行一个 `[HH:MM:SS]` 前缀，日志按时间读得动。它只依赖标准库
`time`，不 import 任何项目模块（更不 import 屏模块 —— 环在 import 期就炸）。
原先这里有一条 `from shared.reasons import NEED_STRATEGY`，注释说是"方便
`from shared.kit import *`"——全仓库没有任何一处那么写，2026-10-04 删掉。
"""

import time


def log(msg):
    """打印一行带 `[HH:MM:SS]` 前缀的日志 —— 脚本里**所有**给人看的输出都走它。

    消息先 `strip()`：**前后空白一律去掉**（含历史写法里那套 2/4/6 格的缩进，
    以及 `"\\n[3] …"` 那种开头换行）。从前那套缩进是随手写的、深浅不一，打出来
    一列里 0/2/6 格混着；开头换行还会多打一行只有时间戳的空行 —— 2026-10-08
    用户报的「有多余的回车与空格」就是这两样。现在每行都是
    `[HH:MM:SS] 正文`，正文顶格。整条空白（strip 后为空）的直接不打印。
    """
    msg = msg.strip()
    if not msg:
        return
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


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
    """
    if snap:
        g.snap(snap)
    for line in lines:
        log(line)
    return reason
