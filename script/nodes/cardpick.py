"""卡组网格屏（标题「选择卡牌」）：从自己的卡组里挑一张卡。

什么时候会撞上：
    2026-10-01 事件「不曾存在的往昔」选「“扔下它”」之后第一次见到，
    那一项的效果文字是「从卡组中选择一张卡牌复制加入到卡组中」。
    凡是"从卡组里挑一张"的效果（复制、刻印、升变……）大概率都是这个版式。

这一屏的**难点：卡面只有图，没有名字**。
    13 张卡排成 5+5+3 的网格，画面上除了标题「选择卡牌」和底部「确定」之外
    一个字都没有——OCR 读不出任何卡名。所以想**按名字**选卡，只有一条路：
    **先点它一下**，左边才会弹出一块详情面板，卡名写在面板中部的横幅上（大字）。
    也就是说"读名字"天生带副作用：会改变当前选中项、把「确定」点亮。
    这个副作用是**无害且可逆的**（只要不点「确定」，什么都不算数），但心里要有数。

怎么找格子（**不写死坐标**）：
    卡组大小每局都不一样（这一局 13 张），格子数会变，所以坐标靠投影现算：
    在整个卡片面板的范围里，按列/行统计"亮点"个数切出一条条带子，带子的交点就是格子。
    空位（不足一行的尾部）用**格子正中的平均亮度**排除——实测空位 29~32，
    最暗的一张卡（棕龙）也有 55，取 45 当线，两边都留了余量。

**策略——五种效果，靠副标题分派**（见 `handle()`）：

  · **复制屏（两副卷面，走同一条路）**：**默认拿第 1 张**（左上角，行 1 列 1）。
    两副卷面 = **没有副标题**的那版（事件「不曾存在的往昔」→「“扔下它”」）和
    **有副标题**「选择1张卡牌，复制2张加入牌组。」的那版（2026-10-04 事件「狭缝」
    → 第 2 格「“坠入”」第一次撞上）。用户 2026-10-02 在「残垣壁画 → 选第 2 格
    （"翻看四周"）→ 弹出这一屏」时给的回答就是四个字：「默认第一张」。
    ⚠️ **有副标题那版从前是按卡名挑的**（`COPY_CARD = 莽撞头槌`，用户 2026-10-04
    对这一屏的原话就三个字，走法见当时的 `_copy_named`：挨格点开读、读到就停）；
    **2026-10-06 用户改了口径** —— 原话「如果触发了选卡, 默认选第一张」，
    于是两版并成一条路（`_copy`），`_copy_named` / `COPY_CARD` /
    `cardpick_copy_nofind` 整个删掉。现在**与卡组里有什么牌无关**。
    这是**默认**不是"某张好牌"——要改就改 `PICK`。
  · **移除屏（第一版，单张）**（副标题「从卡组中选择一张卡牌移除。」）：用户
    2026-10-03 定的「选择 无畏斧,莽撞头槌,隐痛 之外的卡牌移除」——扫一遍挑一张
    **不在 `KEEP`** 的牌移除；一张可移除的都没有就点左上角「返回」取消
    （原话「如果没有, 则点击返回」）。
  · **移除屏（第二版，最多 3 张）**（副标题「选择最多3张卡牌，将其移除。」，
    2026-10-04 事件「狭缝」第一次撞上）：走法见 `_remove_multi`。**两版只差
    "最多"两个字，走法却差很多** —— 这一版点一张＝**加进选中**、最多 3 张、
    选完点「确定」才真移除，而且**没有「返回」**（出口只有底下那枚「确定」）。
    用户 2026-10-04 定的：「选择最多三张(可以不选)非指定牌进行移除, 选择完成后点击
    确认即可移除」+「可以不选择, 如果有非保留名单的牌, 就选择, 如果都是保留名单的牌,
    就一张都不选」。
  · **升级屏**（副标题「选择最多3张可升级卡牌，将其升级。」，2026-10-04 事件
    「狭缝」→ 第 2 格「“坠入”」之后撞上，是这一屏的第 5 个变体）：走法见
    `_upgrade` —— **一张都不选，直接点「确定」**（用户 2026-10-04 定的原话）。
    这一屏的牌是**居中排**的（存档帧 `cardpick_unknown_effect.png`：只有 2 张，
    列心 868/985、行心 221），与 `SLOTS` 那套 5 列格子不是一张表。

**这一屏只有一个入口：事件**（`event.py` 的效果，2026-10-01 起的路）。
从前这里还写着"商店的「移除卡牌」也走这一屏"——**那句话已经不成立了**：2026-10-04
那天「移除卡牌」真点下去，弹出的是**另一屏**（标题「你的卡组」，走法在
`nodes/deck.py`，认屏表里是独立的一行）。所以这一屏和商店再没关系，
跨屏那两格旗（`shared/gridstate.py`）也不许在这儿写。

**商店那条路的卡面认法不能照搬到这里**：`卡面.json` 那套模板是给销毁面板的 4 列
网格裁的，在这一屏的 5 列网格上分数掉到 0.73~0.91（实测，见 `debug/_cardtpl_check.py`）
—— 所以在这一屏上**还是只能挨个点开读名字**（`scan()`）。

`report()` 保留着，给"格子都读不出来"的兜底路用：那时候不猜，照旧停车等人。

选了哪张会**打进日志**（`pick()` 会读卡名）—— 事后核账就靠那一行。
"""

