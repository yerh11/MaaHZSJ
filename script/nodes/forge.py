"""锻造使 —— 地图节点「献祭锻造间」进来看到的那一屏。

**策略（用户 2026-10-01 修订）：不分是否为第一次，每次都进去看一眼**
    点「形态升变」进「卡牌升变」→ 有没升变过的斧头就升，**能升几把升几把**
    （2026-10-02 用户定的：没有上限）→ 点「返回」→ 离开节点。

    最早写的是"全局只做一次"（做过就记一个标记、以后直接走人）。用户当天改掉了：
    **不分是否为第一次**，每次遇到都进去看一眼。所以这里**没有**任何
    "做过没做过"的状态文件——那个标记连同 already_done()/reset() 一起删了。

    之所以说"看一眼"而不是"做一轮"：多数时候**进去是没事干的**。
    实测第 4 层那次：升变图鉴「数量：13」，上一局升过的那两把斧头还在（卡面带
    蓝色「1」角标），网格里未升变的斧头 0 把，_upgrade() 当场就收工返回了。
    真有钱有料才升，没有就空手出来——两种情况走的是同一条路径。

其它地点各有各的文件，对照表见 assets/resource/pipeline/地点.json 的头部注释。

**顺序**：地点专属必须排在通用「离开地点」之前（认屏表里这么排的），
否则通用分支会抢先把它点掉。
"""

import time
from pathlib import Path
from strings import (
    升变确认,
    卡牌_无畏斧,
    卡牌升变界面,
    形态升变,
    离开地点,
    离开确认弹窗,
    返回,
    金币数量,
    锻造使界面,
    )
from shared.reasons import (
    WAIT_FORGE,
    )
from shared.kit import log, park

ROOT = Path(__file__).parent.parent.resolve()

# 一次最多升几把 —— **没有上限**（2026-10-02 用户改的：先问「最多升 UPGRADES = 2」，
# 随即定「没有上限」）。网格里还有未升变的斧头就一直升：升变一次那把卡就从土黄转橙、
# 模板不再匹配（见 _axes），所以"取最靠前的一把"天然往前走，不会原地打转。
# 金币不够 / 点了没反应时才停（那条出口见 _upgrade 里"金币没减"那一段）。
UPGRADES = None

# 一把"未升变的斧头"的最低匹配分。**必须与 锻造.json 里 `卡牌-无畏斧` 的 threshold 一致。**
# 实测：未选中的斧头 0.966~1.000，被点中高亮的那张掉到 0.531。
# 0.85 把两者分得很干净——而且筛掉高亮那张正是我们要的：
# 点过的牌卡面变亮，模板不再匹配它，"取最靠前的一把"天然跳过刚点过的。
AXE_MIN_SCORE = 0.85


# ---------- 流程 ----------

def _leave(g):
    """点「离开地点」走人（带二次确认的话一起点掉）。

    从前这里套着"连试 3 次、每次 sleep(1.0) 再重截一张"的重试环——那是给
    "复用了 g._img 缓存帧"打的补丁（子界面上根本没有「离开地点」，拿缓存图
    去找必然找不到，还一声不吭）。缓存已经拆了，click_when 自己每轮现截，
    这段重试就没有存在的理由了。失败就是真失败：停下，不猜。
    """
    if not g.click_when(离开地点, timeout=6.0):
        log("    锻造使：找不到「离开地点」")
        return False
    log("    锻造使：离开地点")
    # 弹窗可能浮出来、也可能不浮（勾过「本局不再提示」之后就不再弹）——
    # 这条两行套路六个屏各抄了一遍，收到 Game.leave_after() 里了
    g.leave_after()
    return True


def _axes(g, image):
    """网格里**未升变**的斧头，按自上而下、自左而右排。

    必须自己按分数筛：all_results 是**原始**结果，既不过 threshold 也不过滤
    expected（实测被选中高亮的那张只有 0.531，一样会返回）。直接拿它排序
    就会点到高分之外的东西。
    """
    reco = g.probe(卡牌_无畏斧, image)
    # probe() 可能返回 None（引擎没收下任务，多半是控制器掉线）——
    # 从前这里直接取 reco.all_results，会抛 AttributeError。补 None 闸。
    if reco is None:
        return []
    return sorted(
        (r for r in (reco.all_results or []) if r.score >= AXE_MIN_SCORE),
        key=lambda r: (r.box[1], r.box[0]),
    )


