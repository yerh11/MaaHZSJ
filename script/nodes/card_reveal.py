"""新到手的卡牌展示屏 —— **唯一的出口**是底部那句「点击空白处继续」。

2026-10-01 事件「困兽或囚徒」选中「“询问他详情”」（一张特殊卡牌加入卡组）
之后第一次撞上：当时还不知道有这一屏，主循环认不出、连空转 10 轮就停车了。

它不是"选奖励"（用户要求战斗后不选奖励），只是把刚到手的那张卡给你看一眼，
点掉就行。

**认屏和点击已经拆开**：从前是"这句能点中，就说明是这一屏"（认屏即点击）——
那是拿认屏那帧去动手的老病。现在"是不是这屏"由认屏表的 `点击空白处继续`
回答，这里只管点：现截现验，点完等它真的退场再返回（一帧还在就再点第二下
是这个屏最容易踩的坑）。
"""

from strings import 点击空白处继续
from shared.reasons import (
    WAIT_CARD_REVEAL,
    )
from shared.kit import log, park


def handle(g, hit):
    if not g.click_when(点击空白处继续, guard=hit.matched):
        return park(g, WAIT_CARD_REVEAL, "card_reveal_stuck",
            "卡牌展示屏：「点击空白处继续」点不到 —— 停下等人（已存 card_reveal_stuck.png）")

    log("    卡牌展示屏 → 点击空白处继续")
    if not g.wait_gone(点击空白处继续, timeout=8):
        return park(g, WAIT_CARD_REVEAL, "card_reveal_stuck",
            "点过「点击空白处继续」，但这行字还在 —— 停下等人（已存 card_reveal_stuck.png）")
    return ""