import time

import numpy as np

from strings import (卡牌名, 选卡_复制, 选卡_最多, 选卡_移除,
                    选卡_升级, 选卡副标题, 选卡返回, 选卡确定, 选择卡牌)
from shared.cards import KEEP, base_name, looks_like_name
# 面板范围 / 格位表 / 格心大小 / 详情面板带子 —— 固化坐标收在 shared/coords.py
#（1280x720 基准；换分辨率只看那个文件）。这里 import 回原名，使用点一字未动。
from shared.coords import CARD_GRID as GRID
from shared.coords import PANEL_BAND, SLOT_HALF, SLOT_X, SLOT_Y
from shared.reasons import (
    WAIT_CARD,
    WAIT_CARD_CONFIRM,
    )
from shared.kit import log, park

# 投影时"这一列/行上有卡"的亮度线，以及切出来的带子至少要多宽才算数
LUM_ON = 85
BAND_MIN = 25

# 格子正中 60x60 的平均亮度低于这条线 = 空位（见模块 docstring 的实测值）
CELL_MIN = 45

# 点一张卡之后，详情面板要等它弹出来才读得到卡名
AFTER_TAP = 1.1

# 默认挑哪一格：**行 1 列 1 = 左上角那张**（cells() 是按 行→列 排的，
# 所以它就是"第一张"）。用户 2026-10-02 定：「默认第一张」，2026-10-06 又把
# **带副标题那版复制屏**也并到这条路上（原话「如果触发了选卡, 默认选第一张」）。
# 要改成别的格子就把这行改掉；要按卡名挑见模块 docstring。
PICK = (1, 1)

