"""卡牌网格的共用机制 —— **一切"在卡牌网格上选牌"的屏共用这一套**。

谁在用：`script/ops/card_copy.py`（复制）、`card_remove.py`（移除两版）、
`card_upgrade.py`（升级）。选卡屏的四副卷面共用同一套控件与同一套格位，
差别只在**副标题**（分派在 `nodes/cardpick.py` 的 `handle()`），所以
"怎么找格子 / 怎么看选没选中 / 怎么点「确定」"这三件事收在这里一份。

⚠️ **别和 `shared/gridstate.py` 混了**：那是**跨屏状态的唯一一处**
（商店 ⇄ 销毁面板之间的那两格旗），与这里的"网格几何 + 判据"毫无关系，
名字撞了纯属巧合。

⚠️ **这儿的模块级常量会被 debug 单测打猴子补丁**（`grid.AFTER_TAP = 0`
这类，把等待压掉），所以操作小类引用它们时写 `grid.AFTER_TAP` 而**不是**
`from shared.grid import AFTER_TAP` —— 后者在 import 期就把值冻住了，补丁打不进去。

**判据的来历（实测值）都写在各条常量上面那段注释里** —— 那些注释是判据的一部分，
改数之前先把它们读完。
"""

import time

import numpy as np

from strings import 卡牌名, 选卡副标题, 选卡确定, 选择卡牌
from shared.cards import base_name, looks_like_name
# 面板范围 / 格位表 / 格心大小 —— 固化坐标收在 shared/coords.py
#（1280x720 基准；换分辨率只看那个文件）。这里 import 回原名，使用点一字未动。
from shared.coords import CARD_GRID as GRID
from shared.coords import PANEL_BAND, SLOT_HALF, SLOT_X, SLOT_Y
from shared.reasons import WAIT_CARD
from shared.kit import log


# 投影时"这一列/行上有卡"的亮度线，以及切出来的带子至少要多宽才算数
LUM_ON = 85
BAND_MIN = 25

# 格子正中 60x60 的平均亮度低于这条线 = 空位（见 `nodes/cardpick.py` 模块 docstring 的实测值）
CELL_MIN = 45

# 点一张卡之后，详情面板要等它弹出来才读得到卡名
AFTER_TAP = 1.1


# 移除屏的**保留名单**不在这个文件里了 —— 在 `script/cards/保留.json`（判据在
# `shared/cards.py` 的 `Rules`，卡面那份是同文件的 `FACES`，商店的销毁卡牌屏两个都用）。
# 这条单子最早住在这儿（2026-10-03 事件那条路），2026-10-04 商店那条路要的是同一张，
# 而屏模块之间不许互相 import（tools/check_screens.py 第 1 条钉着），所以搬去了公共层。