def _upgrade(g, limit=None):
    """在「卡牌升变」界面里，从最靠前的一把开始升。返回实际升成的把数。

    每次重新读一遍网格再取**最靠前**的一把，不按下标记号死点：升变后卡面
    从土黄变橙，模板就不再匹配它了，所以"取第一个"天然跳过已升过的。

    `limit=None` = **没有上限**（用户 2026-10-02 定的），一直升到网格里再没有
    未升变的斧头、或下面那两条出口为止。
    """
    done = 0
    while limit is None or done < limit:
        hits = _axes(g, g.capture())
        if not hits:
            log(f"    网格里再没有未升变的斧头了（已升 {done} 把），收工")
            break

        before = g.read_number(金币数量)
        g.click_box(hits[0].box)
        # 两段式：点卡只是选中，底部浮出的确认按钮才真扣钱。
        # 现截现验地等它浮出来（从前是 sleep(1.2) 蒙）
        #
        # **这一点落在哪儿**：那枚确认按钮上**没有文字**（只有锤子图标 + 「-6」，用户
        # 2026-10-02 又确认了一次：「升变(-6)位置是固定的」），所以 锻造.json 拿它上面
        # 那行提示「付出…」定位，再用 `target_offset` (10, 73) 落到按钮上 ——
        # 提示中心 (390,537) + (10,73) = **(400,610)**，正是实测的按钮中心。
        # auto.click_when 现在会照 offset 点（node_offset）—— 从前它点的是框中心
        # 也就是「付出」那行字本身，按钮纹丝不动，这条路上停了 9 次没升成一把。
        if not g.click_when(升变确认, timeout=4.0, guard=(卡牌升变界面,)):
            log(f"    第 {done + 1} 把没等到「升变确认」（金币不足？当前 {before}）")
            break

        # 光看按钮点了不算数——**等金币真的减下去**才算升成（点完到扣钱有动画）。
        # 减不动就是没升成（比如钱不够，点了没反应），不计进 done。
        deadline = time.monotonic() + 5.0
        after = g.read_number(金币数量)
        while (before is not None and after is not None and after >= before
               and time.monotonic() < deadline):
            time.sleep(0.4)
            after = g.read_number(金币数量)
        if before is not None and after is not None and after >= before:
            # **留一张现场图**：这条路 2026-10-02 之前 9 次全是这么停的
            # （金币 111/85/83/72/36/136 一动不动），而一张图都没留下 ——
            # 于是"点了确认却没扣钱"到底卡在哪一步，谁也说不清。
            # 用户那天报「当前锻造间,无畏斧升级没成功」，正是这条路。
            g.snap("forge_no_deduct")
            log(f"    第 {done + 1} 把点了确认但金币没减（{before} → {after}），当没升成，停下")
            break
        log(f"    → 升变第 {done + 1} 把斧头：金币 {before} → {after}")
        done += 1
    return done


def handle(g, hit):
    """在锻造使界面做一次决策并执行。

    真升成了几把，日志里 `_upgrade` 会报；**"这一轮没得升"不等于出错**——
    多数时候网格里本来就没有未升变的斧头。
    """
    # 1) 进「卡牌升变」子界面
    if not g.click_when(形态升变, guard=hit.matched):
        log("    没找到「形态升变」，直接离开")
        _leave(g)
        return ""
    if not g.wait_for([卡牌升变界面], timeout=8):
        # 进了子界面却认不出它 —— 这时候**别乱点**，停在这儿等人看一眼
        return park(g, WAIT_FORGE, "forge_stuck",
            "点了「形态升变」但没进到卡牌升变界面 —— 停下（已存 forge_stuck.png）")

    # 2) 升两把
    done = _upgrade(g, UPGRADES)

    # 3) 返回锻造使。现截现验：返回箭头在卡牌升变那一屏上，验到才点
    if not g.click_when(返回, timeout=5.0, guard=(卡牌升变界面,)):
        return park(g, WAIT_FORGE, "forge_stuck",
            "没找到返回箭头 —— 停下（已存 forge_stuck.png）")
    g.wait_for([锻造使界面], timeout=8)

    # 没升成（一把都没动，多半是网格里没有未升变的斧头、或金币不够）也照常离开：
    # 现在是"每次都进去看一眼"，下次遇到再来看一眼就是了，不需要记任何状态。
    if not done:
        log("    锻造使：这一轮没得升（网格里没有未升变的斧头，或金币不够）")

    _leave(g)
    return ""
