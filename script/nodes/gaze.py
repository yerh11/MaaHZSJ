"""始源之凝视 —— 开局那屏赐福三选一。

**策略**（用户 2026-10-06 定，取代 2026-10-01 的「不拿、直接离开」）：

    三张赐福里**有「宝石收集者」就接受它**（那颗花 1 神智，2026-10-06 实测）；
    **没有就按右边那颗「刷新」换一批再看 —— 只按这一次**（用户 2026-10-06
    当天改的口径，取代早先那句「换到出为止」）。

    换出来了 → 认在哪一格就接受哪一格；换了一次还是没有、或者那颗点了**卡面
    没换**（次数用完）→ **一张都不拿、点「离开地点」**（照 2026-10-06 那条
    老规矩）。不猜"随便拿一张"，也不停在那儿等人。

    **只动右边那颗**：屏上左下并排两颗「刷新(N/M)」，右边那颗写 `刷新(0/1)`、
    左边那颗写 `刷新(0/3)`（底下还挂着一行小图标 +「60/13」，看着要花资源）。
    用户点名的是右边那颗，**左边那颗现在一下都不点** —— `刷新-左` 那个 pipeline
    节点还在（`debug/gaze.py` 那个手动量尺要用它），但生产脚本不碰，
    所以 `strings.py` 里那条常量跟着删掉了。

    **"换没换成"看的是卡面变没变**，不是"点没点到"：次数用完的按钮照样认得出、
    照样点得下去（`click_when` 会照实返回 True），只有卡面不动才算它没生效。
    这么写就不必知道屏上那个 `刷新(N/M)` 是按"已用"还是"剩余"记的 —— 那个没量过。

    「接受」之后**这一屏不会自己走**，还要「离开地点」才进第一层；不过拿过赐福
    之后「当前未获取始源祝福，是否离开？」那个确认框就不弹了，`Game.leave_after()`
    本来就把"弹 / 不弹"两种都兜住。

判据是**卡名**，不是卡面：卡面每局随机，只有名字说得清是哪一张。三张卡的名字
各有一个窄 roi 节点（`宝石收集者-左/中/右`，祭坛.json，只圈名字那一行）。
`赐福卡-左/中/右`（整张卡面、故意不写 expected）是给 `debug/gaze.py` 读牌用的，留着。
"""

import time

from strings import (
    始源之凝视,
    接受_左,
    接受_中,
    接受_右,
    赐福卡_左,
    赐福卡_中,
    赐福卡_右,
    宝石收集者_左,
    宝石收集者_中,
    宝石收集者_右,
    刷新_右,
    离开地点,
    )
from shared.reasons import (
    WAIT_GAZE_ACCEPT,
    WAIT_GAZE_REFRESH,
    WAIT_LEAVE_GAZE,
    )
from shared.kit import log, park

# 三格：卡名节点 → 那一格的「接受」按钮，位置一一对应（节点都在 祭坛.json）
SLOTS = (
    (宝石收集者_左, 接受_左),
    (宝石收集者_中, 接受_中),
    (宝石收集者_右, 接受_右),
    )

# 三格的**整张卡面**节点（读原文、没有 expected）—— 只用来判"卡面换没换"，
# 不参与挑卡（挑卡看的是上面那组窄 roi 的名字节点）。
FACE_NODES = (赐福卡_左, 赐福卡_中, 赐福卡_右)

WAIT_REFRESH = 2.5     # 按那颗刷新最多等多久 —— 它就在屏上，等不到＝真点不动
REFRESH_SETTLE = 2.0   # 换一批之后，等新卡面画出来再读
ACCEPT_SETTLE = 2.0    # 接受之后，等神智条和局面落定


def _wanted_slot(g, image):
    """这一帧上「宝石收集者」摆在哪一格；三格都没有返回 None。"""
    for name_node, accept_node in SLOTS:
        if g.see(name_node, image):
            return accept_node
    return None