# ==================== 第二版移除屏：「选择最多3张卡牌，将其移除。」 ====================
#
# 2026-10-04 第一次撞上（事件「狭缝」→ 第 2 格「接纳御火者的指引，跳过本层，直面首领」，
# 现场图 `debug/screenshots/cardpick_noback.png`）。**和第一版只差一个"最多"，可走法差很多**：
#
#   · 第一版「从卡组中选择一张卡牌移除。」：点一张＝选它（点另一张＝换选中），
#     没有可移除的就点左上角「返回」。
#   · 这一版「选择最多3张卡牌，将其移除。」：**点一张＝把它加进选中（最多 3 张，可以不选）**，
#     选完点底下的「确定」才真移除；**这一版没有「返回」**（实测：`选卡返回` 模板在这屏
#     0 命中，全屏 OCR 也只有「确定」一枚按钮）。
#
# 策略是用户 2026-10-04 定的：「选择最多三张(可以不选)非指定牌进行移除, 选择完成后点击
# 确认即可移除」+「可以不选择, 如果有非保留名单的牌, 就选择, 如果都是保留名单的牌,
# 就一张都不选」+ 全是保留牌时「取消选中再点「确定」」。
#
# ---- 这一版的格子表为什么**写死**（第一版是靠投影现算的）----
#
# 这一屏**同一条格子的长相会随"选没选中"变**。格心取 60x60 一块，量的是**标准差**
# （下面第一组数出自 `cardpick_noback.png`，那帧上脚本已经选中了 3 张；标准差那一列
# 是 2026-10-04 拿 71 张存档真屏全量的）：
#
#                     均值        标准差
#     空位（面板底色）   29.9~34.3   **0.6 ~ 2.0**       ← 平
#     没选中的牌（洗白） 96.2~102.5  **10.89 ~ 15.62**   ← 亮而平（灰罩把它罩白了）
#     没洗白的牌（全对比）59.6~63.4  **30.24 ~ 67.4**    ← 有画
#
# 分界线就落在那道空档（15.62 → 30.24）正中，所以一格是哪一种**一眼就分得出来**
# （`state_of`）。**注意"洗白"看的是标准差不是亮度**：它被罩得**更亮**、但更**平**。
#
# ---- 这一屏的"选中"到底怎么看（2026-10-04 重量的，头一版判据是错的）----
#
# 头一版按"洗白＝没选中"反推"选中的是哪几张"，**栽过一次**：脚本点了一张牌，
# 牌也确实选上了，可屏上一个灰罩都没有，于是被判成"点了没选上"当场停车
# （现场图 `debug/screenshots/cardpick_select_stuck.png`）。当天量下来是这样：
#
#   ① **灰罩只在选满 3 张时渲染**。选满时没选中的牌被洗白、选中的 3 张保持全对比；
#      **不足 3 张时一张都不洗白**，选中的牌与没选中的**像素上一模一样**
#      （实测：选着 2 张那帧 8 张全亮 46~57；再点一张凑满 3 张，同一帧就变成
#      3 亮 5 暗 —— 顺序、位置都对得上）。
#   ② **点一下＝切换选中**（选中↔取消），上限 3 张。选满之后点没选中的牌
#      **游戏直接不理**（左边面板那行名字也不跟着换 —— `debug/cards.py list`
#      就是被这一条骗的：连着 6 次报同一张卡名）；点**已经选中的**牌照样能取消。
#      所以"同一格点两下"＝净效果为零 —— 这是"点开面板读卡名"却不改选中的唯一办法
#      （卡面模板在这一屏认不准，见 `nodes/cardpick.py` 的模块 docstring，所以非点开不可）。
#   ③ **左边那块卡牌详情面板在不在**：一张都没选时面板**收起来**，那一带露出深色
#      空白；选着（哪怕只 1 张）面板就弹着。于是量「卡牌名」节点 roi 那一带
#      （`PANEL_BAND`）的平均亮度：实测"一张都没选"是 **0.9~4.2**（五帧），
#      "选着"是 **39.6~46.7**（四帧）—— 差着 10 倍，线取 20。
#
# 三条合起来，这屏能**确定**下来的只有三件事：**有灰罩 ⇒ 选满 3 张，且选中的就是
# 亮的那 3 张**；**面板关着 ⇒ 一张都没选**；**面板开着却没有灰罩 ⇒ 选着 1 或 2 张，
# 但看不出是哪几张（没判据）**。最后这一种不猜，停车等人（`cardpick_preselected`）。
#
# 2026-10-09 补了第四条判据（`HALO_GREEN` 那一段），治的是"面板开着**也可能**一张都
# 没选"——那块亮着的东西是从别处飘过来的卡牌信息框。它把上面第三条拆成两种：
# **有光环 ⇒ 真的选着 1~2 张**（照旧停车）；**满屏一格光环都没有 ⇒ 一张都没选**
# （收掉那个框，按 0 张走）。
#
# ⚠️ **不能拿 `read_name` 单独当"没选中"的判据**：k=0 时那一带露着事件正文
# （实测 k=0 那帧 roi 里是「你感受到了黄金野兽-帕特拉姆的存在」这种整句），
# 两个字以上的汉字 `looks_like_name` 全收。卡名要和亮度**一起看**（`nothing_selected`）。
#
# 而第一版那套"按亮度投影切列带"（`cells()`）**在这一屏不能用**：选中的牌换成了洗白
# 之后，牌与牌之间那道缝不再变暗，列带会**黏成一整条**（实测那帧只切出 3 条，
# 而牌有 5 列）—— 所以它只能在同一帧**全都一个样**的时候用（第一版那屏就是这样）。
# 写死格位反而稳：**格位不随选中变，只有格子上牌的长相会变**。
#
# 格位是实测的（`debug/screenshots/_cp_slots_probe.png` 是把这 15 个点画回那一帧的
# 核对图，每个点都落在牌心/空位正中间）：列心 692/809/926/1043/1160（间距 117），
# 行心 221/387/553（间距 166）。
#
# ---- 第 3 行是 2026-10-04 补上的，**从前那套"最多 5x2"是量错了的** ----
#
# 头一版只量到两行，就照"面板底下放不下第 3 行"写死了 10 个格位，还拿
# y=553 那一带当"这儿还有没有牌"的哨兵 —— 牌超过 10 张就停车等人。那天真撞上
# 12 张（`debug/screenshots/cardpick_third_row.png`，5+5+2）才量明白：
# **第 3 行用的是同一套列心、同一档行距**，只是从前量到的那两局牌都不够 10 张，
# 第 3 行本来就是空的（0.49~0.92，平的底色）—— "面板底下放不下"是照空位推出来的，
# 不是真的。
#
# 三帧各量一次（都是 15 个格心 60x60 的标准差，口径同 `state_of`）：
#
#     张数/摆法              第 3 行五列（列 1→5）
#     12 张 5+5+2           56.62  65.82   0.61   0.81   0.72   ← cardpick_third_row.png
#     11 张 5+5+1           65.77   0.70   0.61   0.59   0.49   ← cardpick_recon_before.png
#      8 张 5+3              0.90   0.92   0.81   0.85   0.74   ← cardpick_noback.png
#
# 12 张那一帧再按"亮过底色"的投影切一次：第 3 行两张牌的横段是 641~743、760~860
# （**牌心 692、810**，宽 ~102 —— 和第 1 行同一列心切出来的 644~740 / 996~1092 /
# 1113~1209 一模一样的宽度），竖直范围 473~630（**牌心 ~551**，第 1 行是 144~295、
# 牌心 219.5）。**行距 166、列距 117，与头两行一格不差** —— 所以格位表就是
# **5 列 × 3 行 = 15 格**，不用另立一张表。
# 上面这两个数（`SLOT_X` / `SLOT_Y`）与格心大小 `SLOT_HALF` 已搬进
# `shared/coords.py`（1280x720 基准），这里 import 回来。
#
# 下面两条分界线**不是坐标、是亮度阈值**（随牌面变），留在本文件。
SLOT_FLAT = 4.0        # < 4 = 空位（实测 0.6~1.4）
# 洗白有多"白"**随牌面变**：同一帧里量到 8.6 / 10.9 / 15.2 / 15.3 / 15.6 / 17.9。
# 所以分界线要压在**最小的那个洗白值**（8.6）下面 —— 从前这条写的是 8.0，
# 差 0.6 就撞上了，那张牌会被读成"空位"，紧接着的 1-2 是张牌，`holes` 当场判"读花了"。
#
# ---- 34.0 这条线 2026-10-04 从 34 挪到 23：**它从前切在牌的群里** ----
#
# 那 8.6~17.9 是拿**一张牌很多的帧**量的，谁想到还有**画得平**的牌：紫底火球卡
# （「迅捷」那类的卡面）的格心标准差只有 **32.12~32.17**，压在 34 底下，于是
# "没选中、也没洗白"的一张牌被读成**洗白**。后果不是停车而是**走错路**：
# `_remove_multi` 第 ① 步把"屏上有洗白"当成"进来时就选满 3 张"，会去挨个点掉
# —— 12 张那一局就是这么差点点歪的（`cardpick_third_row.png`，实测 8 张全对比里
# 混着两张 32.15）。
#
# 所以把**全部 71 张存档的真·选卡屏**（`debug/screenshots` + `_probe_lu*` 里
# 1280x720 且认得出「选择卡牌」的）15 个格心全量一遍，三种状态**分得干干净净**：
#
#     空位        0.6 ~ 2.0
#     洗白       10.89 ~ 15.62        ← 10 格
#     全对比     30.24 ~ 67.4         ← 最低那 4 格是 30.24，紫底火球卡 32.12~32.17
#
# 中间 **15.62 ~ 30.24 —— 空着 14.6 个单位没人**，线取正中 **23.0**（两边各留 7.3）。
SLOT_WASHED = 23.0     # < 23 = 洗白（实测 10.89~15.62）；>= 23 = 全对比（实测 30.24~67.4）

