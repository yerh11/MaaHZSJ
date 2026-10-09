"""路口 —— 地图节点「深入」过去后那一屏：下一层走哪条道。

**这一屏没有「离开地点」**——它不是地点界面，是必须做的选择，
脚本在这儿只能选边，"跳过"这个选项压根不存在。

目的地**每层都不一样**（第一层是「古王国遗迹-印记石厅」「黑龙祭祀场-祭祀长廊」，
第三层是「白树高塔-秘密通道」「逆生白树-白树树根」），所以不能像最早那样
把目的地名写进 pipeline 的 expected 里——那样每下一层都得重写一遍节点，
而且没重写之前脚本只会**无声地空转**（实测空转了 15 轮才被人发现）。
现在改成：pipeline 只放一个"取字"探针，本模块把选项读回来、按名字做子串匹配。

选项小标题套着**全角引号**（和事件屏是同一套控件），所以「取带引号的行、
按 y 排序」这套在两边都能用，见 script/nodes/event.py。本模块的判据放宽成
"前引号开头**或**后引号结尾"——选中行会被高亮吃掉前引号（见 option_rows）。

选边**不看目的地叫什么，只看它是第几条**（见 ROW_INDEX）：目的地名每层都换，
按名字匹配等于每层都得等人重新指一次；按序号则到哪层都一样。屏上给几条、
分别写着什么，每次都照原样打进日志，事后能回头看这一层走的是哪条道。

地图节点「深入」≠ 本屏「路口」，其它屏幕的对照表见
assets/resource/pipeline/地点.json 的头部注释。
"""

import time
from strings import 路口界面, 路口选项行, 确认选择
from shared.reasons import (
    WAIT_FORK,
    )
from shared.coords import CLICK_DY
from shared.kit import log

# 选**第几条**（0 起算），不是"哪个目的地"。用户 2026-10-02：「均选择1」——
# 从此路口一律走第 1 条，不再按目的地名匹配、也不再每层停下来问。
#
# 来历（都记着，好回头核这条规则对不对）：
#   · 2026-10-01 第二层→第三层：指了「白树高塔-秘密通道」——当时它也在第 1 位。
#   · 2026-10-01 第四层：全屏只读到一条带引号的选项（「前往 旧城-山坡」），
#     等于只有 1 号位可选。
#   · 2026-10-02「深入」下来那次：两条是「前往古王国遗迹-水晶侵蚀区」和
#     「前往黑龙祭祀场-祭祀长廊」，脚本按旧规则停车问人，用户指了 1。
#   · 2026-10-02 白树高塔/逆生白树这层：脚本又停下来问，用户答「均选择1」。
# 前三次全都是 1 —— 那就不再逐层问了，写成定死的规则。
ROW_INDEX = 0

QUOTE = "“"

# 引号是**一对**。选中那行的前引号会被高亮框吃掉、后引号还在（2026-10-02 实测，
# debug/_measure_fork.py），两头的判据都要用它。
CLOSE_QUOTE = "”"

# 点击是**双击**（用户 2026-10-02：「都说了，要双击」——单击没反应也不报错，
# 地图节点就是这个脾气，见 auto.py 的 double_click）。落点比小标题中心低
# `CLICK_DY`（已搬进 `shared/coords.py`；同 event.py 的 OPTION_DY：旧实测
# "只点标题那一行会白点、低 20 上下才过"）。
# 这一屏是**两段式**，而双击的语义**看行选没选中**：没选中 → 只算选中（行高亮、
# 右边浮出「确认选择」，还要按它）；本来就选中 → **直接确认走人**。
# 两种都实撞过，见 handle 里的注释（2026-10-02 实测）。


def option_rows(g, image=None):
    """选项区里带全角引号的那几行（前引号开头或后引号结尾），按 y 从上到下排序。返回 [(box, text), ...]。"""
    if image is None:
        image = g.capture()
    reco = g.probe(路口选项行, image)
    rows = []
    for r in (reco.all_results or []) if reco else []:
        text = (r.text or "").strip()
        # 至少两个汉字（同 event.py 2026-10-02 点歪事故后加的滤网，
        # 挡掉背景发光读出来的 '1'/'o8' 碎屑）
        if sum(1 for ch in text if "一" <= ch <= "鿿") < 2:
            continue
        # 小标题带**全角引号**。判据是"**前引号开头或后引号结尾**"——
        # 2026-10-02 实测（debug/_measure_fork.py 连拍三帧）：**选中**的那行
        # 前引号读不出来（高亮框的光效把它吃了，框整体右移 ~25px，分 0.999，
        # 不是置信度问题），OCR 只给回 '前往古王国遗迹-水晶侵蚀区”'。
        # 旧判据只认前引号 → "已选中的行"反而从选项表里消失：脚本读到
        # "没有含「古王国」的"、白停一次车。说明行两种引号都没有，仍被挡在外面。
        if text.startswith(QUOTE) or text.endswith(CLOSE_QUOTE):
            rows.append((tuple(r.box), text))
    rows.sort(key=lambda x: x[0][1])
    return rows


