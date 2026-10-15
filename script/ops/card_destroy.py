"""卡牌操作小类 · **销毁**：商店点「移除卡牌」弹出那一屏「你的卡组」。

**这一屏的实测与策略记在 `script/nodes/deck.py` 的模块 docstring 里** ——
那一整段（怎么认格子、卡面先筛名字后验、两个出口、返回箭头没量过的那一条）
说的是这一屏，所以留在屏模块当索引；实现落在这儿，是因为"销毁"是个独立的
**操作**，而 `nodes/` 那一层放的是"哪一屏"。

⚠️ **它一行都没有用 `shared/grid.py`**：销毁面板的格子靠**笔触投影**切列、靠
**羊皮纸底色**排除空位，与选卡屏那套（亮度投影 + 写死的 5 列格位表）不是同一套
判据；卡名的读法也不同（这边的节点是 `销毁卡名`）。两屏长得像、判据不共用 ——
别为了"看着重复"把它们并成一份。
"""


import re
import time

import numpy as np

from strings import (你的卡组, 销毁卡名, 销毁价钱, 销毁按钮, 销毁返回, 商店界面,
                     金币数量)
from shared import gridstate
from shared.cards import (SCREEN_DECK, CardsConfigError, load_rules,
                         looks_like_name)
# 网格范围 / 三行格心 y / 归格半径 —— 固化坐标收在 shared/coords.py，import 回原名。
from shared.coords import DECK_GRID as GRID
from shared.coords import ROW_Y, SNAP
from shared.reasons import WAIT_CARDS_CONFIG, WAIT_DECK
from shared.kit import log, park

# 投影用的判据：**笔触**（相邻像素的亮度差）超过 EDGE_ON 算"这儿有东西"。
# 牌上有画、有边框、有字，笔触多；面板底色是平的，笔触少 —— 实测底色 5.6~10.3、
# 牌上 25.8。一列里过 EDGE_FRAC 的像素够多就算这一列落在牌上。
EDGE_ON = 12
#
# ⚠️ **EDGE_FRAC 是 0.25 改 0.10 的（2026-10-04）** —— 0.25 切在刀口上：
# 牌与牌之间那道真空隙实测掉到 **0.00~0.05**，可**牌自己身上**也能出现一条平的竖带
# （紫球的中段、斧柄那道），那条带实测就在 **0.25~0.28** —— 正好被 0.25 拦腰切断，
# 于是一张牌被切成**两列**。代价是两样：`cells()` 数出的格子不对，而且**会飘**
# （四帧存档实测：11 / 11 / 11 / **14** 格，那 14 就是两处切断各多出一格），
# 而"点完「销毁」看牌数少没少"那道闸正是拿这个数比的 —— 见 `_wait_card_gone`。
# 0.10 落在两个实测值中间（离 0.05 和 0.25 各留一倍余量），四帧跑下来**同一副牌
# 同 4 列、列心一模一样**（840/956/1071/1187），不再切。
EDGE_FRAC = 0.10

# 格子正中的颜色离底色多远才算"这儿有牌"。实测空位 0、最平的一张牌 61。
#
# ⚠️ **这三个数是 RGB 上的**（从**存盘帧**上量的：PIL 读 png 是 RGB）。
# 而 `Game.capture()` 给的是 **BGR**（见 `_rgb`）—— 两条路差一个换序，实测踩过。
PARCH = (178, 158, 128)
CELL_BG = 30

# 三行的格心 y（`ROW_Y`）与"命中框归格半径"（`SNAP`）已搬进 `shared/coords.py`。
# 行数为什么写死见 `nodes/deck.py` 的模块 docstring 末尾。

# 一条带子至少要多宽才算一列
BAND_MIN = 25

# 点一张牌之后详情面板要弹一下才写得出名字；第一次读不到就再等一档重读（不重点）
AFTER_TAP = 1.1
REREAD_WAIT = 0.8

