"""商店（地图节点「商店」）—— 用「移除卡牌」把保留名单之外的卡清掉。

屏幕上是「神秘商人」的立绘，左侧两个选项「购买卡牌」「移除卡牌」，右下角照例
「离开地点」，底栏中部是「金币」。那两个选项在 `assets/resource/pipeline/地点.json`
里认得出（action 是 DoNothing）。

**策略**（用户 2026-10-04 的话）：

    「点击"移除卡牌" 移除"隐痛\\无畏斧\\莽撞头槌"之外的卡牌
      (金币不足时或没有可移除时离开)」

这条接的是 2026-10-03 那句「如果遇到商店, 就将非指定卡(无畏斧 / 莽撞头槌 / 隐痛)外
全部移除,(**在下一个商店停下**,然后再来补充逻辑)」——"在下一个商店停下"那一步
（`shop_park.png` 那次）已经在 2026-10-04 了了，这是补上的逻辑。

**保留名单不在这份文件里**：名字那份是 `shared/cards.py` 的 `KEEP`，卡面那份是同一个
文件的 `KEEP_TEMPLATES`（两个入口共用，一个字都不用抄第二遍）。本模块只管两件事：
**点「移除卡牌」**、**什么时候该走**。

---- 两个出口怎么判（都不需要知道"移一张花多少钱"）----

这一屏"移成一张"和"一张都没移成"**长得一模一样**——都是又站回这一屏。所以出口不能
靠"看起来变了没有"判，只能靠**上一趟销毁卡牌屏自己报的结果**（那两格旗住在
`shared/gridstate.py`，跨屏状态的来历也写在那儿）：

| 上一趟销毁卡牌屏 | 商店这边 | 走哪个出口 |
|---|---|---|
| 移成了一张（`True`） | 接着点「移除卡牌」 | —— |
| **没有可销毁的了**（`False`） | 点「离开地点」 | 用户说的「**没有可移除时**离开」 |
| **压根没跑过**（`None`）而我上一轮点过「移除卡牌」 | 先等一会儿看面板上没上屏；等不到才点「离开地点」 | 用户说的「**金币不足时**离开」 |

第三行是**这一屏自己**认得出来的：「点了「移除卡牌」却根本没进销毁卡牌屏」= 那一下
没生效。金币不够时按钮多半就是点不动（`click_when` 等不到它退场），**这一屏上
看不到任何别的提示**，所以只能这么判。也因此**移一张花多少钱、花不花金币，
这里一概不用知道** —— 金币那笔账是销毁卡牌屏自己算的（屏上写着价钱，见
`nodes/deck.py`），它算下来"买不起"就直接退回来走第二行。

那个"等一会儿"（`wait_for(你的卡组)`）是 2026-10-04 加的：**点完「移除卡牌」到面板
画出来之间隔着一两帧**，那两帧里先认出来的还是商店屏，不问一句就会把"面板正在淡入"
当成"没进去"、白白跳过这家商店的清理。

每次进门还会打一行当前金币，"移一张掉多少金币"下次从日志里就能读出来。

---- 点完「移除卡牌」之后那一屏 ----

**已经量到了**：`debug/screenshots/play_not_here.png` / `_deck_after_select.png`
——是**销毁卡牌屏**（标题「你的卡组」），走法在 `nodes/deck.py`，认屏表里它排在
这一屏**前面**（面板盖在商店屏的右半边，左边那半屏还是这一屏 —— 顺序按"先判盖在上面
那张"钉着；今天实测两帧面板上这一屏的锚点都读不出来，所以两屏**并不同时命中**，
那条顺序是保险）。从前这里挂着一句"没验证过的前提"（"点下去可能是 `cardpick` 那张
卡组屏"），2026-10-04 面板本身量清楚之后就删了。
"""

from strings import 移除卡牌, 离开地点, 金币数量, 你的卡组
from shared import gridstate
from shared.reasons import WAIT_SHOP
from shared.kit import log, park

# 点「移除卡牌」的等待上限。跟地点屏其它选项一个量级（篝火的 WAIT_ACTIVATE = 4.0）。
# 也用来等面板上屏（`wait_for`）—— 面板实测是点完就淡入，取同一个量级够用。
WAIT_REMOVE = 4.0
# 点「离开地点」的等待上限 —— 跟篝火的 WAIT_LEAVE 同值。
WAIT_LEAVE = 3.0


def _leave(g, hit, why):
    """点「离开地点」走人：`why` 是这次为什么走，原样打进日志。

    两个出口共用（"没有可移除" / "金币不足"），所以 `why` 由调用方给。

    走之前 `gridstate.forget()` 把那两格擦干净，见模块顶部那张表的最后一行。
    """
    gridstate.forget()

    if not g.click_when(离开地点, timeout=WAIT_LEAVE, guard=hit.matched):
        return park(g, WAIT_SHOP, "shop_leave_stuck",
                    f"商店：{why}，该走了 —— 可「离开地点」没找到/点不掉 —— 停下等人（已存 shop_leave_stuck.png）")
    log(f"    → 离开地点（{why}）")
    g.leave_after()
    return ""


def handle(g, hit):
    """在商店界面做一次决策并执行。

    返回值只管"要不要停"（`""` = 处理完 / 非空 = 理由），**走去哪了看 print**。
    一次进门只点一个键：要么「移除卡牌」（然后交给销毁卡牌屏），要么「离开地点」。
    """
    last, asked = gridstate.take()          # 读走就清

    if last is False:
        return _leave(g, hit, "销毁卡牌屏里没有可销毁的牌了")
    if last is None and asked:
        # 刚点过「移除卡牌」，可这一帧先认出来的还是商店屏：面板可能还在淡入，
        # 也可能压根打不开（老规矩当作金币不足）。**等一眼再判**，见模块顶部那段。
        if g.wait_for((你的卡组,), timeout=WAIT_REMOVE) is not None:
            gridstate.ask()                 # 还没答：这问继续悬着，别重复点
            log("    商店：面板正在淡入")
            return ""
        return _leave(g, hit, "点过「移除卡牌」却没进销毁卡牌屏 —— 当作金币不足")

    gold = g.read_number(金币数量)
    log(f"    商店：金币 {gold}，"
          f"{'上一趟还销毁得动，接着清' if last else '开始清卡'}")

    gridstate.ask()
    if not g.click_when(移除卡牌, timeout=WAIT_REMOVE, guard=hit.matched):
        gridstate.forget()
        return park(g, WAIT_SHOP, "shop_remove_noclick",
            "商店：「移除卡牌」没找到/点不掉 —— 停下等人（已存 shop_remove_noclick.png）")

    log("    → 移除卡牌")
    return ""
