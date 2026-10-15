"""卡牌操作小类 · **加入卡组**：默认一张都不拿；名单非空时按名单挑。

副标题「可选择最多2张卡牌加入卡组」（**2026-10-15 05:19** 事件「狭缝」→ 第 2 格
「“坠入”」→「确认选择」之后**第一次**撞上）。这是这一屏的第 6 个变体，也是
**半屏面板版**：面板只盖住右半边，左半边还看得见底下的「狭缝」事件屏
（和 2026-10-06 那块盖在篝火上的选卡面板同一种版式）。

⚠️ **「一张都不拿」这条默认走法，用户没定过** —— 全库日志里
`可选择最多2张卡牌加入卡组` 一共只出现过一次，就是撞上那一次
（`debug/run_1014_auto8.log:11619`，现场帧 `debug/screenshots/cardpick_unknown_effect.png`）。
它是**照同类屏推导出来的**：

  · 它的**形状**和另外两副「最多 N 张」屏一模一样 —— 都是**可选的、张数有上限**
    的多选屏：「选择**最多**3张卡牌，将其移除。」→ 用户 2026-10-04 定「可以不选择…
    就一张都不选」；「选择**最多**3张可升级卡牌，将其升级。」→ 同一批他定「**一张都不选**，
    直接「确定」」。两副都选了"不选"，这一屏是「最多2张」，同一形状。
  · 而且**动卡是不可逆的** —— 这一屏是往卡组里**加**牌。本工程对"没有规矩可依的不可逆
    动作"一贯是**不动手**：`shared/cards.py` 的 `MODE = 均不使用` 取的就是「谁也不动」
    那一侧，理由一模一样。

**2026-10-15 补上了真正的规矩**：用户那天说「添加一个逻辑, 与升级, 升变, 移除同等级,
叫做选择.json, 用于出现卡牌选择页面时, 进行选择」，范围说定成「选择, 是用来管理向卡组
添加卡牌的逻辑」—— 于是这一屏和复制屏（`ops/card_copy.py`）共用
`script/cards/选择.json`：

  · **名单空着**（出厂就是这样）⇒ 走上面那条"一张都不拿"的老路，**一字不差**。
  · **名单非空** ⇒ 挨格点开读卡名，挑出名单里的、选上（`shared/grid.py` 的 `wanted`）。
  · 名单非空、可屏上**一张都没出现** ⇒ 用户 2026-10-15 定的：「如果能跳过选择, 就跳过,
    不能就第一张」。**这一屏能跳过**（副标题写的是「**可**选择最多2张」）⇒ 一格都不点，
    直接「确定」—— 也就是那条老路。

⚠️ **"能不能跳过"没有做成一个常量摆在这儿**：这一屏的答案恒为"能"，上面那条 `if`
的另一半会是**永远不会走到的分支**（本工程对这种分支有先例：`nodes/campfire.py` 的
`SKIP_ACTIVATE` 2026-10-04 被用户点名削掉）。所以这里照实写成"名单不命中就什么都不做"。
"不能跳过"那一侧（退回第一张）在 `ops/card_copy.py` 里。

⚠️ **名单非空那一整条路，实机上一次都没走过**（这一屏连格位都没量过）。所以在那条路上
**每一步读不出来就停车**，第一次真撞上时拿现场帧量准 —— 本工程一贯的节奏。
格位走 `grid.cells(image)`（**投影现算**，不是写死的 `SLOT_X/SLOT_Y` 表）：切不出来就是
`cardpick_select_nogrid` 停车，**不照图推**（现场帧上它看着就是标准 5 列那套格心
692/809/926/1043/1160、行心 221/387，但那是**看**出来的，不是量的）。
"""

from strings import 选卡确定, 选择卡牌
from shared import grid
from shared.cards import CardsConfigError, load_rules
from shared.reasons import WAIT_CARD, WAIT_CARD_CONFIRM, WAIT_CARDS_CONFIG
from shared.kit import log, park


# 这一屏最多能拿几张 —— 副标题写的是「可选择最多2张卡牌加入卡组」。
# 名单里命中超过 2 张时按读到的先后取前 2 张（用户 2026-10-15 定的
# 「能拿几张拿几张（上限屏允许的张数）」—— 这一屏的上限就是 2）。
LIMIT = 2


def run(g):
    """加入卡组屏：按名单挑（名单空着就是**一张都不选，直接「确定」**）。

    名单空着时**一格都不读、也不点** —— 这一趟根本不用格子（理由见模块开头）。
    名单非空时才去读格位（**十几秒**：每格 2 次点击 + 每次 1.1s）。

    点不掉、或者点了这屏不走，**不猜、不补第二下，停车等人**；两个出口各存各的图，
    事后一眼看得出是哪一件。
    """
    try:
        rules = load_rules()
    except CardsConfigError as exc:
        return park(g, WAIT_CARDS_CONFIG, "cards_config_broken",
            f"选卡（加入卡组）：卡牌配置读不动（{exc}） —— 停下等人（已存 cards_config_broken.png）")

    # ---- 名单那一趟（只有名单非空才走；空名单 = 完全维持旧行为）----
    chosen = []
    if rules.has_select:
        cs = grid.cells(g.capture())
        if not cs:
            return park(g, WAIT_CARD, "cardpick_select_nogrid",
                "选卡（加入卡组）：「选择.json」的名单非空，可这一屏一格都没切出来"
                "（投影没切出格子） —— 停下等人（已存 cardpick_select_nogrid.png）")
        chosen, trouble = grid.wanted(g, cs, rules, LIMIT)
        if trouble:
            kind, text = trouble
            return park(g, WAIT_CARD, f"cardpick_select_{kind}",
                f"选卡（加入卡组）：按「选择.json」挑牌时{text} —— 停下等人"
                f"（已存 cardpick_select_{kind}.png）")
        if chosen:
            log(f"    选卡（加入卡组）：按「选择.json」选了 {len(chosen)} 张（{grid.names(chosen)}）")
        else:
            log("    选卡（加入卡组）：名单里的牌屏上一张都没有 —— 这一屏能跳过，"
                "一张都不选，直接点「确定」")
    else:
        log("    选卡（加入卡组）：一张都不选，直接点「确定」")

    if not g.click_when(选卡确定, guard=(选择卡牌,)):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_add_noconfirm",
            "选卡（加入卡组）：「确定」没找到/点不掉 —— 停下等人（已存 cardpick_add_noconfirm.png）")
    if not g.wait_gone(选择卡牌, timeout=8):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_add_stuck",
            "选卡（加入卡组）：点了「确定」这屏还在 —— 停下等人（已存 cardpick_add_stuck.png）")
    if chosen:
        log(f"    选卡（加入卡组）：已提交（拿了 {len(chosen)} 张：{grid.names(chosen)}）")
    else:
        log("    选卡（加入卡组）：已提交（这一趟一张都没拿）")
    return ""