# 点「销毁」之后等屏上变样（等牌数真少一张，见 `_wait_card_gone`）；
# 点「返回箭头」之后等面板走。
WAIT_DESTROY = 6.0
WAIT_BACK = 6.0
# `_wait_card_gone` 轮询的间隔（每轮要截一张图 + 认一眼面板在不在）
POLL_INTERVAL = 0.4
# 读网格时"等它稳住"的两张帧之间隔多久 / 最多等几轮（见 `_read_grid`）。
# 0.8s 取自实测：销毁一张之后面板要动上小一秒（牌烧掉、剩下的挪位），
# 两张帧隔 0.8s 还读到一模一样的格子，就当它停了。
SETTLE_GAP = 0.8
SETTLE_TRIES = 3

# 一趟的兜底上限：最多销毁这么多张 / 最多转这么多轮（防转圈 —— 正常一副牌
# 十来张，两个数都够用）。
MAX_DESTROY = 12
MAX_ROUNDS = 20

# 详情面板底下那行价钱有**两种写法**，钱的方向不一样（2026-10-04 实测两帧）：
#
#   普通牌  「支付 5金币，销毁该卡牌。」  按钮「销毁」  ← _deck_after_select.png（1-1 隐痛）
#   财宝牌  「获得 8金币，卖出该卡牌。」  按钮「卖出」  ← deck_click_stuck.png（1-3 金块，财宝8）
#
# 前者**花掉**、后者**进账**。策略是**照卖**（用户 2026-10-04：面板底下那枚按钮读
# 「卖出」时"照卖"）—— 于是那行读出来的是 `(钱数, 方向)` 而不是光一个数，两道判据
# （"钱够不够"、"点完核不核对"）都按方向走。
#
# 方向认**两组词**：领头词（支付/获得）是主判据，动词（销毁/卖出）是备份 ——
# OCR 偶尔漏字，两条任一对上就认得出，两条都看不出 = 读花了（`kind` 给 None，调用点停车）。
PRICE_PAY = "支付"
PRICE_GAIN = "获得"
PAY_WORDS = (PRICE_PAY, "销毁")
GAIN_WORDS = (PRICE_GAIN, "卖出")


def _rgb(image):
    """把 `Game.capture()` 的帧换成 **RGB** —— 本屏的颜色判据是在 RGB 上量的。

    实测（2026-10-04，同一帧、同一格）：

        capture() 在空位读到        [128 158 178]
        同一帧 snap() 存盘后读回来  [178 158 128]

    差的正是红蓝两通道 —— `snap()` 里写着 `Image.fromarray(capture()[:, :, ::-1])`
    （`core/auto.py:616`），也就是说 **capture 原样是 BGR、存盘帧是 RGB**，
    而 `PARCH` 当初是从存盘帧上量的（那一格 178 158 128 = 羊皮纸色）。

    **不换序的后果**（不是理论，是那两次停车）：空位离 PARCH 从 0 变成 **100**，
    远在 `CELL_BG = 30` 之上 —— 第 3 行的四个空位全被判成"有牌"，同一屏读出
    **12 格**（真牌只有 8 张），脚本挑到 3-1 一点一个空，卡名读不出来就停车
    （`deck_name_unknown.png`）。而存盘帧读出来永远是 8 格 —— 两边差的就是这一下换序。
    亮度类的判据（`_edges`、正中的 `.mean()`）与通道序无关，不受影响。
    """
    return image[:, :, ::-1]


def _edges(lum):
    """每个像素的"笔触"：左右、上下的亮度差之和。"""
    gx = np.abs(np.diff(lum, axis=1))
    gy = np.abs(np.diff(lum, axis=0))
    edge = np.zeros_like(lum)
    edge[:, :-1] += gx
    edge[:-1, :] += gy
    return edge


def _bands(profile, thr, minw):
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
    return [(a, b) for a, b in out if b - a > minw]


