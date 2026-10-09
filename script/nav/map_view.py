"""地图 —— 按优先级**自动选路**（用户 2026-10-02 改的规矩），走一步就交回主循环。

从前这里是"一个都不点、停车等人选"（用户起初要求「先不自动选」）。2026-10-02
用户说「我希望脚本自己选，按照优先级」，于是接上了 map.py 里那张早就备好的
优先级表（**那表也是用户 2026-10-01 亲自给的**，见 map.py 的 NODE_PRIORITY）。
同级取读图顺序第一个、优先表没定过的停下问人 —— 挑法与例外都写在
script/nav/map.py 的 pick_target()，本模块只负责执行与打印。

识别细节见 script/nav/map.py：`read_view` 自己连拍 6 帧取并集（箭头会闪烁），
那是**动作时刻的现场事实**，所以留在原地、不并进认屏表 —— 表只回答
"这是不是地图屏"（一个节点的事），"现在能去哪"是 handler 现读的事。
读不到就如实说读不到，**不猜**一个位置去点。

**读空了要重读**（`READ_TRIES`）：连拍取并集只护着**标记**，标签 OCR 每轮只吃
第一帧，标签漏读一次这个节点就整轮消失。实测漏读率约 1/3，读一次就停车
太脆。重读只在读空时才发生，正常一轮不多花时间。

**认不出、挑不出、走不动，都停在"等待选路"**（停车理由保持与旧版同字），
不同之处是日志里那几行会说清是哪一种。

**读空了先收一次残余信息框再判**（2026-10-03 加）：游艺结果面板弹的那块奖励说明
会一路骑到地图上（用户当天：「当前页面被上一次的游艺的信息阻挡了」），把标记和
标签全挡掉——那不是"没路"，是"看不见路"。收它的规矩用户 2026-10-02 就定过
（「点击其他空白地方恢复」「不点掉就会一直挂着」），2026-10-03 补了"单击、别双击"。
见 auto.clear_info_box()。

**再读不出来就滑屏幕换视角**（2026-10-03 加，用户：「给出一个保底机制, 在地图
识别不到时, 滑动屏幕」）。同上，那是"看不见路"而不是"没有路"：同一天 13:5x 那
一停里，屏上明明有一枚 0.774 的标记，它指的那个节点的标签却压在底栏下面没被
读出来 —— 把画面往上一拖，节点连标签一起进可视区。四个方向轮着拖，读到就交回
挑路（挑哪条**仍然只由 map.pick_target 按优先级决定**，拖屏幕不参与挑路）。
四方向全试完还是空才停车。细节与量准的数见下面 PAN_SWEEP_DIRS 那一段。

**走一步没走成，重读重挑再走**（2026-10-03 加，用户：「卡住了, 当前缺失重试
机制」）。上面那几道保底管的是"读空"，管不了"读出来的位置是错的" —— 见下面
GOTO_TRIES 那一段（现场：读到的点比真位置低了 64px，`goto` 按位置认节点、
认不出就不点，一下都没点就停车等人）。重试是**重读一帧、重新按优先级挑**，
不是拿着旧坐标再点一下。
"""

import time

from nav import map as mapmod
from strings import 地图界面
from shared.reasons import (
    WAIT_ROUTE,
    )
from shared.coords import PAN_SWEEP_DIRS
from shared.kit import log

# 标签落在地图区下沿外面（被底栏压着）时，**拖地图让它露出来**——用户 2026-10-03
# 定的做法（「字体在地图显示区域外面」）。拖够次数还不露就照旧往下走，别无限拖。
PAN_TRIES = 2

# 读空时重读几次。**不是预防性加的**：2026-10-02 在同一屏上连读 3 次实测 ——
# 2 次读到「篝火」并配上（分 0.786 / 0.783），1 次一个都读不到：那一次**标记
# 照样找到 1 枚，篝火的标签却没被 OCR 读出来**，配不上，整屏就报"没有可前往
# 节点"。read_view 的连拍取并集只用在**标记**上（防箭头闪），标签 OCR 只吃
# 第一帧（`_ocr_band` 兜底也吃同一帧），所以标签漏一帧 = 这个节点整轮消失。
# 原来读一次就停车，等于把约 1/3 的漏读率直接变成"停车等人"。
READ_TRIES = 3