# 这一屏最多选几张（屏上写着「最多3张」）
SLOT_LIMIT = 3
# 面板上那行卡名要弹一下才写得出来，第一次读不到就再等一档重读（`AFTER_TAP` 之上再加的）
SLOT_REREAD = 0.8

# 左边那块详情面板的卡名带子（`PANEL_BAND`，已搬进 `shared/coords.py`）在不在看它亮不亮。
# 那条带子的 roi 与 `assets/resource/pipeline/卡牌族.json` 的 `卡牌名` 节点**同值但不同用**：
# 那边是喂给 OCR 的裁剪区，这边只量这一带有多少光（见上面 ③ 那段实测）。
PANEL_MIN = 20.0       # < 20 = 面板不在（实测"一张没选" 0.9~4.2）；>= 20 = 面板弹着（39.6~46.7）

# ---- ④ **"这一格选着没有"的第二条判据：牌框外侧那一圈青绿光环**（2026-10-09 加）----
#
# 上面 ③ 那条"面板开没开"只分得出"零 / 非零"，**面板亮着也可能一张都没选** ——
# 2026-10-09 撞上的就是这个：上一屏（第一版移除屏）的 `scan()` 把最后点过的那张牌的
# **卡牌信息框**留在了屏上（用户 2026-10-02 定的规矩：「不点掉就会一直挂着」，
# 落点在 `Game.clear_info_box()`），这个框飘到这一屏、**正好压住 `PANEL_BAND`**，
# 于是"面板弹着"＋"读出卡名『莽撞头槌+』"两条判据同时成立 ⇒ 判成"选着 1~2 张"，
# 明明一张都没选却停下等人（现场帧 `cardpick_preselected.png`）。
#
# 选中时游戏会在牌框**外侧**画一圈青绿光晕。量法（`debug/_scan_selected.py`，
# **46 张真·选卡屏存档帧**逐格过一遍；带子＝格心往外 58~63px、高 140px，
# 左右两条**取较暗的那条**）：看那条带子里"绿像素"（`G>=R 且 G>B+3 且 G>110`）
# 占多少 ——
#
#     选着的那一格     **44% ~ 67%**     （每个选中格都过 44%，共 14 格次）
#     一张都没选       **0%**            （46 帧 × 15 格，一格不例外）
#
# 中间 0 → 44 是空的，线取 **20**。**只看亮度不行**：别的屏那一带本来就亮，
# 而这一屏上相邻两张都选着时中间那条缝两边都亮 —— 所以两条竖带取**较暗的那条**，
# 那才是"这一格自己那侧"的真实情况（`cardpick_noback.png` 的 1-4 就是这么从
# 27% 掉回 0% 的）。
#
# ⚠️ 它只用在**"满屏一格光环都没有"**这个方向上（⇒ 屏上真的一张都没选），
# **不拿它去逐张核身份** —— 它给的是"选着没选着"，不是"选的是哪张"。
HALO_EDGE = 52         # 牌框半宽（实测 ≈51），从格心往外量
HALO_GAP = (6, 12)     # 再往外 6~12px —— 那两条竖带落在格心外 58~63px
HALO_HALF_H = 70       # 竖带的高度半值（牌高半值 ≈75，取 70）
HALO_GREEN = 20.0      # 绿像素占比 < 20% = 这一格没有光环（实测 0% vs 44~67%）


