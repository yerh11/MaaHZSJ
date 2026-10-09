"""战斗结算屏 —— **什么都不拿**，直接走。

用户 2026-10-01 明确：**战斗结束后不要选择任何奖励**。所以这里连
「获取战利品」「获取」都不点，只点右下角「离开地点」。

不拿奖励会弹一次确认框（「当前仍有未查看奖励，是否离开？」），
那是模态，交给 `Game.leave_confirm()` 按规则清掉。

「战斗胜利」和「逃离战斗」是**两屏、两套锚点**（认屏表里都算「战斗奖励屏」），
但处理完全一样 —— 实测精英战打到第 7 回合会转成逃跑结算，
认不出它就会空等到超时。
"""

from strings import 离开地点, 离开确认弹窗
from shared.reasons import (
    WAIT_LEAVE_REWARD,
    )
from shared.kit import log, park


def handle(g, hit):
    if not g.click_when(离开地点, guard=hit.matched):
        return park(g, WAIT_LEAVE_REWARD, "reward_stuck",
            "战斗结算：没找到「离开地点」 —— 停下等人（已存 reward_stuck.png）")

    log("    离开地点（不拿奖励）")
    # 弹窗可能浮出来、也可能不浮（勾过「本局不再提示」之后就不再弹）——
    # 这条两行套路六个屏各抄了一遍，收到 Game.leave_after() 里了
    g.leave_after()
    return ""