# ============ 保底：读空到最后一刻，**滑动屏幕换个视角再看** ============
#
# 用户 2026-10-03 定的：「给出一个保底机制, 在地图识别不到时, 滑动屏幕」。
#
# 为什么非要它（同一天 13:5x 那一停的实测，debug/run_1003i.log 末尾）：
# 屏上**有一枚 0.774 的标记**（框 (795,525,40x47)，指着下方那枚节点），可它指的
# 那个节点的**标签压在底栏下面**（标签中心 y≈650，底栏从 662 起），整屏 OCR 没
# 读出这行字 —— 配不上，`reachable` 就是空的。而 bottom_dangling 那条兜底**没接住
# 它**：它只看"标记中心离下沿 110px 以内"，这枚标记中心 548、阈值 552，**差 4px**
# 落在界外。于是脚本报「没有可前往节点」停车等人。
#
# 判定：这是**"看不见路"，不是"没有路"**。把画面往上一拖，那枚节点连标签一起进
# 可视区，再读就有了 —— 所以拖屏幕**不是猜路**（挑哪条仍然只由 map.pick_target
# 按优先级决定），只是换个看得见的视角。**一枚都读不出、也没得拖** 时才停车。
#
# 方向与次数：一轮试四个方向，**"往上拖"排第一**。理由是已归档的几次读空都栽在
# "标签被底栏压住"（大商店、这一次的元素石碑那枚），把画面往上拖正是把它们抬出来
# 的那一下；左右是地图本身的走向（从左往右铺），下放最后只是补全。
# 每拖一次都**重新整读**（read_view 不带 markers 参数 = 重跑连拍取并集），因为
# 视角一动、标记位置全变，复用旧标记表就是拿错位置的框去配新一帧的字。
#
# 步长 `PAN_SWEEP_STEP` 与四方向表 `PAN_SWEEP_DIRS` 已搬进 `shared/coords.py`。

# ============ 走一步没走成 → **重读、重挑、再走** ============
#
# 用户 2026-10-03 22:50 那一停的原话：「卡住了, 当前缺失重试机制」。
#
# 现场（debug/screenshots/map_goto_fail.png + debug/run_1003_2248.log 末尾）：
#   脚本读到可前往 2 个，挑中「印记石 点 (801,303)」，`goto` 复读那一帧却在
#   同一带找不到它（它报的是标签框 (770,320,62,22)），于是**一个点击都没发**
#   就停车等人（理由「等待选路」）。而失败帧后来只读复读（`debug/map.py see`）
#   量到的是：标签 (798,267)、标记中心 (798,239) —— **那一次的读数比真位置低了
#   整整 64px**，两处证据（同一张失败帧 + 事后复读）互相吻合。
#
# 那 64px 从哪来（**推断**，没有"刚进地图那一下"的存档帧）：`read_view` 的**标签
# 只吃连拍的第 0 帧**（map.py:1477 `g.probe(地图节点文字, images[0])`），而第 0 帧
# 是**刚进地图、镜头还在滑**的那一帧；标记却是整段 5s 连拍取并集（map.py 的
# `_burst`）。镜头滑完标签位置就变了，而 `goto` 是**按位置**认节点的（见它的
# docstring：位置比标签文字硬）—— 位置对不上就不点，于是停车。
#
# 重试正好治它：第二遍读的第 0 帧已经是停稳的那一帧。**注意重试必须"重读 + 重挑"**，
# 不能拿着旧坐标再点一下 —— 旧坐标本身就是歪的那个（这也是 `goto` 自己修不了的
# 原因：它手上只有那个歪位置）。
#
# 次数取 3：一次 `goto` 最多花 20s（等地图关）+ 两趟连拍，3 次封顶约一分半，
# 比"停下车等人"便宜得多；真三次都走不成，那是地图/游戏真出事了，就该停车。
GOTO_TRIES = 3