def cells(image):
    """网格里**有牌**的格子，按 行、列 排好。

    返回 [{"row": 1起, "col": 1起, "cx":, "cy":}, ...]。行/列都从 1 数，
    跟人看屏幕的习惯一致（"第 2 行第 1 个"）。怎么找的见 `nodes/deck.py` 的模块 docstring。
    """
    x0, y0, x1, y1 = GRID
    rgb = _rgb(image)                 # 颜色判据要 RGB，见 `_rgb`
    edge = _edges(rgb[y0:y1, x0:x1].astype(int).mean(axis=2))
    cols = _bands((edge > EDGE_ON).mean(axis=0), EDGE_FRAC, BAND_MIN)

    out = []
    for ri, cy in enumerate(ROW_Y, 1):
        for ci, (xa, xb) in enumerate(cols, 1):
            cx = x0 + (xa + xb) // 2
            patch = rgb[cy - 35:cy + 35, cx - 35:cx + 35].astype(int)
            if np.abs(patch - PARCH).sum(axis=2).mean() < CELL_BG:
                continue                       # 空位：这块就是底色
            out.append({"row": ri, "col": ci, "cx": cx, "cy": cy})
    return out


def _same_grid(a, b):
    """两张帧读出来的格子表是不是一模一样（行/列/格心三样都比）。"""
    key = lambda cs: [(c["row"], c["col"], c["cx"], c["cy"]) for c in cs]  # noqa: E731
    return key(a) == key(b)


def _read_grid(g):
    """读网格 —— **等它稳住**再算数：连着两张帧读到的格子一模一样才认。

    面板每销毁一张会重排一次，重排途中 `cells()` 读出来的是**过期的位置**（甚至凭空
    多出几格）。2026-10-04 实测栽过：上一张刚销毁、面板还在动的时候读到 12 格，
    脚本照着它点 3-1，点了个空 —— 卡名读不出来，停车等人（`deck_name_unknown.png`）；
    过一秒再拍同一屏，**其实是 8 张、第 3 行整个空着**。

    返回 (用哪一帧算的, 格子表)。等 `SETTLE_TRIES` 轮还稳不下来就返回 `(None, None)`
    —— **没稳住就不点**，由调用方停下留图，别拿一张还在动的表去点牌。
    """
    image = g.capture()
    last = cells(image)
    for _ in range(SETTLE_TRIES):
        time.sleep(SETTLE_GAP)
        image = g.capture()
        now = cells(image)
        if _same_grid(now, last):
            return image, now
        last = now
    return None, None


def protected(g, image, cs, rules):
    """卡面说"这一格是保留名单里的牌"的格子：{(行, 列), ...}。

    四条卡面模板各命中的框，按**中心离哪个格心最近**归到那一格（见 `SNAP`：
    归不上的不算数，只打日志）。调用方拿它当"别碰"的名单。

    **哪几张模板**由 `rules.keep_templates(SCREEN_DECK)` 给 —— 名字来自
    `script/cards/保留.json`（减掉 移除.json），名字 ↦ 卡面见 `shared/cards.py`
    的 `FACES`。`rules` 由 `run()` 在循环外取一次传进来（**别在这儿重载配置**：
    那会 N 次读盘，还会让"循环走到一半改了配置"变成半程换判据）。
    """
    out = set()
    for node in rules.keep_templates(SCREEN_DECK):
        for box, score in g.matches(node, image):
            cx, cy = box[0] + box[2] // 2, box[1] + box[3] // 2
            near = min(cs, key=lambda c: (c["cx"] - cx) ** 2 + (c["cy"] - cy) ** 2)
            if abs(near["cx"] - cx) > SNAP or abs(near["cy"] - cy) > SNAP:
                log(f"    ! {node} 命中在 ({cx},{cy})，离最近的格子"
                      f"（{near['row']}-{near['col']}）超过 {SNAP}px —— 不算它保护了哪一格")
                continue
            log(f"    {node} → 保住 {near['row']}-{near['col']}（score {score:.4f}）")
            out.add((near["row"], near["col"]))
    return out


def read_name(g, image=None):
    """读详情面板里那行卡名；没选中牌、或读出来的不像名字，返回 None。"""
    if image is None:
        image = g.capture()
    reco = g.probe(销毁卡名, image)
    if reco is None or not reco.best_result:
        return None
    text = (getattr(reco.best_result, "text", "") or "").strip()
    return text if looks_like_name(text) else None


