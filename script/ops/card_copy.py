"""卡牌操作小类 · **复制**：选卡屏上取一张（默认第一张，名单非空时按名单挑）。

副标题**读不到**、或者写着「复制」的那两副卷面都走这里（`nodes/cardpick.py`
的 `handle()` 分派）。用户 2026-10-02 定的原话就四个字：「默认第一张」；
2026-10-06 他又把带副标题那版并了过来（「如果触发了选卡, 默认选第一张」）。

**2026-10-15 加了第三条链（`script/cards/选择.json`）**：用户那天说「添加一个逻辑,
与升级, 升变, 移除同等级, 叫做选择.json, 用于出现卡牌选择页面时, 进行选择」，随后把
范围说定成「选择, 是用来管理向卡组添加卡牌的逻辑」—— **往卡组里加牌的那两屏**（这一屏
与 `ops/card_add.py` 的加入卡组屏）共用那一份名单。

  · **名单空着**（出厂就是这样）⇒ 走上面那条老路，**与加这份配置之前一字不差**。
  · **名单非空** ⇒ 挨格点开读卡名，挑出名单里的、选上（`shared/grid.py` 的 `wanted`）。
  · 名单非空、可屏上**一张都没出现** ⇒ 用户 2026-10-15 定的：「如果能跳过选择, 就跳过,
    不能就第一张」。**这一屏不能跳过**（副标题写死了「选择1张卡牌」——不是「可选择」）
    ⇒ 照默认取第一张，也就是**老路那一格**。

⚠️ **"能不能跳过"没有做成一个常量摆在这儿**：这一屏的答案恒为"不能"，上面那条
`if` 的另一半会是**永远不会走到的分支**。本工程对这种"常量定死之后恒假的日志分支"
是有先例的 —— `nodes/campfire.py` 的 `SKIP_ACTIVATE` 就是 2026-10-04 被用户点名削掉的
（「定在 False 之后……那句日志的分支恒假」）。所以这里就照实写成一个 `else`：**这一屏
不能跳过，就取第一张**。加卡组那一屏能跳过，写在 `ops/card_add.py` 里。

⚠️ 这一族里**只有复制**用"投影现算"找格子（`grid.cells()`），
移除那两版用的是写死的格位表（`grid.slots()`）—— 为什么分成两套，
见 `shared/grid.py` 里 `SLOT_FLAT` 上面那几段实测。
"""

from shared import grid
from shared.cards import CardsConfigError, load_rules
from shared.reasons import WAIT_CARD, WAIT_CARD_CONFIRM, WAIT_CARDS_CONFIG
from shared.kit import log, park


# 默认挑哪一格：**行 1 列 1 = 左上角那张**（grid.cells() 是按 行→列 排的，
# 所以它就是"第一张"）。用户 2026-10-02 定：「默认第一张」，2026-10-06 又把
# **带副标题那版复制屏**也并到这条路上（原话「如果触发了选卡, 默认选第一张」）。
# 要改成别的格子就把这行改掉；要按卡名挑见 `script/cards/选择.json`。
PICK = (1, 1)

# 这一屏最多能选几张 —— 副标题写死了「选择1张卡牌，复制2张加入牌组。」
#（没副标题那版同样是挑一张）。屏幕只让选 1 张，所以名单里就算命中好几张也只取第一张
#（用户 2026-10-15 定的：「能拿几张拿几张（上限屏允许的张数）」—— 这一屏的上限就是 1）。
LIMIT = 1


def run(g, image):
    """复制屏：选一张、点「确定」提交。

    **名单空着时 = 老路**（用户 2026-10-02「默认第一张」）：`PICK` 那一格。
    **名单非空时按名单挑**（2026-10-15 加的），挑不动就退回老路 —— 这一屏不能跳过，
    退路就是"第一张"（见模块 docstring）。
    """
    try:
        rules = load_rules()
    except CardsConfigError as exc:
        return park(g, WAIT_CARDS_CONFIG, "cards_config_broken",
            f"选卡（复制）：卡牌配置读不动（{exc}） —— 停下等人（已存 cards_config_broken.png）")

    cs = grid.cells(image)
    target = None
    # ---- 名单那一趟（只有名单非空才走；空名单 = 完全维持旧行为）----
    if rules.has_select:
        if not cs:
            return park(g, WAIT_CARD, "cardpick_select_nogrid",
                "选卡（复制）：「选择.json」的名单非空，可这一屏一格都没切出来"
                "（投影没切出格子） —— 停下等人（已存 cardpick_select_nogrid.png）")
        chosen, trouble = grid.wanted(g, cs, rules, LIMIT)
        if trouble:
            kind, text = trouble
            return park(g, WAIT_CARD, f"cardpick_select_{kind}",
                f"选卡（复制）：按「选择.json」挑牌时{text} —— 停下等人"
                f"（已存 cardpick_select_{kind}.png）")
        if chosen:
            # `wanted` 已经把这一格**选上了** —— 下面不再点它
            #（这一屏点一下＝选、再点一下＝取消，多那一下就是把它取消掉）。
            target = chosen[0][0]
            log(f"    选卡（复制）：按「选择.json」选 {grid.names(chosen)}")
        else:
            log("    选卡（复制）：名单里的牌屏上一张都没有 —— 这一屏不能跳过"
                "（副标题写死「选择1张」），照默认取第一张")

    if target is None:
        target = next((c for c in cs if (c["row"], c["col"]) == PICK), None)
        if target is None:
            g.snap("cardpick_nogrid")
            log(f"    选卡：读不出 {PICK[0]}-{PICK[1]} 这一格（本屏读出 {len(cs)} 格）")
            return grid.report(g)

        log(f"    选卡（复制）{len(cs)} 张，按默认取第 {target['row']}-{target['col']} 格")
        grid.pick(g, target)

    if not grid.confirm(g):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
            "选卡：卡选中了、但「确定」没点掉 —— 停下等人")

    log("    选卡：已提交")
    return ""