def patch(image, cx, cy, half=SLOT_HALF):
    """格心那一小块（亮度图）。**取通道均值，与通道序无关**，所以 BGR/RGB 都行。"""
    return image[cy - half:cy + half, cx - half:cx + half].astype(int).mean(axis=2)


def state_of(patch):
    """一小块是三种状态里的哪一种（分界线见 `SLOT_FLAT` / `SLOT_WASHED`）。"""
    s = float(patch.std())
    if s < SLOT_FLAT:
        return "empty"
    return "full" if s >= SLOT_WASHED else "washed"


def slots():
    """这一屏 **5 列 × 3 行**的格位表（**只有位置，没有状态** —— 状态要现截现读）。

    牌不到 11 张时第 3 行是空位（量出来 0.6~2.0），照样在表里 —— `empty` 不占
    `occupied`，多出来的格子不花钱。"""
    return [{"row": ri, "col": ci, "cx": cx, "cy": cy}
            for ri, cy in enumerate(SLOT_Y, 1)
            for ci, cx in enumerate(SLOT_X, 1)]


def states(image, cells=None):
    """一帧上每格是三种状态里的哪一种：`{(行,列): "empty"|"washed"|"full"}`。

    默认拿这一屏写死的那 10 个格位（`slots()`）去量。
    """
    return {(c["row"], c["col"]): state_of(patch(image, c["cx"], c["cy"]))
            for c in (cells or slots())}


def panel(image):
    """左边详情面板那一带（`PANEL_BAND`）的平均亮度。**与通道序无关**（取通道均值）。"""
    x, y, w, h = PANEL_BAND
    return float(image[y:y+h, x:x+w].astype(int).mean(axis=2).mean())


def glow(image, cx, cy):
    """这一格**外侧**那一圈光环有多绿 —— 报绿像素的占比（0~100）。

    选中时游戏在牌框外画一圈青绿光晕（带子与分界线见 `HALO_GREEN` 上面那段实测）。
    左右两条竖带取**较暗的那条**再看绿：相邻那张牌选着时，两条带子中间那条缝里
    是它溢过来的光，较暗的那条才是"这一格自己那侧"的真实情况。

    `image` 是 `Game.capture()` 的原样帧 —— **BGR**（`snap()` 里那句
    `capture()[:, :, ::-1]` 就是证据），所以绿是第 1 个通道、红是第 2 个。
    """
    strips = []
    for sign in (-1, 1):
        xs = cx + sign * (HALO_EDGE + np.arange(HALO_GAP[0], HALO_GAP[1]))
        xs = xs[(xs >= 0) & (xs < image.shape[1])]
        if len(xs) == 0:
            return 0.0
        strips.append(image[cy - HALO_HALF_H:cy + HALO_HALF_H, xs].astype(int))
    b, g, r = min(strips, key=lambda a: a.mean()).transpose(2, 0, 1)
    lit = (g >= r) & (g > b + 3) & (g > 110)
    return 100.0 * float(lit.sum()) / float(lit.size)