def _reveal_dangling(g, view):
    """贴着下沿的节点：拖地图让它露出来，然后重读。返回拖完之后的 view。"""
    for n in range(PAN_TRIES):
        dangling = mapmod.bottom_dangling(view)
        if not dangling:
            break
        log(f"    有可前往节点贴着地图区下沿（{'；'.join(d for _b, d in dangling)}）")
        log(f"    —— 拖地图让它露出来（第 {n + 1}/{PAN_TRIES} 次）")
        mapmod.pan_to_reveal(g, dangling[0][0])
        time.sleep(1.2)  # 等镜头惯性停住，不然读到的是模糊的中间帧
        view = mapmod.read_view(g)
    return view


def _pan_sweep(g, view):
    """兜底：滑动屏幕换个视角，四个方向轮流试，读到可前往节点就交回。

    只在**读空之后**才跑（正常一轮一步都不多花）。全试完还是空，就把最后一帧
    的 view 交回去，由调用方按"读不到"停车。
    """
    for i, (name, dx, dy) in enumerate(PAN_SWEEP_DIRS, 1):
        log(f"    读空了 —— 滑动屏幕换个视角（第 {i}/{len(PAN_SWEEP_DIRS)} 次：往{name}拖）")
        mapmod.pan(g, dx, dy)
        # 等镜头惯性停住。这里**故意用固定 1.2s、不用 g.wait_still()**：地图上有
        # 飘动的雾，画面不一定真"停"，wait_still 可能一路等到超时白花十几秒 ——
        # 那条路在这个屏上没验过，别预防性上。这个 1.2s 与 _reveal_dangling 里
        # 那句同源（pan_to_reveal 的既有做法）。
        time.sleep(1.2)
        view = mapmod.read_view(g)
        if view["reachable"]:
            log(f"    → 拖完这一下读到了 {len(view['reachable'])} 个可前往节点")
            return view
    return view


def _read_until_visible(g, archive=True):
    """读到**看得见可前往节点**为止：重读 → 收残余信息框 → 四向拖屏幕 → 下沿再兜一次。

    返回最后那一次的 view —— 可能仍然是空的（那就由调用方按"读不到"停车，
    详细原因这里已经打出来了，理由里那几个数只有这里知道）。

    archive=True 时把那一眼存成 `battle_map.png`（这一屏的存档帧）；**重试时传
    False** —— 那一下不是为了存档，别拿它盖掉基线帧。
    """
    view = mapmod.read_view(g)

    # 有节点贴着地图区下沿 → 拖地图把它拖进来再读（见 map.py 的 bottom_dangling）。
    # 这一段排在挑路**之前**：标签读不出来就没法归类，也就没法按优先级挑。
    view = _reveal_dangling(g, view)

    tries = 1
    while not view["reachable"] and tries < READ_TRIES:
        tries += 1
        log(f"    地图上没读到可前往节点 —— 重读（第 {tries}/{READ_TRIES} 次）")
        if view["markers"]:
            # 标记这一批还在 → 缺的只是**字**（这一帧标签没读全），把标记表带过去
            # 重读一次就够了：不重跑 4 秒连拍（连拍只为标记取并集，而地图是静的，
            # 同一屏标记位置一颗都不挪）。省下的是每次重读约 10s → 约 0.5s。
            #
            # ⚠️ 这一条**只在"读空"时能用**：标记表是上一轮的**位置**，镜头一挪
            # （或上一轮读的本来就是歪的，见 GOTO_TRIES）它就全错了。走一步失败
            # 之后的重读**故意不带 markers**，就是为这个。
            view = mapmod.read_view(g, image=g.capture(), markers=view["markers"])
        else:
            # **一枚标记都没读到**时不能省连拍：那就是箭头全在暗相，只有再拍一遍
            # （也才可能盖到亮相段）才有救。
            view = mapmod.read_view(g)
    if archive:
        g.snap("battle_map")
    if not view["reachable"]:
        # 读空还可能是**屏上挂着一块残余信息框**（卡牌/物品/金币那类）把标记和
        # 标签挡了。用户 2026-10-03 的现场就是这么一次：「当前页面被上一次的游艺
        # 的信息阻挡了」—— 那块框是游艺结果面板弹的，脚本点什么按钮都不动它，
        # 一路骑到地图上，连读 3 次都是 0 个可前往。
        #
        # 收它的规矩用户 2026-10-02 就定过：「这是卡牌信息(或者如金币等信息)的残余,
        # **点击其他空白地方恢复**」「不点掉就会一直挂着」；2026-10-03 又补了
        # 「翻牌时不要双击」→ **单击**（地图上单击本来就安全，见 clear_info_box）。
        #
        # 这一步**不猜路**：只是"把挡视线的收掉，再读一眼"——读得出来就照常按
        # 优先级挑路，读不出来才停车（下面那段）。框本来就没上屏时点它也无害。
        log("    读空了 —— 先把残余信息框点掉，再读一次")
        g.clear_info_box()
        time.sleep(0.8)   # 框收掉有一小段淡出；没有节点可 wait_gone，就等这一下
        view = mapmod.read_view(g)

    # 最后一招：**滑动屏幕换个视角**（用户 2026-10-03 定的保底，见文件头 PAN_SWEEP_DIRS）。
    # 排在收信息框之后：那一步是"把挡视线的收掉"，这一步是"把视角挪到看得见的地方"，
    # 两件事互不代替。拖完可能又有标签贴到下沿，所以下沿那条兜底要再跑一遍。
    if not view["reachable"]:
        view = _pan_sweep(g, view)
        view = _reveal_dangling(g, view)

    if not view["reachable"]:
        log(f"    地图上没读到可前往节点（重读 {tries} 次、收起残余信息框、"
              f"{len(PAN_SWEEP_DIRS)} 个方向各拖一次，都没读到）")
    return view


