"""整局结算（打穿首领 / 失败，**这一屏不分胜负**）→ 收尾回主界面。

用户 2026-10-01：「每次结束后都返回主页面」。

**这条路不是一个"两步"那么简单。** 2026-10-01 打通首领那局实测：
    结算总览屏 →「继续」→ 星空过场 →「结束此次探索」
    →「获得物品」×2（梦境等级升级奖励、整局结算的材料，**排队弹**，
       出口都是「点击任意空白处关闭」）
    → 星空过场**又回来了** →「结束此次探索」**再点一次**
    → 加载屏（几秒）→ 主界面

「结束此次探索」要点两次、弹窗个数不固定（等级没升就少一个）、每步出下一屏
的延迟也都在 3 秒上下 —— **所以这里不写死步数**：看见哪个点哪个，直到
「主界面」出现。被中断了重跑一次也能接着走完。
（第一版按"继续 → 结束探索 → 主界面"写死，就是这么栽的：点完前两下停在
升级窗上，报「没看到主界面」。）

**别改走 ensure_main()**（battle.py 里那个）：那是杀进程重开
（post_stop_app + start_game），冷启动 40~60s，还得重过标题界面和评价弹窗 ——
这里只要十几秒。

**胜负从 2026-10-03 起分得出来了**：胜负写在**这一屏左上角那行标题**上 ——
用户当天给的就是这条判据：「**当屏幕上显示"仪式终结?"时,表示成功通关**」。
实图核对过（debug/screenshots/_crop_title_probe.png，通关那局的结算屏），
失败那侧同一位置是「仪式失败」（见 结算.json 两个节点的注释）。
只报胜负，**不改收尾流程**：通不通关都是回主界面，`handle()` 照旧返回 `FINISHED`。
（`Game.fight()` 那边仍旧只报「本局结束」—— 它结束在战斗屏上，胜负要到这一屏才写出来。）
"""

import time

from strings import (
    主界面,
    仪式成功,
    仪式失败,
    仪式结算,
    结束此次探索,
    获得物品,
    点击任意空白处关闭,
    继续,
    )

# 收尾走完时的协议值：battle.py 靠它分辨"这一局正常打完了"和"停车等人/出事了"
# —— 前者接着开下一局，后者必须停下。
#
# 2026-10-04 起**定义搬去 `shared/reasons.py`**（和 ABANDONED 住一起，那才是
# "一共有哪些停车理由"的唯一答案）。这里 import 回来是**为了兼容**
# `from system.settlement import FINISHED` 老写法（battle.py 就这么写的）。
# 新代码请直接从 shared.reasons 取。
from shared.reasons import FINISHED  # noqa: F401
from shared.kit import log


def finish_run(g, timeout=300.0):
    """结算总览屏 → 主界面。**幂等**：从这条路上任何一屏接上都能走完。

    这份**局部判据子集留在原地，不并进认屏表**：路上夹着「获得物品」这类弹窗，
    并进表就等于局内遇到它会被自动点掉 —— 那是策略变化，用户没定过。

    **timeout 从 90s 挪到 300s（2026-10-04，实测）**：这条路的最后一步是**加载屏**
    （「结束此次探索」点完之后的过场，满屏插画 + 底下一条进度条），从前按
    「加载屏（几秒）」估的 90s 兜。当天连着两次停在它上面（`loop_notmain.png` /
    `finish_run_stuck.png` 两帧都是那张加载屏，进度条才走了 15%~30%），而**游戏自己会
    走完** —— 拿秒表连拍量到的那一次是 **177.3s**（15:49:39 点「结束此次探索」→
    15:52:41 「主界面」命中，同一局的另一次只要 **13s**）。所以这个数不是"卡住了"，
    是**慢得没谱**：13s ~ 177s。300s 把量到的最慢那次留出 1.7 倍余量；
    真要是卡死，代价只是多等这 300s 再停车留图。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        image = g.capture()

        if g.see(主界面, image):
            log("    已回主界面")
            return True

        # **模态优先**：弹窗盖着的时候，底下「结束此次探索」就算认得出也点不动，
        # 所以「获得物品」必须排在它前面（实测弹窗屏上两个都在，见
        # debug/screenshots/finish_run_main.png）。
        #
        # 「每日签到」面板同理，而且它盖得**更死** —— 2026-10-05 08:11 那局就是这么停的：
        # 面板整屏盖住主界面，底下「主界面」三个字一个都认不出来，这一整段空等到
        # 300s 超时（现场图 loop_notmain.png）。出口用户当天定：「点右上角 X 关掉（不领）」，
        # 判据与点法在 `auto.close_daily_panel`。**用的是这一轮已经截好的 frame**。
        if g.close_daily_panel(image):
            continue


        # 每一项都是"现截现验地点、点完等它退场"：从前是点完 sleep(2.0)，
        # 时长是猜的，猜短了下一轮会对着还在退场的同一屏再点一次。
        if g.see(获得物品, image) and g.click_when(点击任意空白处关闭, guard=(获得物品,)):
            log("    获得物品 → 点击空白处关闭")
            g.wait_gone(获得物品, timeout=10)
            continue

        if g.see(结束此次探索, image) and g.click_when(结束此次探索, guard=(结束此次探索,)):
            log("    结束此次探索")
            g.wait_gone(结束此次探索, timeout=10)
            continue

        if g.see(仪式结算, image) and g.click_when(继续, guard=(仪式结算,)):
            log("    结算 → 继续")
            g.wait_gone(仪式结算, timeout=10)
            continue

        # 什么都认不出：多半是加载过场（实测那句「护甲牌保留在队列中才能抵挡伤害」
        # 就是这时候的屏），等它，**别当成失败**。
        time.sleep(0.6)

    log(f"    {timeout:.0f}s 内没回到主界面 —— 存图，停下等人")
    g.snap("finish_run_stuck")
    return False


def read_outcome(g):
    """读结算屏那行标题，回 "成功" / "失败" / ""（没读出来）。

    **两个正判据，都不命中就如实说不知道** —— 不用"没读到成功"当失败：
    OCR 漏一次就把赢报成输，正是这个项目里最不能有的那种判据（从前
    `Game.fight()` 把通关报成失败，就是同一类错）。

    只在**刚进这一屏**读：点过「继续」面板就关了，标题跟着没（所以 handle()
    里这一次读排在 finish_run() 前面）。
    """
    image = g.capture()
    if g.see(仪式成功, image):
        return "成功"
    if g.see(仪式失败, image):
        return "失败"
    return ""


def handle(g, hit):
    """整局收尾（回主界面），然后交回一个**终局**理由。

    先报胜负（见 read_outcome 与模块开头），再收尾 —— 两条路都回主界面，
    **本函数不因胜负改走法**。

    注意返回值是 `FINISHED`，而 `finish_run` 的成功与否**没有**体现在里面 ——
    这里从前就是这么写的，本函数不替调用方判断"到底回没回到主界面"。
    battle.py 的循环开下一局之前会自己 `see(主界面)` 核一遍（收尾没回去就停下），
    所以这里不重复那道闸。
    """
    log("整局结束：仪式结算 → 返回主界面")
    outcome = read_outcome(g)
    if outcome == "成功":
        log("    这一局：**通关成功** —— 标题「仪式终结?」")
        g.snap("run_win")
    elif outcome == "失败":
        log("    这一局：**没通关** —— 标题「仪式失败」")
        g.snap("run_lose")
    else:
        log("    这一局：胜负**没读出来**（标题那两串都没命中）—— 如实记")
        g.snap("run_outcome_unknown")
    finish_run(g)
    return FINISHED
