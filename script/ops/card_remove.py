"""卡牌操作小类 · **移除**：两副卷面，判据只差"最多"两个字，走法差很多。

两份名单都在 `script/cards/`（`保留.json` / `移除.json`），判据在 `shared/cards.py`
的 `Rules.is_removed`（**移除优先**，然后是"不在保留里"）。

  · `run`       —— 第一版（副标题「从卡组中选择一张卡牌移除。」）：
    扫一遍挑一张**要移除**的牌移除；一张可移除的都没有就点左上角「返回」。
  · `run_multi` —— 第二版（副标题「选择最多3张卡牌，将其移除。」）：
    点一张＝**加进选中**（最多 3 张、可以不选），选完点「确定」；
    **这一版没有「返回」**，所以分派时它必须排在 `run` 前面认领。

两版都是用户 2026-10-03 / 2026-10-04 定的（原话见各自函数的 docstring）。
共用的东西 —— 格位、选中判据、点「确定」—— 全在 `shared/grid.py`。
"""

import time

from strings import 选卡返回, 选择卡牌
from shared import grid
from shared.cards import CardsConfigError, load_rules
from shared.coords import CARD_BLANK
from shared.reasons import WAIT_CARD, WAIT_CARD_CONFIRM, WAIT_CARDS_CONFIG
from shared.kit import log, park


def run(g, image):
    """移除屏：挑一张"要移除"的牌移除；一张都没有 → 点左上角「返回」取消。

    "要移除"由 `script/cards/` 那两张配置算出来（`rules.is_removed`：`移除.json`
    优先，然后是"不在 保留.json 里"）—— 名字那份是权威，比对规则见
    `shared/cards.py`。

    先 `grid.scan()` 把每张卡点一遍读名字（只改选中项、不提交，见 `nodes/cardpick.py` 的模块 docstring）。
    **读不出名字的格子不碰**（可能是名单里的牌，猜不得）：
      · 有**读得准**的待移除牌 → 移它（取行→列的第一张）。
      · 一张待移除牌都没有、又没有读不出的格子 → 确实全保留了 → 点「返回」。
      · 有读不出的格子、又没有待移除牌 → 分不清是不是"全保留了"，**不猜**，停车。
    """
    try:
        rules = load_rules()
    except CardsConfigError as exc:
        return park(g, WAIT_CARDS_CONFIG, "cards_config_broken",
            f"移除屏：卡牌配置读不动（{exc}） —— 停下等人（已存 cards_config_broken.png）")

    cards = grid.scan(g)
    if not cards:
        return park(g, WAIT_CARD, "cardpick_nogrid",
            "移除屏：一张卡都没读出来 —— 停下等人（已存 cardpick_nogrid.png）")

    grid.clear_box(g, cards)      # 扫完别把卡牌信息框留在屏上（见那个函数的 docstring）
    unknown = [c for c in cards if not c["name"]]
    outside = [c for c in cards if c["name"] and rules.is_removed(c["name"])]

    if outside:
        t = outside[0]
        log(f"    移除屏：{len(cards)} 张里，名单外的「{t['name']}」排在第一张"
              f"（{t['row']}-{t['col']}）→ 移它")
        grid.pick(g, t)
        if not grid.confirm(g):
            return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
                "移除屏：选中了、但「确定」没点掉 —— 停下等人")
        log(f"    移除屏：已移除「{t['name']}」")
        return ""

    if unknown:
        where = "、".join(f"{c['row']}-{c['col']}" for c in unknown)
        return park(g, WAIT_CARD, "cardpick_remove_unknown",
                    f"移除屏：没有名单外的牌，但有 {len(unknown)} 张名字读不出（{where}） —— 停下等人（已存 cardpick_remove_unknown.png）")

    log(f"    移除屏：{len(cards)} 张全在保留名单里（{'、'.join(rules.keep_names)}）"
        " —— 没有可移除的，点左上角「返回」取消")
    if not g.click_when(选卡返回, guard=(选择卡牌,)):
        return park(g, WAIT_CARD, "cardpick_noback",
            "移除屏：「返回」没找到/点不掉 —— 停下等人（已存 cardpick_noback.png）")
    if not g.wait_gone(选择卡牌, timeout=8):
        return park(g, WAIT_CARD, "cardpick_back_stuck",
            "移除屏：点了「返回」这屏还在 —— 停下等人（已存 cardpick_back_stuck.png）")
    log("    移除屏：已返回（这一项没移除任何牌）")
    return ""