def _card_faces(g, image=None):
    """三格的整张卡面读一遍（名字 + 效果 + 花费），拼成一个可比的东西。

    用它判「这一下刷新真生效了吗」—— **次数用完的按钮照样认得出、照样点得下去**，
    所以"点到了"不算数，唯一的现成证据是**卡面变没变**。
    这样就不必知道屏上那个 `刷新(N/M)` 是按"已用"还是"剩余"记的。
    """
    if image is None:
        image = g.capture()
    faces = []
    for node in FACE_NODES:
        reco = g.probe(node, image)
        items = []
        if reco and reco.hit:
            items = sorted((r for r in (reco.all_results or []) if r.text.strip()),
                           key=lambda r: (r.box[1] // 12, r.box[0]))
        faces.append("  ".join(r.text.strip() for r in items))
    return tuple(faces)


def _accept(g, hit, accept):
    """点上那一格的「接受」，再把这一屏走完。"""
    if not g.click_when(accept, guard=hit.matched):
        return park(g, WAIT_GAZE_ACCEPT, "gaze_accept_stuck",
            "「宝石收集者」认出来了，可它那一格的「接受」点不着 —— 停下等人（已存 gaze_accept_stuck.png）")
    log("    → 接受「宝石收集者」")
    time.sleep(ACCEPT_SETTLE)

    # 接受之后这一屏**多半还在**（要不要再点「离开地点」才进第一层没量过），
    # 所以看结果：屏已经走了就直接交回主循环，还在就点「离开地点」。
    if not g.see(始源之凝视):
        return ""

    if not g.click_when(离开地点, guard=hit.matched):
        return park(g, WAIT_LEAVE_GAZE, "gaze_stuck",
            "接受完「宝石收集者」，可「离开地点」点不着 —— 停下等人（已存 gaze_stuck.png）")

    log("    离开地点（已接受宝石收集者）")
    g.leave_after()
    return ""


def _leave_without(g, hit):
    """刷过一次、三张里还是没有「宝石收集者」——**一张都不拿**，点「离开地点」。

    用户 2026-10-06 定（那天上午刷新用完时定的规矩，下午改成"只刷一次"之后
    这条出口没变）。**一张都不拿时那个确认框会弹** ——「当前未获取始源祝福，
    是否离开？」—— 由 `leave_after()` 兜住（拿过赐福之后才不弹）。
    """
    if not g.click_when(离开地点, guard=hit.matched):
        return park(g, WAIT_LEAVE_GAZE, "gaze_leave_stuck",
            "刷过一次、三张里也没有「宝石收集者」，这一屏该走了，可「离开地点」点不着 —— 停下等人（已存 gaze_leave_stuck.png）")
    log("    离开地点（刷过一次、没有宝石收集者 —— 一张都不拿）")
    g.leave_after()
    return ""


def handle(g, hit):
    """在始源之凝视做一次决策并执行。

    **面板可能还在淡入**：先给那颗刷新钮一小段时间（等不到也继续 —— 真正动手的
    每一次 `click_when` 都带着 `guard=hit.matched`，"按钮和这一屏同在一帧上"由它兜住）。
    """
    g.wait_for([刷新_右], timeout=2.0)

    image = g.capture()
    accept = _wanted_slot(g, image)
    if accept is not None:
        return _accept(g, hit, accept)

    # 没有「宝石收集者」→ 按右边那颗「刷新」**一次**（用户 2026-10-06 定的口径）
    before = _card_faces(g, image)
    if not g.click_when(刷新_右, timeout=WAIT_REFRESH, guard=hit.matched):
        return park(g, WAIT_GAZE_REFRESH, "gaze_refresh_noclick",
            "三张里没有「宝石收集者」，该按右边那颗「刷新」了，可这一下没点出去（按钮找不着 / 这一屏已经不在） —— 停下等人（已存 gaze_refresh_noclick.png）")

    time.sleep(REFRESH_SETTLE)
    if _card_faces(g) == before:
        log("    刷新-右 点了、卡面没换 —— 当它没生效（次数用完）")
        return _leave_without(g, hit)

    log("    → 刷新-右（没有「宝石收集者」，换一批）")
    accept = _wanted_slot(g, g.capture())
    if accept is not None:
        return _accept(g, hit, accept)

    log("    换了一批，还是没有「宝石收集者」")
    return _leave_without(g, hit)