def glowing(image):
    """这一帧上**哪几格带着选中光环**：`{(行, 列), ...}`（没有就是空集）。

    ⚠️ 这个判据只往**"有没有"**上用（见 `HALO_GREEN` 上面那段）——**别拿它挑格子**。
    """
    return {(c["row"], c["col"]) for c in slots()
            if glow(image, c["cx"], c["cy"]) >= HALO_GREEN}


def nothing_selected(mean, name):
    """**"一张都没选"的判据：亮度与卡名两条一起看**（来历见上面 ③ 那段实测）。

    为什么非要两条：k=0 时那条带子上露着的是**事件正文**，光看卡名会把
    「你感受到了黄金野兽-帕特拉姆的存在」当成卡名（`looks_like_name` 只要两个汉字，
    它全收）；光看亮度又怕别的屏上那一带本来就亮。**两条都指向"面板不在"才算数。**
    """
    return mean < PANEL_MIN and name is None


def frame(g):
    """**现截一帧**，报 `(每格状态, 面板上的卡名, 面板那一带的亮度)`。

    一帧只截一次：三样都从**同一帧**上读（卡名那个 roi 也在这帧上，`read_name`
    收现成的帧就不再自己截）。这一屏"一格的长相会随选中变"，所以每次动手前后
    都得重看一眼，**不缓存**。
    """
    image = g.capture()
    return states(image), read_name(g, image), panel(image)


# 从前这儿有个 `_no_extra_rows()`：格位表只有两行，就把它当哨兵，拿 y=553 那一带
# 探"这儿还有没有牌"，一见有牌就停车等人（理由 `cardpick_third_row`）。
# **2026-10-04 撞上 12 张那局（`cardpick_third_row.png`）量明白它是多余的** ——
# 第 3 行用的就是同一套格位（见 `SLOT_Y` 上面那段实测），哨兵挡掉的是本来就该走的路。
# 函数与那条停车理由一起删了，**别再把它加回来**。


def holes(states):
    """格子读花了才会出现的"空洞"：一行里前面空着、后面却又有牌。

    这一屏的牌是**从左上角起一行行排满**的（实测：8 张＝5+3、11 张＝5+5+1、
    12 张＝5+5+2 都合这一条），所以按行优先数过去应当是"先占满、后全空"。
    出现空洞说明那几格里至少有一格不是牌 —— 读花了，停车，别拿这种格子表去点。
    """
    seen_empty = False
    for key in sorted(states):
        if states[key] == "empty":
            seen_empty = True
        elif seen_empty:
            return True
    return False


def tap_slot(g, cell):
    """点一格（选中↔取消选中由游戏自己切），等画面重画。

    等的这一档就是第一版那个 `AFTER_TAP` —— 那 1.1 秒当初是等详情面板弹出来的，
    这一屏一样要等（面板要弹/收，牌面上那层灰罩也要重画）。
    """
    g.click(cell["cx"], cell["cy"])
    time.sleep(AFTER_TAP)


def undo(g, cell, tries=2):
    """把这一格"点回去"，直到面板回到"深色 ＋ 没卡名"。**先看后点**，已经回去了就不点。

    用在两处：`read_slot` 的正常收尾（读完之后点回去），以及它的出错收场
    （**别把选中留在屏上** —— 停在这一屏时要是还选着牌，接手的人看不明白是哪来的）。
    `tries=2` 是给"这一下点漏了"留的余量；先看后点保证不会多点（多点一下就又选上了）。
    """
    for _ in range(tries):
        _, name, mean = frame(g)
        if nothing_selected(mean, name):
            return True
        tap_slot(g, cell)
    _, name, mean = frame(g)
    return nothing_selected(mean, name)