# 刚进这一屏时**正文是一个字一个字打出来的**，选项行要等正文打完才画上来。
# 2026-10-02 实撞（debug/run_1002y.log:63 + debug/screenshots/fork_stuck.png）：
# 那帧正文断在「显然通往不」、两条选项**一行都没读到**，脚本当场白停一次车；
# 几分钟后对着**同一屏**再 OCR（python debug/ocr_screen.py），两条都在
# （「前往古王国遗迹-印记石厅」y=367 分 1.000；「前往黑龙祭祀场-祭祀长廊」
# y=463 分 0.993）。和篝火那次一个道理：**一帧读不到 ≠ 这一屏没得选**。
# 只在"一行都没有"时等；只要读到一条就立刻往下走（少读一条仍是停车，见 handle）。
READY_TIMEOUT = 6.0
READY_INTERVAL = 0.3


def _wait_rows(g):
    """等选项行画上来再读。返回 (rows, 等了几秒) —— 没等就是 0.0。

    一行都读不到就重截重读，到 READY_TIMEOUT 为止；超时也把最后一次的结果
    原样交回去，**停不停车由 handle 判**，这里不替它下结论。
    """
    t0 = time.monotonic()
    while True:
        rows = option_rows(g)
        waited = time.monotonic() - t0
        if rows or waited >= READY_TIMEOUT:
            return rows, waited
        time.sleep(READY_INTERVAL)


def handle(g, hit):
    """在路口选一条道走。

    这一屏**没有「离开地点」**，选边是必须做的选择 —— 所以认得出这一屏、
    却选不出该走哪条时，只能停下等人（从前这里是往下掉、空转到步数上限）。
    """
    # 选项在**动作之前现读**（不传图 = 现截一张）：认屏那一刻的选项行不能用来
    # 算点击坐标，这是新契约第 1 条
    rows, waited = _wait_rows(g)
    if waited >= READY_INTERVAL or not rows:
        # 等过就报一声等了多久：调 READY_TIMEOUT 时要看的就是这个数
        log(f"    路口：选项行等了 {waited:.1f}s 才画上来")
    # 读不全就停：**少读一行不是"没得选"**——第 1 条读丢了、第 2 条读到了，
    # 照 ROW_INDEX 点下去会走错道，而这一屏走出去就回不了头。
    if len(rows) <= ROW_INDEX:
        # 把读到的**原样列出来**：上一次在这儿闷头空转了 15 轮，人只看到一句
        # "没认到某地名"，根本不知道这层给的是哪几条路。
        g.snap("fork_stuck")
        names = "、".join(t for _b, t in rows) or "（一行都没读到）"
        log(f"    路口：只读到 [{names}]，凑不出第 {ROW_INDEX + 1} 条")
        return WAIT_FORK

    box, text = rows[ROW_INDEX]
    names = "、".join(t for _b, t in rows)
    cx, cy = box[0] + box[2] // 2, box[1] + box[3] // 2 + CLICK_DY
    log(f"    路口：这层给的是 [{names}]")
    log(f"    路口：按规则走第 {ROW_INDEX + 1} 条 —— 双击 {text}  (x={cx}, y={cy})")
    g.double_click(cx, cy)

    # 双击之后**两种情况都在这一圈里**（2026-10-02 同一天先后实撞）：
    #   · 行**本来没选中** → 双击只算选中（行高亮、右边浮出「确认选择」按钮），
    #     这一圈在同一帧里看到按钮就按它一下（单击；要双击的是选项行，同 campfire）；
    #   · 行**本来就选中**（上一轮"选中了没走掉"留下的状态）→ 双击**直接确认**、
    #     屏当场开始过场，按钮压根不浮出来 —— 旧写法写死"等按钮浮出"，把这种成功
    #     误报成失败、白停了一次车（现场见 fork_stuck.png：屏都已经走到「狭缝」过场了）。
    # 判据始终是**这一屏还在不在**：屏走了就算成（现截现判，不猜）。
    deadline = time.monotonic() + 7.0
    clicked = False
    while time.monotonic() < deadline:
        image = g.capture()
        if not g.see(路口界面, image):
            log(f"    路口：选了 {text}")
            return ""
        if not clicked:
            box = g.box_of(确认选择, image)
            if box is not None:
                g.click_box(box)
                clicked = True
                log("    → 确认选择")
        time.sleep(0.4)
    g.snap("fork_stuck")
    if clicked:
        log("    路口：按了「确认选择」、屏还停在这一屏")
    else:
        log("    路口：双击之后「确认选择」没浮出、屏也没走")
    return WAIT_FORK