def run_multi(g):
    """第二版移除屏：「选择最多3张卡牌，将其移除。」（用户 2026-10-04 定的走法）。

    **不接 `handle()` 递进来的那一帧**：这一屏一格的长相会随"选没选中"变，
    每一步动手前后都得现看一帧（`grid.frame`），拿旧帧做的判断没有意义。

    **走法**（每一步读不明白都停车，**绝不带着没核过的选中去点「确定」**——
    那一下是真移除，点错了牌就没了）：

      ① **先把选中清成一个"确定的 0"**：有灰罩 ⇒ 选满 3 张、且知道就是亮的那 3 张
         （**灰罩在、全对比的却不是恰好 3 格 ⇒ 这一帧读花了，停车** `cardpick_wash_mismatch`）
         ⇒ 挨个点掉 ⇒ 核"面板关着"；没灰罩、面板也关着 ⇒ 本来就是 0，一步不用点；
         没灰罩、**面板却开着** ⇒ 再看**选中光环**（`grid.glowing`，2026-10-09 加）：
         有光环 ⇒ 选着 1~2 张而看不出是哪几张 ⇒ **停车**（`cardpick_preselected`）；
         **一格光环都没有** ⇒ 屏上其实一张都没选，那块亮着的是**飘过来的卡牌信息框**
         ⇒ 点一下空白（`CARD_BLANK`）把它收掉 ⇒ 再看一帧，面板暗了就按"0 张"往下走，
         没收掉／那一记没点出去就停车（`cardpick_infobox_stuck` / `cardpick_infobox_noclick`）
         ——**不猜**，乱点会把不该移除的牌选上。
      ② **读一遍卡名**（`grid.read_slot`：点开→读→点回去，配对点击净效果为零），挑出
         **不在保留名单**的牌，最多 `grid.SLOT_LIMIT` 张；名单里的牌原样放过。
         凑够 3 张就不再读后面的了（封顶就 3 张，后面的名字用不上）。
      ③ **选上、核对、提交**：逐张点选，再读一帧核对（**选满 3 张时灰罩能逐张核对
         身份**，不足 3 张时核"面板开着/关着"这条粗的），然后点「确定」等这屏走掉。

    "一张都不选"是**正路不是异常**（用户原话「可以不选择」）：全是保留名单里的牌
    时，第 ② 步一张都不选，第 ③ 步核"面板关着"，照样点「确定」走人
    （用户原话「取消选中再点「确定」」）。
    """
    try:
        rules = load_rules()
    except CardsConfigError as exc:
        return park(g, WAIT_CARDS_CONFIG, "cards_config_broken",
            f"选卡（最多3张）：卡牌配置读不动（{exc}） —— 停下等人（已存 cards_config_broken.png）")

    cells = grid.slots()
    by_key = {(c["row"], c["col"]): c for c in cells}

    states, name, mean = grid.frame(g)
    if grid.holes(states):
        return park(g, WAIT_CARD, "cardpick_nogrid",
                    f"选卡（最多3张）：格子读花了（{grid.describe(states)}） —— 停下等人（已存 cardpick_nogrid.png）")
    occupied = [c for c in cells if states[(c["row"], c["col"])] != "empty"]
    if not occupied:
        return park(g, WAIT_CARD, "cardpick_nogrid",
                    f"选卡（最多3张）：一张牌都没读到（{grid.describe(states)}） —— 停下等人（已存 cardpick_nogrid.png）")

    # ---- ① 把选中清成"确定的 0" ----
    if any(v == "washed" for v in states.values()):
        lit = sorted(k for k, v in states.items() if v == "full")
        # "有灰罩"和"亮着 3 张"是**同一件事的两面**（上限 3 张 + 灰罩只在选满时渲染，
        # 两条都是实测量出来的，见上面 ①②）。对不上就说明这一帧读花了 —— 这一屏
        # 唯一能把选中清干净的办法是"挨个点掉亮着的那几张"，数不对就会点到不该点的
        # 牌上，所以**不猜，停车**。（2026-10-04 之前没有这道闸，是因为 `grid.SLOT_WASHED`
        # 那条线切在牌的群里、会凭空造出"洗白"，见那个常量上面那段。）
        if len(lit) != grid.SLOT_LIMIT:
            return park(g, WAIT_CARD, "cardpick_wash_mismatch",
                        f"选卡（最多3张）：屏上有洗白（＝选满了），可全对比的却是 {len(lit)} 格（{grid.describe(states)}） —— 停下等人（已存 cardpick_wash_mismatch.png）")
        where = "、".join(f"{k[0]}-{k[1]}" for k in lit)
        log(f"    选卡（最多3张）：这屏进来时就选满 {len(lit)} 张（{where}）—— 先挨个点掉")
        for key in lit:
            grid.tap_slot(g, by_key[key])
        states, name, mean = grid.frame(g)
        if not grid.nothing_selected(mean, name):
            return park(g, WAIT_CARD, "cardpick_undeselect",
                        f"选卡（最多3张）：想把已经选着的清掉，可点完 {'还剩灰罩' if any((v == 'washed' for v in states.values())) else '面板还弹着'}（{grid.describe(states)}，面板亮度 {mean}） —— 停下等人（已存 cardpick_undeselect.png）")
        log("    选卡（最多3张）：已清空选中")
    elif not grid.nothing_selected(mean, name):
        # 面板亮着、又没灰罩 —— **两种可能**，靠"选中光环"分开（见 `grid.HALO_GREEN` 那段）：
        # ① 真的选着 1~2 张（光环在）→ 老规矩，不猜，停车；
        # ② 屏上其实一张都没选，这块亮着的是**从别处飘过来的卡牌信息框**（光环一处都没有）
        #    → 点一下空白收掉它，收掉了就按"0 张"照常往下走（2026-10-09 加的）。
        lit = grid.glowing(g.capture())
        if lit:
            where = "、".join(f"{k[0]}-{k[1]}" for k in sorted(lit))
            return park(g, WAIT_CARD, "cardpick_preselected",
                        f"选卡（最多3张）：这屏进来时**面板弹着、却没有灰罩**，而 {where} 上带着选中光环"
                        f"（亮度 {mean}，卡名「{name}」）—— 选着 1~2 张、看不出是哪几张"
                        " —— 停下等人（已存 cardpick_preselected.png）")
        log(f"    选卡（最多3张）：面板亮着（亮度 {mean}，卡名「{name}」），可满屏一格选中光环都没有"
            " —— 是飘过来的卡牌信息框，点一下空白收掉它")
        if not g.click_at(CARD_BLANK, guard=(选择卡牌,)):
            return park(g, WAIT_CARD, "cardpick_infobox_noclick",
                        "选卡（最多3张）：想把飘来的卡牌信息框点掉，可那一记**没点出去**"
                        "（空白点或这屏没认住） —— 停下等人（已存 cardpick_infobox_noclick.png）")
        time.sleep(grid.AFTER_TAP)
        _, name, mean = grid.frame(g)
        if not grid.nothing_selected(mean, name):
            return park(g, WAIT_CARD, "cardpick_infobox_stuck",
                        f"选卡（最多3张）：点了一下空白想收掉卡牌信息框，可面板还亮着"
                        f"（亮度 {mean}，卡名「{name}」）—— 不猜，停下等人"
                        "（已存 cardpick_infobox_stuck.png）")
        log("    选卡（最多3张）：框收掉了，按一张都没选往下走")
    else:
        log("    选卡（最多3张）：进来时一张都没选")

    # ---- ② 读一遍卡名，挑出不在保留名单的牌 ----
    chosen = []          # [(格位, 卡名)]，按读到的先后
    for c in occupied:
        if len(chosen) >= grid.SLOT_LIMIT:
            log(f"    选卡（最多3张）：已经挑出 {grid.SLOT_LIMIT} 张可移除的，后面的不读了")
            break
        key = (c["row"], c["col"])
        name, trouble = grid.read_slot(g, c)
        if trouble:
            return park(g, WAIT_CARD, "cardpick_name_unknown",
                        f"选卡（最多3张）：{trouble} —— 停下等人（已存 cardpick_name_unknown.png）")
        if rules.is_kept(name):
            log(f"    选卡（最多3张）：{key[0]}-{key[1]}「{name}」在保留名单里 —— 原样放过")
            continue
        chosen.append((key, name))
        log(f"    选卡（最多3张）：{key[0]}-{key[1]}「{name}」不在保留名单里"
              f" —— 记下（第 {len(chosen)}/{grid.SLOT_LIMIT} 张）")

    # ---- ③ 选上、核对、提交 ----
    want = {key for key, _ in chosen}
    for key, _ in chosen:
        grid.tap_slot(g, by_key[key])
    states, name, mean = grid.frame(g)
    lit = {k for k, v in states.items() if v == "full"}
    if any(v == "washed" for v in states.values()):
        # 选满 3 张灰罩才出来 —— 这是**唯一**能逐张核对身份的时刻
        if lit != want:
            return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                        f"选卡（最多3张）：打算选 {grid.names(chosen) or '不选'}，屏上亮着的却是 {'、'.join((f'{k[0]}-{k[1]}' for k in sorted(lit))) or '不选'} —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif len(want) == grid.SLOT_LIMIT:
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：点了 {grid.SLOT_LIMIT} 张可移除的，屏上却没出现灰罩 —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif want and grid.nothing_selected(mean, name):
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：打算选 {len(want)} 张，屏上却像一张都没选（面板没弹） —— 停下等人（已存 cardpick_pick_mismatch.png）")
    elif not want and not grid.nothing_selected(mean, name):
        return park(g, WAIT_CARD, "cardpick_pick_mismatch",
                    f"选卡（最多3张）：一张都不打算选，可屏上还选着（面板弹着，亮度 {mean}） —— 停下等人（已存 cardpick_pick_mismatch.png）")

    if chosen:
        log(f"    选卡（最多3张）：共选 {len(chosen)} 张（{grid.names(chosen)}）→ 点「确定」")
    else:
        log("    选卡（最多3张）：一张可移除的都没有（全在保留名单里）"
            " —— 不选，直接点「确定」走人")
    if not grid.confirm(g):
        return park(g, WAIT_CARD_CONFIRM, "cardpick_noconfirm",
            "选卡（最多3张）：选完了、可「确定」没点掉 —— 停下等人（已存 cardpick_noconfirm.png）")

    log(f"    选卡（最多3张）：已提交（移除 {len(chosen)} 张：{grid.names(chosen) or '无'}）")
    return ""