def read_slot(g, cell):
    """点开一格读出卡名，**读完立刻点回去**（配对点击＝净效果为零，见上面 ②）。

    为什么非点不可：这一屏的卡面模板认不准（`nodes/cardpick.py` 模块 docstring 的实测），卡名只有
    "点开左边那块面板"一条路；而点一下又会改选中，所以只能点开→读→点回去。

    返回 `(卡名, 出问题的说明)`，卡名读准了说明是 None。每一步都带核对：

      · 点开后**面板得弹出来**（那一带亮度冲上去）。要是**这一下点漏了**
        （亮度还是深的、卡名也没有）→ 重点一次再读；
      · 面板弹着却读不出卡名（八成是张名单里认不出的牌）→ 报错，交调用方去停车；
      · 点回去之后**面板必须回到「深色 ＋ 没卡名」**（进来之前那一格已经核过
        "一张都没选"，配对点击净效果为零，点完必须还是）。回不去 ⇒ 这一下没点掉、
        选中被搅乱了 ⇒ 报错，**绝不带着它去点「确定」**。
    """
    key = (cell["row"], cell["col"])
    where = f"{key[0]}-{key[1]}"

    tap_slot(g, cell)
    _, name, mean = frame(g)
    if name is None and mean < PANEL_MIN:      # 面板压根没弹 = 这一下点漏了
        log(f"    选卡（最多3张）：{where} 点了一下，面板没弹（亮度 {mean:.1f}）—— 重点一次")
        tap_slot(g, cell)
        _, name, mean = frame(g)
    if name is None:                           # 面板那行字慢一拍，再等一档重读
        time.sleep(SLOT_REREAD)
        _, name, mean = frame(g)
    if name is None:
        back = undo(g, cell)
        return None, (f"{where} 点开了、可卡名读不出来（面板亮度 {mean:.1f}）"
                      f"，已{'点回去' if back else '点不回去'}")

    tap_slot(g, cell)                         # 点回去
    if not undo(g, cell):
        return None, (f"{where}「{name}」读到了，可再点一下**没收回去**"
                      "（面板还开着）—— 选中被搅乱了")
    return name, None


def wanted(g, cells_, rules, limit):
    """**按名字挑**：逐格读出卡名，把在 `rules.is_wanted()` 名单里的选上，最多 `limit` 个。

    给「往卡组里加牌」那两屏用（`ops/card_copy.py` 的复制屏、`ops/card_add.py` 的加入
    卡组屏）—— 用户 2026-10-15 加的第三条链，名单在 `script/cards/选择.json`。
    **这两屏共用同一个函数**：形状一模一样（逐格读名 → 挑名单里的 → 选上 → 点「确定」），
    不同的只有"上限几张"（`limit`）和"一张都没挑中时怎么办"（**那是调用方的事**，
    这个函数不管）。

    `cells_` 由调用方给（`cells(image)`）—— 切不出来是**另一回事**（那屏整个没读明白），
    出口归调用方，这个函数不替它决定。

    `limit` 之外的格子**读都不读**：读到第 `limit` 张就收工（一张 5 格的屏每格要
    2 次点击 + 每次 1.1s，能少读一格是一格）。

    → `(chosen, trouble)`：

      · `chosen` = `[((行, 列), 卡名)]`，**按读到（＝行优先）的顺序**，可能为空
        （名单里的牌屏上一张都没有）；形状与 `names()` 那个格式化函数、
        与 `ops/card_remove.py` 里那份 `chosen` 是同一个（日志才拼得出来）。
      · `trouble` = **`(出口后缀, 一句说明)`** 或 `None`（＝一切正常）。那一截后缀
        就是现场图名的尾巴 —— 调用方照它存图（`cardpick_select_<后缀>.png`），
        三种收场在事后一眼分得开：

          `"unknown"` = 哪一格读不明白（点漏了 / 卡名认不出 / 点不回去）；
          `"mismatch"` = 选上了，可面板上写的不是想拿的那张（格子表歪了）。

        非 None 时 `chosen` 里是**已经选上的那几张**（**不替调用方取消它们** ——
        调用方随即停车等人，屏上是什么样就让它是什么样，接手的人一眼看得见；
        偷偷点回去反而会在这个屏上留下没量过的动作）。

    **为什么用 `read_slot` 读、不用 `scan`**：`scan()` 是"每格单击一下"，扫完**最后那张
    还选着**，得靠 `clear_box` 补一下 —— 而"再点一下能取消"那条**在第一版那屏上没量过**
    （`clear_box` 的 docstring 自己写着）。这两屏是**要提交选中**的，把不该拿的牌留在
    选中里就是真拿了。`read_slot` 是**配对点击 + 每步核对**：点开必须弹面板、点回去必须
    回到深色，收不回去它自己就报 trouble。

    **选中之后要核一遍**（`cardpick_select_mismatch` 那条出口的由来）：名单说"要这张"，
    选上之后面板上得**还写着同一个名字**。对不上 = 这一点落到了别的格上（格子表歪了 /
    面板读到的是上一张的残留），**不猜、交出去停车**。

    ---- 为什么分两步走（先全读完、再回头选）----

    `read_slot` / `undo` 有一条**前提：进屏时格子上"一张都没选"** —— `undo` 的收尾就是
    "等到 `nothing_selected` 为真"，而它读的 `PANEL_BAND` 是**整块面板**：只要屏上已经
    选着任意一张，那一带就一直亮着，`undo` 永远等不到那个条件，于是**一路再点下去**
    （每多转一圈就多点一下，把更多格子选上）。所以"边读边选"会当场把这条链走坏。
    ⇒ 第一步全程只读（清一色配对点击，屏上一直是一张没选），第二步才逐格选上。
    """
    found = []                                   # 第一步：只读，屏上一直是"一张没选"
    for cell in cells_:
        where = f"{cell['row']}-{cell['col']}"
        name, trouble = read_slot(g, cell)
        if trouble:
            return [], ("unknown", f"{where}：{trouble}")
        if rules.is_wanted(name):
            found.append((cell, name))
            log(f"    选卡：{where}「{name}」在名单里（读到 {len(found)}/{limit} 张）")
            if len(found) >= limit:
                break
    if not found:
        return [], None

    chosen = []                                  # 第二步：把挑中的逐格选上
    for cell, want in found:
        tap_slot(g, cell)
        _, back, _ = frame(g)
        if back is None or base_name(back) != base_name(want):
            return chosen, ("mismatch",
                            f"{cell['row']}-{cell['col']} 想选「{want}」，可选上之后"
                            f"面板上写的是「{back or '（空）'}」—— 对不上")
        chosen.append(((cell["row"], cell["col"]), want))
    return chosen, None


