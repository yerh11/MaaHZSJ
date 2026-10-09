"""死亡屏（黑屏）—— **点一下屏幕**，就这一件事。

用户 2026-10-02 定的，原话三句：
    「点完「最后的机会」的「挣扎」后，又死亡了, 所以屏幕黑了, 此时要点击一下屏幕」
    「死亡画面不固定」
    「下一次死亡不一定时这个画面」

所以这一屏认的是**屏幕黑没黑**，不是认某个画面 —— 那天停着的是"黑底一大团
紫色水晶"（存图 debug/screenshots/fight_timeout.png），但用户明确说了下次不一定
是这个画面，做成水晶的模板就是拿一次当永远。黑度 0.60 那条线怎么量的
（这一屏 0.649~0.673，其它非死亡帧最黑 0.532）写在 战斗.json 的 `死亡黑屏` 注释里，
量尺脚本是 debug/_crystal_probe.py。

**光"黑"不够，还有第二道闸：屏上没有字**（`is_death_black`，2026-10-02 补）。
用户当天看了那次停车现场，给的原话是「**死亡黑屏是没有任何文字的**」。
那一次就是只认"黑"栽的：停在的是一张**暗事件屏**（「困兽或囚徒」），
黑得跟死亡屏一个样，于是先命中死亡屏、对着插图正中连点了十来下，
而事件屏那两行判据一次都没被问过（详见 is_death_black 的注释）。
两道闸合起来才是这一屏：**黑，且没有字**。
（第二道闸 2026-10-04 又被同一件事绊了一次 —— 这回是"黑、真没字，可插图被 OCR
看出了一个假字"，于是给它加了第三道约束 `TEXT_SCORE`，见那个常量。）

**进来之前**：这一屏在战斗里是 `Game.fight()` 认出来之后返回 "死亡" 交过来的
（它只认"点过「挣扎」之后的黑屏"）。**同一条链上还有下一屏「化形信使」**
（`handle_relic`）——2026-10-03 实测那次死亡**没经过黑屏**、战斗直接跳到了
化形信使屏，fight() 从前不认识它，在那儿空转到 300s（现场图
debug/screenshots/fight_timeout.png、debug/run_1003a.log:632）。现在 fight()
见到它也返回 "死亡" 交出来，两屏由认屏表分派。从主循环别处走进来时没这道闸，
下面那两条自我约束就是替它兜底的。

三道自我约束，都是被坑出来的：

1. **先等它停住 1.5 秒再动手**。过场淡入淡出也会整屏全黑 —— 存档里
   `gone_1.png` / `gaze_left.png` 就是抓在转场上的纯黑帧，那种一两秒就过去了。
   死了之后这一屏是**停着等人点**的（实测停了 13 分钟没变）。
   等不住就什么都不做，让主循环再读一帧 —— 对着转场点一下是白点，
   而"点空"正是公告页被连点两下的那个病。
2. **点过之后 3 秒内不再点**。点下去新画面是从黑里淡进来的，中间那几帧仍然
   "黑"，不设间隔就会对着还没画好的新屏再点一下。
3. **连着点 GIVE_UP 下屏还不换，就停下等人**（`_clicks`）。前两条只管"别点太快"，
   没管"点了根本没用" —— 见 handle 里那段注释。
"""

import time

from strings import 不留下遗物, 屏幕文字, 死亡黑屏, 死亡黑屏继续, 化形信使
from shared.reasons import (
    WAIT_DEATH_RELIC,
    WAIT_DEATH_TAP,
    WAIT_LEAVE_MESSENGER,
    )
from shared.coords import WATERMARK_X, WATERMARK_Y
from shared.kit import log

HOLD = 1.5     # 黑屏要停住这么久才算"死透了那一屏"
REGAP = 3.0    # 点过一次之后，隔这么久才允许再点
GIVE_UP = 5    # 连着点这么多下、屏还是这一屏，就不再空点了 —— 停下等人
STREAK_GAP = 90.0   # 距上一次点击超过这么久 = 上一段早结束了（另一次死亡），重新数

_last_click = 0.0
_clicks = 0         # 这一"段"已经点了几下（段 = 中间没断开超过 STREAK_GAP 的一串）