def handle(g, hit):
    view = _read_until_visible(g)

    for attempt in range(1, GOTO_TRIES + 1):
        if not view["reachable"]:
            # 详细原因 _read_until_visible 已经打过了（那几个数只有它知道）
            return WAIT_ROUTE

        log(f"    可前往 {len(view['reachable'])} 个:")
        for i, r in enumerate(view["reachable"]):
            x, y = mapmod.icon_center(r["box"])
            # 屏幕上写的是 label，kind 是词典里那一条；两者不同时一起报
            # （别名废除后**只有形近字修正过时**才会不同，比如读到「黯淡簧火」）
            name = r["kind"] if r.get("label") in (None, r["kind"]) else f"{r['kind']}（{r['label']}）"
            log(f"      [{i}] {name:<6} prio={mapmod.priority(r['kind'])} 点 ({x},{y})")

        target, why = mapmod.pick_target(view["reachable"])
        if target is None:
            log(f"    {why}")
            return WAIT_ROUTE

        x, y = mapmod.icon_center(target["box"])
        nth = "" if attempt == 1 else f"（重试第 {attempt}/{GOTO_TRIES} 次）"
        log(f"    → {why}  点 ({x},{y}){nth}")
        ok, msg = mapmod.goto(g, target)
        log(f"    {msg}")
        if ok:
            return ""
        g.snap("map_goto_fail")
        if attempt == GOTO_TRIES:
            break

        # 没走成 → **重读、重挑、再走**（用户 2026-10-03：「当前缺失重试机制」，
        # 现场的 64px 偏移与为什么必须"重读"见上面 GOTO_TRIES 那一段）。
        log(f"    —— 这一步没走成：**重读地图、重新按优先级挑一条再走**"
              f"（第 {attempt + 1}/{GOTO_TRIES} 次）")
        time.sleep(0.8)   # 等镜头惯性/退场动画那点尾巴，别读一张糊的
        if not g.see(地图界面):
            # **头一下其实走成了**，只是地图关得慢（goto 那 20s 没等到）——
            # 那就别再点：交回主循环重新认屏。
            log("    （已经不在地图屏上了 —— 交回主循环）")
            return ""
        view = _read_until_visible(g, archive=False)

    log(f"    连着 {GOTO_TRIES} 次都没走出去 —— 停车等人"
        "（现场图 debug/screenshots/map_goto_fail.png）")
    return WAIT_ROUTE