def bands(profile, thr):
    """把一条投影曲线切成一维的连续区间 [(起, 止), ...]，太窄的丢掉。"""
    out = []
    start = None
    for i, v in enumerate(profile):
        if v > thr and start is None:
            start = i
        elif v <= thr and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(profile) - 1))
    return [(a, b) for a, b in out if b - a > BAND_MIN]


def cells(image):
    """网格里**有卡**的格子，按 行、列 排好。

    返回 [{"row": 1起, "col": 1起, "box": (x,y,w,h), "cx":, "cy":}, ...]。
    行/列都从 1 数，跟人看屏幕的习惯一致（"第 2 行第 1 个"）。
    """
    x0, y0, x1, y1 = GRID
    lum = image[y0:y1, x0:x1].astype(int).mean(axis=2)
    colb = bands((lum > LUM_ON).sum(axis=0), 25)
    rowb = bands((lum > LUM_ON).sum(axis=1), 25)

    out = []
    for ri, (ya, yb) in enumerate(rowb, 1):
        for ci, (xa, xb) in enumerate(colb, 1):
            cx, cy = x0 + (xa + xb) // 2, y0 + (ya + yb) // 2
            # 空位判定取正中一小块，避开卡片边框和相邻卡溢出来的光
            patch = image[cy - 30:cy + 30, cx - 30:cx + 30].astype(int).mean()
            if patch < CELL_MIN:
                continue
            out.append({
                "row": ri, "col": ci,
                "box": (x0 + xa, y0 + ya, xb - xa + 1, yb - ya + 1),
                "cx": cx, "cy": cy,
            })
    return out


def read_name(g, image=None):
    """读左侧详情面板里的卡名；没选中卡、或读出来的不像名字，返回 None。

    "像不像名字"那道闸（`looks_like_name`：至少两个汉字）住在 `shared/cards.py` ——
    商店销毁卡牌屏读的是同一块面板上的同一个问题（实测整片底色会被读成「一の」，
    score 0.161），两边共用一条判据。
    """
    if image is None:
        image = g.capture()
    reco = g.probe(卡牌名, image)
    if reco is None or not reco.best_result:
        return None
    text = (getattr(reco.best_result, "text", "") or "").strip()
    return text if looks_like_name(text) else None


def tap(g, cell):
    """点一张卡，返回它弹出来的卡名（读不到就是 None）。"""
    g.click(cell["cx"], cell["cy"])
    time.sleep(AFTER_TAP)
    return read_name(g)


def scan(g, image=None):
    """挨个点一遍，把每个格子和它的卡名对上。**十几秒**，但只改选中项、不改卡组。

    同一张卡在卡组里可能有多份（实测「无畏斧+」占了两格），这里原样列出，
    不去重——去重是调用方的事，脚本只负责"读到了什么"。
    """
    if image is None:
        image = g.capture()
    found = []
    for c in cells(image):
        name = tap(g, c)
        found.append(dict(c, name=name))
        log(f"    {c['row']}-{c['col']}  ({c['cx']},{c['cy']})  {name or '（读不出卡名）'}")
    return found


