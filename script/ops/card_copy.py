"""卡牌操作小类 · **复制**：选卡屏上按默认取第一张。

副标题**读不到**、或者写着「复制」的那两副卷面都走这里（`nodes/cardpick.py`
的 `handle()` 分派）。用户 2026-10-02 定的原话就四个字：「默认第一张」；
2026-10-06 他又把带副标题那版并了过来（「如果触发了选卡, 默认选第一张」），
所以现在**与卡组里有什么牌无关**，也不读卡名。

⚠️ 这一族里**只有复制**用"投影现算"找格子（`grid.cells()`），
移除那两版用的是写死的格位表（`grid.slots()`）—— 为什么分成两套，
见 `shared/grid.py` 里 `SLOT_FLAT` 上面那几段实测。
"""

from shared import grid
from shared.reasons import WAIT_CARD_CONFIRM
from shared.kit import log, park


# 默认挑哪一格：**行 1 列 1 = 左上角那张**（grid.cells() 是按 行→列 排的，
# 所以它就是"第一张"）。用户 2026-10-02 定：「默认第一张」，2026-10-06 又把
# **带副标题那版复制屏**也并到这条路上（原话「如果触发了选卡, 默认选第一张」）。
# 要改成别的格子就把这行改掉；要按卡名挑见 `nodes/cardpick.py` 的模块 docstring。
PICK = (1, 1)


def run(g, image):
    """复制屏：按 `PICK` 选一张、点「确定」提交（用户 2026-10-02「默认第一张」）。

    这是**默认策略不是识别** —— 要改就改 `PICK` 那个常量（或换成 `nodes/cardpick.py` 模块 docstring
    里说的偏好表）。
    """
    cs = grid.cells(image)
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