def tap(g, cell):
    """点一张牌，返回它弹出来的卡名（读不到就是 None）。

    **点一张牌只是选中它**，不花钱也不改卡组（见 `nodes/deck.py` 的模块 docstring）。面板要弹一下才写得出
    名字，读不到就再等一档**重读**一次 —— 是重读不是重点：重点一遍等于换了张选中项。

    ⚠️ **点一下是"切换"，不是"选中"**：那一格**本来就选着**的时候，再点一下是**取消**，
    详情面板会整个消失。2026-10-04 实测撞上过：06:48 那次侦察点开 1-1 之后把游戏留在
    那一屏上，脚本接着跑、同一格再点一下 —— 读不到名字就停车了，现场图
    `deck_name_unknown.png` 里中间那块详情面板**是空的**（一张牌都没选中）。
    所以两档重读都读不到时**再点一下**：上一次点的要是"取消"，这一下就选回来。
    多点的这一下**不会销毁任何东西**（花钱只在「销毁」那一下），最坏也只是白点一下。

    为什么"多点半下"是安全的：**读到的名字和点的那一格其实不必对得上** ——
    后面选价钱、点「销毁」，动的都是**当前选中的那张牌**，也就是刚才读出名字的那张。
    所以这一路只认"屏上写着什么"，不依赖"我点的是哪一格"。
    """
    g.click(cell["cx"], cell["cy"])
    time.sleep(AFTER_TAP)
    name = read_name(g)
    if name is not None:
        return name
    time.sleep(REREAD_WAIT)
    name = read_name(g)          # 再读一次：也可能只是面板画得慢
    if name is not None:
        return name
    g.click(cell["cx"], cell["cy"])      # 还是读不到 → 那一格本来可能就选着（前一下取消了它）
    time.sleep(AFTER_TAP)
    return read_name(g)


def read_price(g, image=None):
    """读详情面板底下那行价钱，返回 `(钱数, 方向)`；读不到就是 `(None, None)`。

    方向：`"pay"`（「支付 N金币，销毁该卡牌。」＝**花掉**）/ `"gain"`（「获得 N金币，
    卖出该卡牌。」＝**进账**）—— 两种写法的来历与实测帧见上面那几条 `PRICE_*` 常量。
    数字读到了、方向却读不出来时给 `(N, None)`：**调用点据此停车**，不猜方向。

    **不调 `g.read_number` 的理由**：那行不光要数字、还要方向，两件事得从**同一帧的
    同一段原文**里读 —— 分两次 probe 会多花一次 OCR，而且两次可能读的不是同一段原文。
    抠数字那一步与 `read_number` 逐字一样（同样的 `hit` 闸、同样的 `all_results` 拼接、
    同样的 `\\d+`）。
    """
    reco = g.probe(销毁价钱, image)
    if not reco or not reco.hit:
        return None, None
    text = "".join(r.text for r in (reco.all_results or []))
    m = re.search(r"\d+", text)
    price = int(m.group()) if m else None
    if any(w in text for w in GAIN_WORDS):
        kind = "gain"
    elif any(w in text for w in PAY_WORDS):
        kind = "pay"
    else:
        kind = None
    return price, kind


def _wait_card_gone(g, expect, timeout=WAIT_DESTROY):
    """点完「销毁」/「卖出」之后等屏上真的变样，返回 (结果, 等了多久)。

    结果三种：

      `"cards"`  网格里的牌数比点之前**少了** —— 这一下生效了
      `"closed"` 面板整个收了 —— 也算生效（走"面板自己收掉"那条路）
      `"none"`   到点了还是原样 —— 那一下没生效

    ⚠️ **为什么必须"等"，不能点完立刻数**：2026-10-04 实测，点下去那一刻屏上
    **原样不动** —— 牌还在、金币还没扣、详情面板还挂着那张牌的名字。当时就是
    "点完马上重读、读到牌数没变"，被当成"那一下没生效"停了车；其实点着了：
    `deck_destroy_stuck.png`（07:37:50，牌还在、金币 29、名字还挂着）与
    `_deck_after_destroy.png`（07:40，**同一副牌**：那张愤怒之力没了、金币 24、
    详情面板空了）—— 中间没有任何人点过，纯粹是"变样要时间"。等多久由
    `WAIT_DESTROY` 兜着，等到了就把真实用时报进日志（这个数下次从日志里读）。

    面板那一眼用 `你的卡组`（实测 0.9998 的那条锚点）—— 少了它，面板一收，
    `cells()` 就会拿商店屏的底纹去切格子，数出一堆假格。
    """
    t0 = time.monotonic()
    while True:
        image = g.capture()
        if len(cells(image)) < expect:
            return "cards", time.monotonic() - t0
        if not g.see(你的卡组, image):
            return "closed", time.monotonic() - t0
        waited = time.monotonic() - t0
        if waited >= timeout:
            return "none", waited
        time.sleep(POLL_INTERVAL)