def clear_box(g, cards):
    """`scan()` 之后**把留在屏上那块卡牌信息框收掉**（2026-10-09 加，治根的那一半）。

    为什么会有块框挂在屏上：`scan()` 是"挨个点一遍读名字"，点到哪儿、哪儿就选着 ——
    扫完之后**最后点过的那张还选着**，左边那块卡牌详情就挂在那儿。第一版移除屏走
    「返回」那一条（一张可移除的都没有）时，这屏带着选中被关掉，而那块框**不会跟着
    走**（用户 2026-10-02：「不点掉就会一直挂着」）—— 它飘到下一屏去。2026-10-09
    撞上的就是它：飘到后面那张选卡屏上、盖住 `PANEL_BAND`，把"面板开着"这条判据
    骗了（现场帧 `cardpick_preselected.png`，那次的日志里就是"亮度 64.7、
    卡名「莽撞头槌+」"）。**第二版那条路有兜底**（`_remove_multi` 第 ① 步的光环判据），
    这里收的是源头。

    收法：把**最后点过的那格再点一下**（这一屏点一下＝选它、再点一下＝取消，与第二版
    同款；进 `scan()` 之前这屏是"一张都没选"，所以这一下要么取消选中、要么什么都不
    发生 —— **两种都不会选错牌**），然后看一眼面板收没收。

    ⚠️ 「再点一下能取消」在**第一版这屏上没量过**（量过的是第二版）。所以这里
    **只看一眼、只打日志**：收不掉也照常往下走（框留着是本条之前的行为，不是新错），
    不当成失败。

    收框这一下**恰好落在"要移除的那张"上**时（扫到的最后一张就是名单外那张）也不
    出事：两种语义下 `_remove` 紧接着那记 `pick` 都落在"那张牌选着"这个状态上 ——
    toggle 的话这一下先把它取消了、`pick` 再选上；不 toggle 的话这一下是空点、
    `pick` 那下（对已选中的牌）也是空点，牌一直选着。**四种组合都对得上**
    （2026-10-09 推的，C29 的场景是刻意避开这一格才写死的）。
    """
    if not cards:
        return
    last = cards[-1]
    g.click(last["cx"], last["cy"])
    time.sleep(AFTER_TAP)
    mean = panel(g.capture())
    if mean < PANEL_MIN:
        log("    移除屏：扫完最后那张再点一下，卡牌信息框收掉了")
    else:
        log(f"    移除屏：扫完最后那张再点一下，信息框还在（面板亮度 {mean:.1f}）—— 照常往下走")


def pick(g, cell):
    """点中某个格子（**不点确定**）。返回读到的卡名。"""
    name = tap(g, cell)
    log(f"    点中 {cell['row']}-{cell['col']}：{name or '（读不出卡名）'}")
    return name


def confirm(g):
    """点「确定」提交。**只有选过卡它才亮**，所以调用前必须已经点中过一张。

    判据用「选择卡牌」这个标题还在不在——点中了这屏就走掉了。
    """
    if not g.click_when(选卡确定, guard=(选择卡牌,)):
        log("    没找到「确定」")
        return False
    return g.wait_gone(选择卡牌, timeout=8)


def report(g, image=None):
    """只报格子、不动手（play() 用）。**不点任何卡**——选哪张是人的决定。"""
    if image is None:
        image = g.capture()
    cs = cells(image)
    log(f"    卡组 {len(cs)} 张，格子 行-列：")
    for c in cs:
        log(f"      {c['row']}-{c['col']}  点 ({c['cx']},{c['cy']})")
    return WAIT_CARD


def read_subtitle(g, image=None):
    """读卡组屏的副标题（「从卡组中选择一张卡牌移除。」这类）；读不到返回 None。

    **副标题是分派各版效果的判据**（见 `handle()`）。但**读不到不等于没有复制屏**：
    复制屏有两副卷面 —— 「不曾存在的往昔」→「“扔下它”」那版**没有**副标题
    （存档帧核过 hit=False），2026-10-04 撞到的那版写着「选择1张卡牌，复制2张加入
    牌组。」。所以 `handle()` 里是「读不到**或**带「复制」」都走复制屏那条路。
    """
    if image is None:
        image = g.capture()
    reco = g.probe(选卡副标题, image)
    if reco is None or not reco.best_result:
        return None
    return (getattr(reco.best_result, "text", "") or "").strip() or None


def describe(states):
    """把一格一格的状态串成一行给日志看（`5-2:washed` 这种），现场按它核。"""
    return " ".join(f"{k[0]}-{k[1]}:{v}" for k, v in sorted(states.items()))


def names(chosen):
    """`[(格位, 卡名)]` → 「1-1「隐痛」、1-2「莽撞头槌」」。"""
    return "、".join(f"{k[0]}-{k[1]}「{n}」" for k, n in chosen)
