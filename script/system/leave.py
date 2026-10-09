"""**通用**地点界面 → 点「离开地点」走人。

走到这儿说明上面那些专属分支一个都没认出来 —— 这屏是个"没见过"的地点。
先存一张图再走：篝火就踩过这个坑，策略写好了却没接线，通用分支把「离开地点」
抢先点掉，**看着一切正常、实际策略从没执行过**。有图才有据可查。

**顺序**：这个模块必须排在**所有地点专属模块之后**（认屏表里这么排的）——
每个地点界面右下角都有「离开地点」，排在前面就会把专属策略的屏全部抢先点掉。
"""

from strings import 离开地点, 离开确认弹窗
from shared.reasons import (
    WAIT_LEAVE_GENERIC,
    )
from shared.kit import log, park


def handle(g, hit):
    g.snap("leave_generic")
    if not g.click_when(离开地点, guard=hit.matched):
        return park(g, WAIT_LEAVE_GENERIC, "leave_stuck",
            "通用离开：点不到「离开地点」 —— 停下等人（已存 leave_stuck.png）")

    log("    离开地点（通用分支）")
    # 点完等它走：第一次离开会浮出确认弹窗（勾过「本局不再提示」之后就不再弹），
    # 不等的直接后果是下一轮可能还认出这屏、把「离开地点」再点一次 ——
    # 公告页连点就是这个病
    # 弹窗可能浮出来、也可能不浮（勾过「本局不再提示」之后就不再弹）——
    # 这条两行套路六个屏各抄了一遍，收到 Game.leave_after() 里了
    g.leave_after()
    return ""