# 移除屏的**保留名单**不在这个文件里了 —— 在 `shared/cards.py`（`KEEP` 是名字那份，
# `KEEP_TEMPLATES` 是卡面那份，商店的销毁卡牌屏两个都用）。
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
# （`_state_of`）。**注意"洗白"看的是标准差不是亮度**：它被罩得**更亮**、但更**平**。
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
#      （卡面模板在这一屏认不准，见模块 docstring，所以非点开不可）。
#   ③ **左边那块卡牌详情面板在不在**：一张都没选时面板**收起来**，那一带露出深色
#      空白；选着（哪怕只 1 张）面板就弹着。于是量「卡牌名」节点 roi 那一带
#      （`PANEL_BAND`）的平均亮度：实测"一张都没选"是 **0.9~4.2**（五帧），
#      "选着"是 **39.6~46.7**（四帧）—— 差着 10 倍，线取 20。
#
# 三条合起来，这屏能**确定**下来的只有三件事：**有灰罩 ⇒ 选满 3 张，且选中的就是
# 亮的那 3 张**；**面板关着 ⇒ 一张都没选**；**面板开着却没有灰罩 ⇒ 选着 1 或 2 张，
# 但看不出是哪几张（没判据）**。最后这一种不猜，停车等人（`cardpick_preselected`）。
#
# ⚠️ **不能拿 `read_name` 单独当"没选中"的判据**：k=0 时那一带露着事件正文
# （实测 k=0 那帧 roi 里是「你感受到了黄金野兽-帕特拉姆的存在」这种整句），
# 两个字以上的汉字 `looks_like_name` 全收。卡名要和亮度**一起看**（`_nothing_selected`）。
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
# 三帧各量一次（都是 15 个格心 60x60 的标准差，口径同 `_state_of`）：
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
# 差 0.6 就撞上了，那张牌会被读成"空位"，紧接着的 1-2 是张牌，`_holes` 当场判"读花了"。
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
# 那条带子的 roi 与 `assets/resource/pipeline/事件.json` 的 `卡牌名` 节点**同值但不同用**：
# 那边是喂给 OCR 的裁剪区，这边只量这一带有多少光（见上面 ③ 那段实测）。
PANEL_MIN = 20.0       # < 20 = 面板不在（实测"一张没选" 0.9~4.2）；>= 20 = 面板弹着（39.6~46.7）


def _patch(image, cx, cy, half=SLOT_HALF):
    """格心那一小块（亮度图）。**取通道均值，与通道序无关**，所以 BGR/RGB 都行。"""
    return image[cy - half:cy + half, cx - half:cx + half].astype(int).mean(axis=2)


def _state_of(patch):
    """一小块是三种状态里的哪一种（分界线见 `SLOT_FLAT` / `SLOT_WASHED`）。"""
    s = float(patch.std())
    if s < SLOT_FLAT:
        return "empty"
    return "full" if s >= SLOT_WASHED else "washed"


def _slots():
    """这一屏 **5 列 × 3 行**的格位表（**只有位置，没有状态** —— 状态要现截现读）。

    牌不到 11 张时第 3 行是空位（量出来 0.6~2.0），照样在表里 —— `empty` 不占
    `occupied`，多出来的格子不花钱。"""
    return [{"row": ri, "col": ci, "cx": cx, "cy": cy}
            for ri, cy in enumerate(SLOT_Y, 1)
            for ci, cx in enumerate(SLOT_X, 1)]


def _states(image, cells=None):
    """一帧上每格是三种状态里的哪一种：`{(行,列): "empty"|"washed"|"full"}`。

    默认拿这一屏写死的那 10 个格位（`_slots()`）去量。
    """
    return {(c["row"], c["col"]): _state_of(_patch(image, c["cx"], c["cy"]))
            for c in (cells or _slots())}


def _panel(image):
    """左边详情面板那一带（`PANEL_BAND`）的平均亮度。**与通道序无关**（取通道均值）。"""
    x, y, w, h = PANEL_BAND
    return float(image[y:y+h, x:x+w].astype(int).mean(axis=2).mean())


def _nothing_selected(mean, name):
    """**"一张都没选"的判据：亮度与卡名两条一起看**（来历见上面 ③ 那段实测）。

    为什么非要两条：k=0 时那条带子上露着的是**事件正文**，光看卡名会把
    「你感受到了黄金野兽-帕特拉姆的存在」当成卡名（`looks_like_name` 只要两个汉字，
    它全收）；光看亮度又怕别的屏上那一带本来就亮。**两条都指向"面板不在"才算数。**
    """
    return mean < PANEL_MIN and name is None


def _frame(g):
    """**现截一帧**，报 `(每格状态, 面板上的卡名, 面板那一带的亮度)`。

    一帧只截一次：三样都从**同一帧**上读（卡名那个 roi 也在这帧上，`read_name`
    收现成的帧就不再自己截）。这一屏"一格的长相会随选中变"，所以每次动手前后
    都得重看一眼，**不缓存**。
    """
    image = g.capture()
    return _states(image), read_name(g, image), _panel(image)