# 版本水印（右下角那枚 `PID619402 1.1.1.5`）**每一屏都在**，不算"这一屏的字" ——
# 它那块位置（`WATERMARK_X` / `WATERMARK_Y`）已搬进 `shared/coords.py`。
# 第二道闸问的是**那块以外**还有没有字。

# OCR 一行要**多像字**才算"这一屏有字"（**2026-10-04 量出来的**）。
#
# 第二道闸从前是"除了水印，一条 OCR 行都不许有" —— 撞上**带插图**的真死亡帧就栽了：
# 插图里的花纹会被 OCR "看出"字来（那一次死亡演出是一头棘刺怪物，屏上其实一个字
# 都没有），一行 `'Mr'` `(484,90,56,125)`、score **0.182** 把这一屏判成了"有字"，
# 于是认屏表不认它、主循环空转到「连续多轮认不出」停车（现场帧
# `battle_unknown_182457.png`，2026-10-04 18:24）。同样的假字还有
# `battle_end.png` 的 `'MU'` 0.153、`_std_10f.png` 的 `'-ö'` 0.544。
#
# 拿**全部 1129 张存档帧**过了一遍（`debug/_text_probe.py --corpus`，只读）：
# 过黑度闸的 89 帧、105 行 OCR ——
#     水印行        88 行（**位置法**排除，score 0.9x）
#     真游戏文字    **14 行，score 0.954 ~ 1.000**（暗事件屏「困兽或囚徒」的标题 /
#                   正文 / 两个选项 / 血量金币 —— 那正是这道闸要挡住的东西）
#     假字（插图里看出来的）**3 行，score 0.153 / 0.182 / 0.544**
# 两群之间是空的，0.75 取在正中间：离真字最近 0.20、离假字最近 0.21。
TEXT_SCORE = 0.75


def is_death_black(g, image):
    """这一帧是不是死亡黑屏：**屏黑，且屏上没有字**（右下角版本水印不算）。

    用户 2026-10-02 给的判据，原话：「**死亡黑屏是没有任何文字的**」。
    第一道闸（`死亡黑屏` 那个 ColorMatch）只问"黑不黑"，撞上暗事件屏会认错 ——
    那次停车就是（debug/run_1002ai.log、debug/screenshots/_park_1002ai.png）：
    那是一张事件屏（「困兽或囚徒」），整帧平均亮度 23.7、亮度<60 的像素占 0.9178，
    黑度和死亡屏一个量级，而排在上面的死亡屏那行先命中，事件屏那两行判据
    （标题 + 选项）**一次都没被问过**，脚本就对着插图正中点了十来下。

    两张图各有多少字（同一张整屏 OCR 量的，量尺 debug/_text_probe.py）：
        死亡屏 fight_timeout.png      1 行，就是那枚版本水印
        暗事件屏 _park_1002ai.png   15 行，标题/正文/两个选项/血量金币

    **第三道约束（2026-10-04 补）：一行字还得分像不像字**（`TEXT_SCORE`）。
    光数行数会在**带插图**的真死亡帧上判错 —— 插图花纹会被 OCR "看出"字来，
    见 `TEXT_SCORE` 上面那段（那一次停在了 `battle_unknown_182457.png`）。
    """
    if not g.see(死亡黑屏, image):
        return None

    reco = g.probe(屏幕文字, image)
    for r in ((getattr(reco, "all_results", None) or []) if reco else []):
        if not getattr(r, "text", None):
            continue
        if (getattr(r, "score", 0.0) or 0.0) < TEXT_SCORE:
            continue                # 认不过线 = 从插图里"看出"的假字，不算这一屏的字
        x, y, _w, _h = r.box
        if x >= WATERMARK_X and y >= WATERMARK_Y:
            continue                # 版本水印，哪一屏都有，不算这一屏的字
        return None                 # 还有别的字 —— 这不是死亡屏

    return {"非水印文字": 0}


def _still_black(g, hold):
    """连续 hold 秒，屏幕一直黑着。中途亮了一下就返回 False（那是转场）。"""
    end = time.monotonic() + hold
    while time.monotonic() < end:
        # 这个 sleep 是**轮询间隔**（隔 0.3s 再看一帧），不是拿时长蒙状态变化 ——
        # 这里要验的恰恰是"它一直没变"，wait_for / wait_gone 都表达不了这件事。
        time.sleep(0.3)
        if not g.see(死亡黑屏):     # 不传 image = 现截一张
            return False
    return True