def _leave(g, why):
    """收工：点左上角那枚返回箭头退回商店屏，走人这件事交给商店那边。

    箭头点下去会到哪儿**没量过**，所以这里"点完之后看结果"，三条路见 `nodes/deck.py` 的模块 docstring。
    """
    if not g.see(你的卡组):
        gridstate.mark(False)      # 已经不在面板上了：告诉商店"该走了"
        return ""

    if not g.click_when(销毁返回, guard=(你的卡组,)):
        return park(g, WAIT_DECK, "deck_back_noclick",
                    f"销毁面板：{why}，该走了 —— 可左上角那枚返回箭头没找到/点不掉 —— 停下等人（已存 deck_back_noclick.png）")
    log(f"    → 返回箭头（{why}）")

    if not g.wait_gone(你的卡组, timeout=WAIT_BACK):
        return park(g, WAIT_DECK, "deck_back_stuck",
            "销毁面板：点了返回箭头，面板还在 —— 停下等人（已存 deck_back_stuck.png）")

    if g.see(商店界面):
        gridstate.mark(False)      # 商店据此点「离开地点」
        log("    销毁面板：已退回商店屏")
    else:
        gridstate.forget()         # 别把"该走了"那道旗留给下一家商店
        log("    销毁面板：退回之后站着的不是商店屏 —— 不写旗")
    return ""

