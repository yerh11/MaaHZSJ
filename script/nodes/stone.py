"""怪石造物 —— 地图节点「印记石」进来看到的那一屏。

**当前策略：不碰「将手放入凹槽」，直接点「离开地点」**（用户 2026-10-01 确认）。

那个选项是干什么的还不清楚，所以：
    * pipeline 里 `将手放入凹槽` 的 action 故意留成 DoNothing；
    * 本模块也不去点它。

其它地点各有各的文件：地图节点名 ≠ 屏名，对照表见
assets/resource/pipeline/地点.json 的头部注释。

**顺序**：地点专属必须排在通用「离开地点」之前（认屏表里这么排的），
否则通用分支会抢先把它点掉。
"""

from strings import 离开地点, 离开确认弹窗
from shared.reasons import (
    WAIT_LEAVE_STONE,
    )
from shared.kit import log, park


def handle(g, hit):
    """点「离开地点」走人。"""
    if not g.click_when(离开地点, guard=hit.matched):
        # 认得出这一屏、却找不到唯一的出口 —— 停，别硬点别的（更别碰凹槽）
        return park(g, WAIT_LEAVE_STONE, "stone_stuck",
            "怪石造物：找不到「离开地点」 —— 停下等人（已存 stone_stuck.png）")

    log("    怪石造物：离开地点（不碰凹槽）")
    # 离开可能要过一道确认框，也可能不要——认到才点，别硬点
    # 弹窗可能浮出来、也可能不浮（勾过「本局不再提示」之后就不再弹）——
    # 这条两行套路六个屏各抄了一遍，收到 Game.leave_after() 里了
    g.leave_after()
    return ""