# 从前这儿有个 `_no_extra_rows()`：格位表只有两行，就把它当哨兵，拿 y=553 那一带
# 探"这儿还有没有牌"，一见有牌就停车等人（理由 `cardpick_third_row`）。
# **2026-10-04 撞上 12 张那局（`cardpick_third_row.png`）量明白它是多余的** ——
# 第 3 行用的就是同一套格位（见 `SLOT_Y` 上面那段实测），哨兵挡掉的是本来就该走的路。
# 函数与那条停车理由一起删了，**别再把它加回来**。


def _holes(states):
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


def _tap_slot(g, cell):
    """点一格（选中↔取消选中由游戏自己切），等画面重画。

    等的这一档就是第一版那个 `AFTER_TAP` —— 那 1.1 秒当初是等详情面板弹出来的，
    这一屏一样要等（面板要弹/收，牌面上那层灰罩也要重画）。
    """
    g.click(cell["cx"], cell["cy"])
    time.sleep(AFTER_TAP)


def _undo(g, cell, tries=2):
    """把这一格"点回去"，直到面板回到"深色 ＋ 没卡名"。**先看后点**，已经回去了就不点。

    用在两处：`_read_slot` 的正常收尾（读完之后点回去），以及它的出错收场
    （**别把选中留在屏上** —— 停在这一屏时要是还选着牌，接手的人看不明白是哪来的）。
    `tries=2` 是给"这一下点漏了"留的余量；先看后点保证不会多点（多点一下就又选上了）。
    """
    for _ in range(tries):
        _, name, mean = _frame(g)
        if _nothing_selected(mean, name):
            return True
        _tap_slot(g, cell)
    _, name, mean = _frame(g)
    return _nothing_selected(mean, name)