def run(g, hit):
    """一趟「销毁会话」：把卡面认出来的**名单外**格子一张张销毁，直到没得销毁 / 金币不够。

    返回值只管"要不要停"（`""` = 处理完 / 非空 = 理由），走去哪了看 print。
    """
    try:
        rules = load_rules()       # 一趟会话读一次，往下传（循环里不重载）
    except CardsConfigError as exc:
        return park(g, WAIT_CARDS_CONFIG, "cards_config_broken",
            f"销毁面板：卡牌配置读不动（{exc}） —— 停下等人（已存 cards_config_broken.png）")

    gone = 0

    for _round in range(MAX_ROUNDS):
        image, cs = _read_grid(g)
        if cs is None:
            return park(g, WAIT_DECK, "deck_grid_unstable",
                "销毁面板：网格连着几张帧都在变（牌在挪位 / 上一张还在烧） —— 停下等人（已存 deck_grid_unstable.png）")
        if not cs:
            return park(g, WAIT_DECK, "deck_nogrid",
                "销毁面板：右边那块卡组网格一张牌都没读出来 —— 停下等人（已存 deck_nogrid.png）")

        keep = protected(g, image, cs, rules)
        free = [c for c in cs if (c["row"], c["col"]) not in keep]
        log(f"    销毁面板：网格 {len(cs)} 格，卡面认出保留名单里 {len(keep)} 格，"
              f"待核 {len(free)} 格")
        if not free:
            return _leave(g, "卡面认出来的格子全在保留名单里（没有可销毁的）")

        target = None
        for c in free:
            name = tap(g, c)
            if name is None:
                return park(g, WAIT_DECK, "deck_name_unknown",
                            f"销毁面板：{c['row']}-{c['col']} 那一格点开了，可卡名读不出来 —— 停下等人（已存 deck_name_unknown.png）")
            if rules.is_kept(name):
                log(f"    ! {c['row']}-{c['col']}：卡面说「名单外」，读出来却是"
                      f"「{name}」（保留名单里的）—— **以名字为准**，不动它")
                continue
            target = dict(c, name=name)
            break
        if target is None:
            return _leave(g, "卡面说名单外的那几格，点开一读名字全是保留名单里的牌"
                             "（没有可销毁的）")

        price, kind = read_price(g)
        if price is None:
            return park(g, WAIT_DECK, "deck_noprice",
                        f"销毁面板：挑中了「{target['name']}」，可底下那行价钱读不出来 —— 停下等人（已存 deck_noprice.png）")
        if kind is None:
            return park(g, WAIT_DECK, "deck_price_sign",
                        f"销毁面板：挑中了「{target['name']}」，价钱读到了 {price}，可那行**看不出是花掉还是进账**（该写「支付…销毁该卡牌」或「获得…卖出该卡牌」） —— 停下等人（已存 deck_price_sign.png）")
        gold = g.read_number(金币数量)
        log(f"    销毁面板：挑中 {target['row']}-{target['col']}「{target['name']}」，"
              f"这一张{'卖' if kind =='gain' else '销毁'} {price} 金币（手里 {gold}）")
        # 「金币不够」这道闸**只对花钱那一版**成立：「获得…卖出」是进账，钱越多越好。
        if kind == "pay" and gold is not None and gold < price:
            return _leave(g, f"金币不够（要 {price}、手里 {gold}）")

        # 点之前有几张牌 —— 点完拿它去等"少一张"（见 `_wait_card_gone`）。
        # **只在这一处比牌数**：从前在每轮开头也比一次（拿上一轮的 `expect`），
        # 2026-10-04 拆掉 —— 它和这里等的是同一件事，可它**不等**：卡组多到面板
        # 摆不下（只显 12 格）时，销毁一张牌数本来就不会变，它就会误报"卡住了"。
        before = len(cs)
        if not g.click_when(销毁按钮, guard=(你的卡组,)):
            return park(g, WAIT_DECK, "deck_click_stuck",
                "销毁面板：「销毁」/「卖出」没找到/点不掉 —— 停下等人（已存 deck_click_stuck.png）")
        gone += 1
        log(f"    → {'卖出' if kind =='gain' else '销毁'}「{target['name']}」"
              f"（这一趟第 {gone} 张）")

        # timeout 从调用点传（不在 `_wait_card_gone` 里写成默认参数）—— 这样它是
        # **每次读**模块常量，离线单测把 `card_destroy.WAIT_DESTROY` 改成 0 就能把这段压掉。
        how, waited = _wait_card_gone(g, before, timeout=WAIT_DESTROY)
        if how == "none":
            # 牌数没少 —— 先别急着判"那一下没生效"：卡组多到面板摆不下第 13 张时
            # （只显 12 格），销毁一张牌数也不变。**钱动了就是生效了**（价钱上面刚读过）——
            # 动的方向按 `kind` 看：花钱那版是**少**、进账那版是**多**。
            now = g.read_number(金币数量)
            moved = (now is not None and gold is not None
                     and (now < gold if kind == "pay" else now > gold))
            if not moved:
                return park(g, WAIT_DECK, "deck_destroy_stuck",
                            f"销毁面板：点过「{'卖出' if kind == 'gain' else '销毁'}」等了 {waited}s，网格里的牌数没少（还是 {before} 张）、金币也没动（{gold} → {now}） —— 停下等人（已存 deck_destroy_stuck.png）")
            log(f"    销毁面板：网格里没看出少一张，可金币 {gold} → {now}"
                  f"{'钱进账了' if kind == 'gain' else '钱扣了'}，当这一下生效")
        else:
            log(f"    销毁面板：{'牌数少了一张' if how =='cards' else '面板自己收掉了'}"
                  f"（点完 {waited:.1f}s）")

        nxt = g.wait_for((你的卡组, 商店界面), timeout=WAIT_DESTROY)
        if nxt is None:
            return park(g, WAIT_DECK, "deck_after_destroy",
                "销毁面板：点了「销毁」之后，面板和商店屏都不在 —— 停下等人（已存 deck_after_destroy.png）")
        if nxt == 商店界面:
            log("    销毁面板：销毁之后面板自己收掉了，回到商店屏")
            gridstate.mark(True)           # 还给商店：接着点「移除卡牌」
            return ""

        if gone >= MAX_DESTROY:
            return _leave(g, f"这一趟已经销毁 {MAX_DESTROY} 张（兜底，防转圈）")

    return _leave(g, f"转了 {MAX_ROUNDS} 轮还没收工（兜底，防转圈）")
