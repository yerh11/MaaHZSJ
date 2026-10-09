"""护符选择界面：**按固定顺序逐个点过去**，挑一个激活。

用户 2026-10-01 定的规则：
    我希望顺序是1,2,3,4,5

候选是 5 个**黑菱形框**，围着中央圆盘摆成下半圈的一道弧，游戏自己在框上印了号 1~5
（逆时针：1 左上、2 左下、3 正下、4 右下、5 右上）。**表的顺序就是号**：
`shared/coords.py` 的 `AMULET_CANDIDATES` 从前每格还带一个护符真名，2026-10-08 用户说
「不再有名称, 按照顺序进行选择」「因为护符可能会改变,同时当前护符名称好像也没有用到」，
名字于是删掉、只剩 5 个位置，**下标 + 1 就是印的号**。（位置与号的对应 2026-10-01
放大截图核过，判据图见 debug/_slot_digits.py。）

怎么知道哪个"能选"：**只有装着待激活护符的那个框有反应**，其余四个点了什么都不发生、
连详情面板都不弹。所以判据就是"面板出没出来"，策略是"按顺序一个个点过去，谁弹出
面板就是谁"。**别改用模板匹配挑**：地点.json 里 `护符-冲锋纹印` 的模板实测已经配不上
了 —— **图案**会变（平时只有待激活那个框画图案，另外四个是空菱形加号），位置反而一直稳。

这一屏是**两段式**：点候选只是选中，还得再点面板里的「激活」才真扣魂晶、装上护符。
本模块只点这两下，别的一概不碰。
"""

import time
from strings import 护符选择界面, 激活护符确认
from shared.reasons import (
    WAIT_AMULET,
    )
from shared.kit import log, park
# 5 个候选框的**固定位置**住在 `shared/coords.py`，**表序就是框上印的号**（见模块头）。
from shared.coords import AMULET_CANDIDATES as CANDIDATES


SETTLE = 1.3          # 点一下候选后，最多等详情面板这么久（空框就不会弹）
AFTER_ACTIVATE = 5.0  # 点「激活」后，最多等这一屏散掉这么久


def _find_activate(g, image=None):
    """找那个**恰好写着「激活」**的按钮，返回它的框；没有就返回 None。

    两件不能偷懒的事：

    1. **不能用固定 roi**。详情面板会**跟着选中的候选飘**——选第 5 个（右上）时
       它贴在右上方，「激活」实测在 (752,460)；选第 3 个（正下）时面板落到左下，
       「激活」跑到 (665,660)。写死哪一处都会错一半。

    2. **不能只靠 expected**。那是**子串**匹配，标题「激活一个护符」和右下角
       「激活XXX护符」提示都含「激活」二字，会撞上。所以这里拿 all_results
       自己按**完全相等**筛。

    顺带一个好处：这个按钮在不在，就是"面板弹出来了没"的判据，
    而"面板弹没弹"又等于"这个候选能不能选"——一个判据办两件事。
    """
    reco = g.probe(激活护符确认, image)
    for r in (reco.all_results or []) if reco else []:
        if r.text.strip() == "激活":
            return tuple(r.box)
    return None


def _wait_activate(g, timeout=SETTLE):
    """等详情面板弹出来，返回里面那个「激活」按钮的框；等不到返回 None。

    判据就是 _find_activate（恰好写着「激活」的那个按钮）——"面板弹没弹"
    和"这个候选能不能选"本来就是同一件事。空框点了什么都不发生，
    等满 timeout 就跳下一个（从前是死睡 SETTLE，不管面板来没来）。
    """
    deadline = time.monotonic() + timeout
    while True:
        box = _find_activate(g)
        if box is not None:
            return box
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.3)


def handle(g, hit):
    """挑一个候选激活。装上哪个，日志里写着；装不上就停下等人。

    **按表序（= 框上印的号 1→2→3→4→5）扫**（用户 2026-10-01 的规则），遇到第一个
    能选的（点了会弹面板的）就装上。空框点一下毫无反应，直接跳过。
    """
    log(f"    按框上印的号 1→{len(CANDIDATES)} 逐个试：")

    for i, (x, y) in enumerate(CANDIDATES, 1):
        g.click(x, y)
        box = _wait_activate(g, SETTLE)
        if box is None:
            log(f"    第 {i} 个：空框（点了没弹面板），跳下一个")
            continue

        log(f"    第 {i} 个：弹出详情面板 → 点「激活」")
        g.click_box(box)
        if g.wait_gone(护符选择界面, timeout=AFTER_ACTIVATE):
            log(f"    第 {i} 个已激活")
            return ""

        # 屏还在：**不一定是失败**。2026-10-01 点 4 号框时，屏没散是因为
        # 上面盖了一层替换确认框（「同一槽位只能存在一个护符 / XX 将被替换为
        # YY，是否确认？」），标题「激活一个护符」还在底下亮着。
        # **那个框的 是/否 怎么选用户还没定**，所以不代它做决定，停下。
        g.snap("amulet_stuck")
        log("    点了「激活」，「激活一个护符」这一屏还在")
        return WAIT_AMULET

    return park(g, WAIT_AMULET, "amulet_stuck",
                f"{len(CANDIDATES)} 个候选挨个点过来，没一个弹出面板 —— 停下等人（已存 amulet_stuck.png）")