def _read_slot(g, cell):
    """点开一格读出卡名，**读完立刻点回去**（配对点击＝净效果为零，见上面 ②）。

    为什么非点不可：这一屏的卡面模板认不准（模块 docstring 的实测），卡名只有
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

    _tap_slot(g, cell)
    _, name, mean = _frame(g)
    if name is None and mean < PANEL_MIN:      # 面板压根没弹 = 这一下点漏了
        log(f"    选卡（最多3张）：{where} 点了一下，面板没弹（亮度 {mean:.1f}）—— 重点一次")
        _tap_slot(g, cell)
        _, name, mean = _frame(g)
    if name is None:                           # 面板那行字慢一拍，再等一档重读
        time.sleep(SLOT_REREAD)
        _, name, mean = _frame(g)
    if name is None:
        back = _undo(g, cell)
        return None, (f"{where} 点开了、可卡名读不出来（面板亮度 {mean:.1f}）"
                      f"，已{'点回去' if back else '点不回去'}")

    _tap_slot(g, cell)                         # 点回去
    if not _undo(g, cell):
        return None, (f"{where}「{name}」读到了，可再点一下**没收回去**"
                      "（面板还开着）—— 选中被搅乱了")
    return name, None


def _bands(profile, thr):
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
    colb = _bands((lum > LUM_ON).sum(axis=0), 25)
    rowb = _bands((lum > LUM_ON).sum(axis=1), 25)

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


def handle(g, hit):
    """这一屏的入口。**四种效果共用这个版式**，靠副标题分派：

      · 副标题里有「移除」**也有「最多」**→ **第二版移除屏**
        （「选择最多3张卡牌，将其移除。」，2026-10-04 事件「狭缝」第一次撞上）。
        走法见 `_remove_multi`：选最多 3 张非保留牌 → 点「确定」（可以不选）。
        **这一版没有「返回」**，所以它必须排在下面那条前面认领。
      · 副标题里有「移除」**没有「最多」**→ **第一版移除屏**
        （「从卡组中选择一张卡牌移除。」，事件「陈旧的信仰」→「“仰望它”」）。
        用户 2026-10-03 定的：扫一遍卡组，挑一张**不在 KEEP 里**的牌移除；
        一张可移除的都没有 → 点左上角「返回」取消（原话「如果没有, 则点击返回」）。
      · 副标题**读不到**、或者里面有「复制」→ **复制屏（两副卷面同一条路）**
        （没副标题那版：事件「不曾存在的往昔」→「“扔下它”」；
         有副标题「选择1张卡牌，复制2张加入牌组。」那版：2026-10-04 事件
         「狭缝」→ 第 2 格「“坠入”」第一次撞上）。
        照旧：按 `PICK` 取第一张（用户 2026-10-02「默认第一张」；
        2026-10-06 把有副标题那版也并了过来 —— 从前的按卡名挑已删）。
      · 副标题里有「升级」→ **升级屏**
        （「选择最多3张可升级卡牌，将其升级。」，2026-10-04 事件「狭缝」→ 第 2 格
        「“坠入”」第一次撞上 —— 与上面那条是同一个入口，落到哪一屏看运气）。
        走法见 `_upgrade`：**一张都不选，直接点「确定」**。
      · 副标题读到了、上面几条都不沾 → 没见过的一屏，**不猜**，停车等人。

    **分派靠先认哪个词**：「移除」排在最前（这一屏的五版里只有那两版带「移除」），
    升级屏那行**同时带「最多」和「升级」** —— 万一将来出现「…已升级卡牌，将其移除。」
    这种卷面，先认「移除」也照样把它送回移除那条路。

    **读不出格子时不猜**：切不出格子/空位全被滤掉，是"这屏没读明白"，照旧只报
    不动、停车等人（跟从前一样）。
    """
    image = g.capture()
    sub = read_subtitle(g, image)

    if sub is not None and 选卡_移除 in sub:
        if 选卡_最多 in sub:
            return _remove_multi(g)
        return _remove(g, image)
    if sub is None or 选卡_复制 in sub:
        return _copy(g, image)
    if 选卡_升级 in sub:
        return _upgrade(g)

    return park(g, WAIT_CARD, "cardpick_unknown_effect",
                f"选卡：副标题读到了「{sub}」 —— 既不是移除、也不是（无） —— 停下等人（已存 cardpick_unknown_effect.png）")


def _upgrade(g):
    """升级屏：「选择最多3张可升级卡牌，将其升级。」→ **一张都不选，直接「确定」**。

    2026-10-04 事件「狭缝」→ 第 2 格「“坠入”」→「确认选择」之后撞上，是这个入口的
    **第二个落点**（同一次「坠入」有时进首领战、有时进复制屏、有时进这一屏）。
    第一趟撞上时它落进"没见过的一屏"停车等人（现场帧
    `cardpick_unknown_effect.png`），问过用户，他定的走法就是：「一张都不选，
    直接「确定」」；张数规矩「照「可以不选」先办」。

    所以这里**一格都不读、也不点**。这一屏的牌是**居中排**的 —— 存档帧上只有
    2 张，量下来的列心是 **868 / 985**（间距 117，和 5 列那套一样、整块却是以
    x≈926 居中的），行心 **y≈221**；`SLOTS` 那套写死的列心是 692/809/926/1043/1160，
    在这一屏上对不上，`cells()` 按投影切也只会切出这两格（真要看格子得另写一张表）。
    反正这一趟一张都不选，**格子读不读都不影响这次的动作**，索性不读。

    **"没选任何牌时点「确定」算不算数"这一屏没量过**（存档帧上那枚「确定」是亮的），
    但同一套版式的第二版移除屏量过：用户定的「可以不选择…就一张都不选」＋
    「取消选中再点「确定」」在那儿就是这么走的。点不掉、或者点了这屏不走
    —— **不猜，停车等人**（现场图名分开写着是哪一件）。

    **2026-10-06 又量到一条（另一个落点）**：升级屏还有**面板版** —— 副标题
    「选择卡组中1张牌升级」，只盖住地点屏右半边（第一次见是在篝火上，用户当天
    补的话：「对于可能出现的升级, 直接点击确定就可以了」）。那一屏上**一张都没选、
    直接点「确定」，游戏受理**：`debug/run_1006_0730.log` 里点完面板就收掉、回到
    篝火，接着「激活护符」就点得动了。也就是说这一支在这副卷面上是有出口的
    （认屏表里它归 `选卡屏` 认领，见 script/recognizer.py 那一行）。
    """
    log("    选卡（升级）：一张都不选，直接点「确定」")
    if not g.click_when(选卡确定, guard=(选择卡牌,)):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_upgrade_noconfirm",
            "选卡（升级）：「确定」没找到/点不掉 —— 停下等人（已存 cardpick_upgrade_noconfirm.png）")
    if not g.wait_gone(选择卡牌, timeout=8):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_upgrade_stuck",
            "选卡（升级）：点了「确定」这屏还在（一张都没选） —— 停下等人（已存 cardpick_upgrade_stuck.png）")
    log("    选卡（升级）：已提交（这一趟一张都没选）")
    return ""


def _copy(g, image):
    """复制屏：按 `PICK` 选一张、点「确定」提交（用户 2026-10-02「默认第一张」）。

    这是**默认策略不是识别** —— 要改就改 `PICK` 那个常量（或换成模块 docstring
    里说的偏好表）。
    """
    cs = cells(image)
    target = next((c for c in cs if (c["row"], c["col"]) == PICK), None)
    if target is None:
        g.snap("cardpick_nogrid")
        log(f"    选卡：读不出 {PICK[0]}-{PICK[1]} 这一格（本屏读出 {len(cs)} 格）")
        return report(g)

    log(f"    选卡（复制）{len(cs)} 张，按默认取第 {target['row']}-{target['col']} 格")
    pick(g, target)
    if not confirm(g):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
            "选卡：卡选中了、但「确定」没点掉 —— 停下等人")

    log("    选卡：已提交")
    return ""


def _remove(g, image):
    """移除屏：挑一张不在 KEEP 里的牌移除；一张都没有 → 点左上角「返回」取消。

    先 `scan()` 把每张卡点一遍读名字（只改选中项、不提交，见模块 docstring）。
    **读不出名字的格子不碰**（可能是名单里的牌，猜不得）：
      · 有**读得准**的名单外牌 → 移它（取行→列的第一张）。
      · 一张名单外牌都没有、又没有读不出的格子 → 确实全保留了 → 点「返回」。
      · 有读不出的格子、又没有名单外牌 → 分不清是不是"全保留了"，**不猜**，停车。
    """
    cards = scan(g)
    if not cards:
        return park(g, WAIT_CARD, "cardpick_nogrid",
            "移除屏：一张卡都没读出来 —— 停下等人（已存 cardpick_nogrid.png）")

    unknown = [c for c in cards if not c["name"]]
    outside = [c for c in cards if c["name"] and base_name(c["name"]) not in KEEP]

    if outside:
        t = outside[0]
        log(f"    移除屏：{len(cards)} 张里，名单外的「{t['name']}」排在第一张"
              f"（{t['row']}-{t['col']}）→ 移它")
        pick(g, t)
        if not confirm(g):
            return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
                "移除屏：选中了、但「确定」没点掉 —— 停下等人")
        log(f"    移除屏：已移除「{t['name']}」")
        return ""

    if unknown:
        where = "、".join(f"{c['row']}-{c['col']}" for c in unknown)
        return park(g, WAIT_CARD, "cardpick_remove_unknown",
                    f"移除屏：没有名单外的牌，但有 {len(unknown)} 张名字读不出（{where}） —— 停下等人（已存 cardpick_remove_unknown.png）")

    log(f"    移除屏：{len(cards)} 张全在保留名单里（{'、'.join(KEEP)}）"
        " —— 没有可移除的，点左上角「返回」取消")
    if not g.click_when(选卡返回, guard=(选择卡牌,)):
        return park(g, WAIT_CARD, "cardpick_noback",
            "移除屏：「返回」没找到/点不掉 —— 停下等人（已存 cardpick_noback.png）")
    if not g.wait_gone(选择卡牌, timeout=8):
        return park(g, WAIT_CARD, "cardpick_back_stuck",
            "移除屏：点了「返回」这屏还在 —— 停下等人（已存 cardpick_back_stuck.png）")
    log("    移除屏：已返回（这一项没移除任何牌）")
    return ""


def _remove_multi(g):
    """第二版移除屏：「选择最多3张卡牌，将其移除。」（用户 2026-10-04 定的走法）。

    **不接 `handle()` 递进来的那一帧**：这一屏一格的长相会随"选没选中"变，
    每一步动手前后都得现看一帧（`_frame`），拿旧帧做的判断没有意义。

    **走法**（每一步读不明白都停车，**绝不带着没核过的选中去点「确定」**——
    那一下是真移除，点错了牌就没了）：

      ① **先把选中清成一个"确定的 0"**：有灰罩 ⇒ 选满 3 张、且知道就是亮的那 3 张
         （**灰罩在、全对比的却不是恰好 3 格 ⇒ 这一帧读花了，停车** `cardpick_wash_mismatch`）
         ⇒ 挨个点掉 ⇒ 核"面板关着"；没灰罩、面板也关着 ⇒ 本来就是 0，一步不用点；
         没灰罩、**面板却开着** ⇒ 选着 1~2 张而看不出是哪几张 ⇒ **停车**
         （`cardpick_preselected`）——没判据就不猜，乱点会把不该移除的牌选上。
      ② **读一遍卡名**（`_read_slot`：点开→读→点回去，配对点击净效果为零），挑出
         **不在保留名单**的牌，最多 `SLOT_LIMIT` 张；名单里的牌原样放过。
         凑够 3 张就不再读后面的了（封顶就 3 张，后面的名字用不上）。
      ③ **选上、核对、提交**：逐张点选，再读一帧核对（**选满 3 张时灰罩能逐张核对
         身份**，不足 3 张时核"面板开着/关着"这条粗的），然后点「确定」等这屏走掉。

    "一张都不选"是**正路不是异常**（用户原话「可以不选择」）：全是保留名单里的牌
    时，第 ② 步一张都不选，第 ③ 步核"面板关着"，照样点「确定」走人
    （用户原话「取消选中再点「确定」」）。
    """
    cells = _slots()
    by_key = {(c["row"], c["col"]): c for c in cells}

    states, name, mean = _frame(g)
    if _holes(states):
        return park(g, WAIT_CARD, "cardpick_nogrid",
                    f"选卡（最多3张）：格子读花了（{_describe(states)}） —— 停下等人（已存 cardpick_nogrid.png）")
    occupied = [c for c in cells if states[(c["row"], c["col"])] != "empty"]
    if not occupied:
        return park(g, WAIT_CARD, "cardpick_nogrid",
                    f"选卡（最多3张）：一张牌都没读到（{_describe(states)}） —— 停下等人（已存 cardpick_nogrid.png）")

    # ---- ① 把选中清成"确定的 0" ----
    if any(v == "washed" for v in states.values()):
        lit = sorted(k for k, v in states.items() if v == "full")
        # "有灰罩"和"亮着 3 张"是**同一件事的两面**（上限 3 张 + 灰罩只在选满时渲染，
        # 两条都是实测量出来的，见上面 ①②）。对不上就说明这一帧读花了 —— 这一屏
        # 唯一能把选中清干净的办法是"挨个点掉亮着的那几张"，数不对就会点到不该点的
        # 牌上，所以**不猜，停车**。（2026-10-04 之前没有这道闸，是因为 `SLOT_WASHED`
        # 那条线切在牌的群里、会凭空造出"洗白"，见那个常量上面那段。）
        if len(lit) != SLOT_LIMIT:
            return park(g, WAIT_CARD, "cardpick_wash_mismatch",
                        f"选卡（最多3张）：屏上有洗白（＝选满了），可全对比的却是 {len(lit)} 格（{_describe(states)}） —— 停下等人（已存 cardpick_wash_mismatch.png）")
        where = "、".join(f"{k[0]}-{k[1]}" for k in lit)
        log(f"    选卡（最多3张）：这屏进来时就选满 {len(lit)} 张（{where}）—— 先挨个点掉")
        for key in lit:
            _tap_slot(g, by_key[key])
        states, name, mean = _frame(g)
        if not _nothing_selected(mean, name):
            return park(g, WAIT_CARD, "cardpick_undeselect",
                        f"选卡（最多3张）：想把已经选着的清掉，可点完 {'还剩灰罩' if any((v == 'washed' for v in states.values())) else '面板还弹着'}（{_describe(states)}，面板亮度 {mean}） —— 停下等人（已存 cardpick_undeselect.png）")
        log("    选卡（最多3张）：已清空选中")
    elif not _nothing_selected(mean, name):
        return park(g, WAIT_CARD, "cardpick_preselected",
                    f"选卡（最多3张）：这屏进来时**面板弹着、却没有灰罩**（亮度 {mean}，卡名「{name}」） —— 停下等人（已存 cardpick_preselected.png）")
    else:
        log("    选卡（最多3张）：进来时一张都没选")

    # ---- ② 读一遍卡名，挑出不在保留名单的牌 ----
    chosen = []          # [(格位, 卡名)]，按读到的先后
    for c in occupied:
        if len(chosen) >= SLOT_LIMIT:
            log(f"    选卡（最多3张）：已经挑出 {SLOT_LIMIT} 张可移除的，后面的不读了")
            break
        key = (c["row"], c["col"])
        name, trouble = _read_slot(g, c)
        if trouble:
            return park(g, WAIT_CARD, "cardpick_name_unknown",
                        f"选卡（最多3张）：{trouble} —— 停下等人（已存 cardpick_name_unknown.png）")
        if base_name(name) in KEEP:
            log(f"    选卡（最多3张）：{key[0]}-{key[1]}「{name}」在保留名单里 —— 原样放过")
            continue
        chosen.append((key, name))
        log(f"    选卡（最多3张）：{key[0]}-{key[1]}「{name}」不在保留名单里"
              f" —— 记下（第 {len(chosen)}/{SLOT_LIMIT} 张）")

    # ---- ③ 选上、核对、提交 ----
    want = {key for key, _ in chosen}
    for key, _ in chosen:
        _tap_slot(g, by_key[key])
    states, name, mean = _frame(g)
    lit = {k for k, v in states.items() if v == "full"}
    if any(v == "washed" for v in states.values()):
        # 选满 3 张灰罩才出来 —— 这是**唯一**能逐张核对身份的时刻
        if lit != want:
            return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                        f"选卡（最多3张）：打算选 {_names(chosen) or '不选'}，屏上亮着的却是 {'、'.join((f'{k[0]}-{k[1]}' for k in sorted(lit))) or '不选'} —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif len(want) == SLOT_LIMIT:
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：点了 {SLOT_LIMIT} 张可移除的，屏上却没出现灰罩 —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif want and _nothing_selected(mean, name):
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：打算选 {len(want)} 张，屏上却像一张都没选（面板没弹） —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif not want and not _nothing_selected(mean, name):
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：一张都不打算选，可屏上还选着（面板弹着，亮度 {mean}） —— 停下等人（已存 cardpick_pick_mismatch.png）")

    if chosen:
        log(f"    选卡（最多3张）：共选 {len(chosen)} 张（{_names(chosen)}）→ 点「确定」")
    else:
        log("    选卡（最多3张）：一张可移除的都没有（全在保留名单里）"
            " —— 不选，直接点「确定」走人")
    if not confirm(g):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
            "选卡（最多3张）：选完了、可「确定」没点掉 —— 停下等人（已存 cardpick_noconfirm.png）")

    log(f"    选卡（最多3张）：已提交（移除 {len(chosen)} 张：{_names(chosen) or '无'}）")
    return ""


def _describe(states):
    """把一格一格的状态串成一行给日志看（`5-2:washed` 这种），现场按它核。"""
    return " ".join(f"{k[0]}-{k[1]}:{v}" for k, v in sorted(states.items()))


def _names(chosen):
    """`[(格位, 卡名)]` → 「1-1「隐痛」、1-2「莽撞头槌」」。"""
    return "、".join(f"{k[0]}-{k[1]}「{n}」" for k, n in chosen)