def handle(g, hit):
    global _last_click, _clicks
    now = time.monotonic()

    # 第 3 道约束（**连着点不换屏就别再空点了**，2026-10-02 补）。
    # 前两道只管"别点太快"，没管"点了根本没用" —— 那次停在暗事件屏上，
    # 日志里刷了十来行一模一样的「死透了 → 黑屏，点一下屏幕」，一直点到人来看
    # （debug/run_1002ai.log）。那十来下每一记都点在插图正中，屏幕纹丝不动。
    # 判据修好之后那一种不会再来，但"点了没反应"本身就不该无限刷 ——
    # 点够 GIVE_UP 下屏还不换，停下等人（理由里带上是第几下）。
    # 段的划分：handle 只在**这一屏还在**的时候被调，点击间隔 ≥ REGAP，
    # 所以"距上次点击超过 STREAK_GAP"只可能是屏走掉了又回来 = 另一次死亡。
    if now - _last_click > STREAK_GAP:
        _clicks = 0

    if now - _last_click < REGAP:
        return ""                   # 刚点过：给它几秒把新画面画出来

    if not _still_black(g, HOLD):
        return ""                   # 只是转场黑一下，别碰

    if _clicks >= GIVE_UP:
        g.snap("death_black_stuck")
        log(f"    黑屏还在，已经点了 {_clicks} 下都没反应")
        return f"等待点击（死亡黑屏·点了{_clicks}下没反应）"

    # guard=hit.matched（就是「死亡黑屏」）：点下去那一帧还得是黑屏，
    # 不接受"认屏那帧是黑的、这一帧已经变了"——变过就说明不用点了
    if not g.click_when(死亡黑屏继续, guard=hit.matched):
        # 这一处从前是 `snap + return`、**一句话都不说**：脚本默默停在黑屏上，
        # 日志里只多一条理由行，看不出图存没存、为什么停（2026-10-04 补的 print，
        # 和同文件 GIVE_UP 那处对齐）。
        g.snap("death_black_noclick")
        log("    黑屏上那一下没点动（「死亡黑屏继续」没认出来 / 那一帧已经亮了）")
        return WAIT_DEATH_TAP

    _last_click = now
    _clicks += 1
    log(f"    死透了 → 黑屏，点一下屏幕（正中 640,360）（第 {_clicks} 下）")
    return ""


def handle_relic(g, hit):
    """「化形信使」那一屏 —— **点「不留下遗物」**，就这一件事。

    用户 2026-10-02 定的：问「死亡后这一屏…脚本该点哪个？」，答"不留下遗物"
    （左边那枚）。

    它和死亡黑屏是同一条链（所以放在同一个文件里），但**来的路不止一条**：
    从前以为必定是"黑屏点一下之后"进来，2026-10-03 00:45 实测那次死亡
    **黑屏那一步整个没出现**，战斗直接跳到了这一屏（debug/run_1003a.log:632、
    现场图 fight_timeout.png）—— 用户早就说过「死亡画面不固定」，这就是它的
    另一种样子。所以 `Game.fight()` 现在两条路都接（黑屏、化形信使），谁先来算谁。
    现场：顶部标题「化形信使」，中间「你要，留下，些什么」，
    底部并排「不留下遗物」/「留下遗物」；存图 debug/screenshots/_death_relic.png，
    当时脚本报「未知界面」停车（debug/run_1002af.log）。

    点完**等这一屏真的走掉**（`wait_gone`）再回去，不是点完就撒手 ——
    退场那几帧上标题还在，主循环下一轮会再认到这一屏、再点一下，
    那就是「公告页被连点两下」那个病。等不到就存图停下，**不猜**。
    """
    if not g.click_when(不留下遗物, guard=hit.matched):
        # 同上：这两处从前也不吱声（2026-10-04 补 print）。
        g.snap("death_relic_stuck")
        log("    「不留下遗物」没点动（那一帧已经不是化形信使屏了）")
        return WAIT_DEATH_RELIC

    log("    化形信使 → 不留下遗物")
    if not g.wait_gone(化形信使, timeout=6.0):
        g.snap("death_relic_notgone")
        log("    点过「不留下遗物」了，可化形信使屏还没退场")
        return WAIT_LEAVE_MESSENGER
    return ""
