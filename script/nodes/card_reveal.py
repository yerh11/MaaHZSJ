"""新到手的卡牌展示屏 —— **唯一的出口**是底部那句「点击空白处继续」。

2026-10-01 事件「困兽或囚徒」选中「“询问他详情”」（一张特殊卡牌加入卡组）
之后第一次撞上：当时还不知道有这一屏，主循环认不出、连空转 10 轮就停车了。

它不是"选奖励"（用户要求战斗后不选奖励），只是把刚到手的那张卡给你看一眼，
点掉就行。

**认屏和点击已经拆开**：从前是"这句能点中，就说明是这一屏"（认屏即点击）——
那是拿认屏那帧去动手的老病。现在"是不是这屏"由认屏表的 `点击空白处继续`
回答，这里只管点：现截现验，点完等它真的退场再返回（一帧还在就再点第二下
是这个屏最容易踩的坑）。

**点的是"空白"，不是那行提示自己的框**（2026-10-14 改）。提示写的就是"点击空白处"，
而卡面面板的高度**随卡变**（有没有底下那块风味文字、描述几行）—— 从前按提示框
上移 30px 找"卡片下缘与提示之间那条空带"，那条空带**不总有**：当天停在
「翁法洛斯石+」上，那块风味文字底板（「消耗品 / 椭圆状的石头…」）一直铺到 y=668，
落点 (639,651) 掉进面板里，游戏不理（同一记落点在 00:24 那次还能用 —— 那张牌
面板矮，651 还是空白）。面板是**居中**的、横向范围由卡面宽度定死（换卡只变高矮），
所以取面板**外**的固定空白，见 `shared/coords.INFO_BOX_TAP`。
"""

from strings import 点击空白处继续
from shared.coords import INFO_BOX_TAP
from shared.reasons import (
    WAIT_CARD_REVEAL,
    )
from shared.kit import log, park


def handle(g, hit):
    if not g.click_at(INFO_BOX_TAP, guard=hit.matched):
        return park(g, WAIT_CARD_REVEAL, "card_reveal_stuck",
            "卡牌展示屏：这一屏的标志物没认住，或那一下空白没发出去 —— 停下等人（已存 card_reveal_stuck.png）")

    log(f"    卡牌展示屏 → 点空白收掉（{INFO_BOX_TAP[0]},{INFO_BOX_TAP[1]}）")
    if not g.wait_gone(点击空白处继续, timeout=8):
        return park(g, WAIT_CARD_REVEAL, "card_reveal_stuck",
            "点过空白，但这行字还在 —— 停下等人（已存 card_reveal_stuck.png）")
    return ""
