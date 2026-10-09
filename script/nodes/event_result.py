"""事件**选完之后的结果屏** —— 正文讲这次选择造成了什么，底下只剩「赶紧离开」。

2026-10-01 事件「腐化白树」选了「你想要离开」之后第一次见到。

为什么单独一个模块：这一屏**左上角没有标题**，所以 nodes/event.py 认不出来
（它的 read_title 返回 None），会一路掉到通用「离开地点」——而这屏压根没有
「离开地点」，就空转到超时了。必须在这儿接住。

顺序：它在事件屏之后（认屏表里这么排的）—— 先让事件屏按标题认，
认不出的（就是本屏）掉到这儿。

**认屏和点击已经拆开**，同 card_reveal：表按节点认屏，这里现截现验地点、
点完等它退场。

**这一屏也是两段式**（2026-10-05 实撞 + 量准，从前只点一下，所以会卡住）：
和这一屏的别处一样，点「赶紧离开」那一行只是**把它点亮**，跟着浮出来的
「确认选择」才是真正交出去的那一下。现场帧 `debug/screenshots/event_result_stuck.png`
（12:03 那一停）上两样都在：那一行是高亮的、`确认选择` box **(637,398,81,24) score 1.0000**
—— 和 `amulet_pick.py` 里量到的**同一枚按钮、同一个位置**（那屏的 docstring 有对照表）。
所以走法照 `amulet_pick` 那套：点行 → 点「确认选择」→ 等它换屏。

⚠️ **「确认选择」是"浮出来才点"，不是"必点"**：这一屏 2026-10-03 有过**单击就走掉**的帧
（`debug/run_1003n.log`：「事件结果屏 → 赶紧离开」之后直接就是下一屏）。所以点完那一行
先给它一次自己走的机会，没走才去点「确认选择」—— 那一档不猜（`event_result_noconfirm`）。

进屏时「确认选择」**就已经浮着**（= 上一趟点过那一行、这一屏没走完，正是 12:03 停在
这里的那个状态）= 直接点它，**不重点那一行**（再点一下是**取消选中**，`amulet_pick.py`
2026-10-05 01:03 那停就停在这个状态上）。
"""

from strings import 赶紧离开, 确认选择
from shared.reasons import (
    WAIT_EVENT_RESULT,
    )
from shared.kit import log, park


def handle(g, hit):
    image = g.capture()
    # 已经选着（「确认选择」浮着）→ 把上一趟那一下兑现掉；没选着 → 先点那一行。
    if g.see(确认选择, image):
        log("    事件结果屏：进屏时「确认选择」就已经浮着 → 直接点它")
    else:
        log("    事件结果屏 → 赶紧离开")
        if not g.click_when(赶紧离开, guard=hit.matched):
            return park(g, WAIT_EVENT_RESULT, "event_result_stuck",
                "事件结果屏：「赶紧离开」点不到 —— 停下等人（已存 event_result_stuck.png）")

        # 第一下点完先给它一次**自己走**的机会（见模块开头那段：单击就走的帧有过）。
        # 3s 够 —— wait_gone 本身要求连续缺席 ≈0.9s，这一屏的过渡在 1~2s 上下。
        if g.wait_gone(赶紧离开, timeout=3.0):
            return ""

    # 走到这儿 = 还停在原地 ⇒ 第二段：「确认选择」浮出来了才点它。
    if not g.click_when(确认选择, timeout=5.0, guard=hit.matched):
        return park(g, WAIT_EVENT_RESULT, "event_result_noconfirm",
            "事件结果屏：那一行点下去了，可「确认选择」没浮出来 —— 停下等人（已存 event_result_noconfirm.png）")

    log("    → 确认选择")
    if not g.wait_gone(赶紧离开, timeout=8):
        return park(g, WAIT_EVENT_RESULT, "event_result_stuck",
            "事件结果屏：那一行＋「确认选择」都点了，可这一屏还挂着 —— 停下等人（已存 event_result_stuck.png）")
    return ""
