"""事件（地图节点「事件」）：按标题查**事件集**，选对应的选项。

事件集在 script/events.json（用户 2026-10-01：「为事件节点建立一个事件集」）。
为什么不能像别的地点那样一刀切：
    用户当天明确「不同事件不同的解决方案」——每个事件给的东西不一样，
    选哪个得看具体是哪个事件。所以策略只能一条一条攒，攒的地方就是那个文件。

本模块只管"怎么读屏、怎么点"，**不存任何策略**——策略全在 events.json 里，
这样看事件集不用读代码，加一条也不用改代码。

怎么认出是哪个事件：
    这一屏**没有固定文字**（标题、正文、选项全是随机的），写不了 expected。
    但**标题的位置是固定的**：左上角那一条，实测读「困兽或囚徒」score 0.999。
    于是 pipeline 里只放一个不带 expected 的 OCR 探针（「事件标题」），
    取字回来由本脚本查表——认得出标题就等于认得出这是哪个事件。

    不过"标题读得出字"**单独不够**（别的屏左上角也有大字）：还得**底下有选项**。
    两道闸都过才算事件屏 —— 那两道闸现在住在 `script/recognizer.py` 的
    `_event_check` 里（就是从本模块 handle() 开头原样搬过去的），
    本模块只剩策略：读标题、查事件集、点选项。

选项点哪里：**位置是固化的**（用户 2026-10-02：「不同选项数量位置是固定的」
「要双击」）。选项数（从事件集来）→ 查 OPTION_SLOTS 那张表 → **双击**固定点。
**怎么点**（双击 / 只单击）来自事件集每条的 `tap`，不写就是双击 —— 见 TAP_SINGLE 那段。
**不拿 OCR 读到的框去算点击坐标**——2026-10-02 点歪事故：封印背景的发光被读成
'1'/'o8' 这类幽灵行、还过了菱形闸，把选项序号挤歪，脚本照着幽灵行的坐标去点，
结果点到第 1 个选项上（拐进了战斗支线）。OCR 如今只留两个用途：
**记录新事件的选项原文**（存进事件集给人看）和 debug/events.py 的 here。
读小标题的判据是**一条**：左边点着菱形圆点；另加一条「至少两个汉字」
——'1'/'o8' 这类碎屑当场滤掉（它们全是这么混进来的）。
（2026-10-02 前还有第二条「以全角引号开头也算」。它被量掉了：真选项一律带菱形，
引号只是文案长相，反倒让「真龙现身」的一行说明混成了第 4 个选项。
量测表与经过见 option_rows 的 docstring。）

新事件怎么办：
    **不猜**。events.json 里查不到就把它**记进去**（pick 留 null，选项原样存下来），
    然后停下等人定策略。下次再撞上就带着上次记的选项直接问了。
    这样见过的怪事件一条都不会丢，而没定策略的绝不会被瞎点。

第二页：
    有些事件选完会**翻到第二页**（「真龙现身」2026-10-05 第一次见：第一页选
    「揭穿他」→「确认选择」之后，翻出一页没有标题、正文换一段、底下又是两格
    选项的页面）。那一页**没有标题**，走不了本模块的主路（`handle` 靠
    `read_title` 查事件集），所以单开一条 `handle_dragon_page2` ——
    判屏用那一页自己的小字节点（`进入和卡兹的战斗`），走法由用户当天定。
    别把"没有标题的事件页"并进 `handle`：那会把主路变成"猜标题还没读出来的屏"。
"""

import json
import time
from pathlib import Path
from strings import (
    事件标题,
    事件选项行,
    事件触发战斗,
    进入和卡兹的战斗,
    离开地点,
    离开确认弹窗,
    确认选择,
    )
from shared.reasons import (
    NEED_STRATEGY,
    WAIT_EVENT,
    WAIT_EVENT_CONFIRM,
    WAIT_SINGLE_OPTION,
    )
# 选项格位表 / 选项 x / 落点偏移 —— 固化坐标收在 shared/coords.py，import 回原名。
from shared.coords import OPTION_DY, OPTION_SLOTS, OPTION_X
from shared.kit import log, park

# 事件集在 script/ 根下，**不在本模块旁边**：本模块是从 script/location_event.py
# 搬进某个屏包的，每搬一次 `Path(__file__).parent` 就跟着往下挪一层
# （script/ → script/screens/ → 现在的 script/nodes/），于是这里会悄悄指向一个
# 不存在的文件 —— 而 load_book() 的容错设计（读不到就当空表）让它**一声不响**，
# 转头还把第 1 个撞上的"事件"写进了新造的同名 events.json（2026-10-02 实测）。
# 所以这里显式回退一级，别再用 `Path(__file__).parent`。
BOOK = Path(__file__).parent.parent / "events.json"

# 「这个事件我（脚本）没定过策略」—— 和别的「等待事件」**分开报**。
#
# 用户 2026-10-02 睡前定的：「如果遇到不认识的事件, 直接记录下来, 然后退出这把游戏,
# 重新开始」；外加一句「记得保留不认识的界面的截图」。
# "退出这一局"那半条 2026-10-03 撤了（battle.py 里认它的那条特例跟着删，
# 来历写在 `battle.py` 的 import 处）—— 现在它和别的理由一样只是"停下等人"。
#
# **但这条理由本身要留着**，因为要区分的是两种完全不同的停：这一条是"我不知道
# 怎么办，得你定策略"，别的「等待事件」是**读数失败**（标题忽有忽无、选项一行都
# 没读到、双击没生效…）—— 那些是认屏抖了，不是缺策略。
# 两边打印的字都还是「等待事件」，只有这一个多带一个括号。


def _safe_name(name):
    """事件名 → 能当文件名的样子。Windows 上 \\ / : * ? " < > | 这九个半角符号不合法
    （全角的「”“，」没事），挨个换成下划线；空了就退回 untitled。"""
    return "".join("_" if ch in '\\/:*?"<>|' else ch for ch in name).strip() or "untitled"

# 这里从前有一个 `QUOTE = "“"`（选项小标题的引导符）—— 2026-10-02 删了。
# 它当年是"认选项行"的第二条判据，可量过 5 张存档帧（见 option_rows 那张表）：
# **真选项一律带菱形**，引号只是文案长相；反倒是「真龙现身」的一行说明
# 「“我看到你了！」靠它混进了选项列表。要显示这个字符的地方（debug/_measure_options.py
# 的"引号="那一列）自己写它的字面量，别从这儿借。

# 选项位置：**固化**（用户 2026-10-02：「不同选项数量位置是固定的」「要双击」）。
#
# 选项数 → 各格的小标题行中心 y（`OPTION_SLOTS`）、选项长条 x（`OPTION_X`）、
# 落点偏移（`OPTION_DY`）—— 三个数连同量它们的来历（存档帧、2026-10-02 点歪的
# 那次事故）已搬进 `shared/coords.py`（1280x720 基准），这里 import 回来。
# 表里没有的数量（比如 4 个）→ 停下问人，不猜。

# 选项格的**点法**记在事件集里 —— 每条的 `tap`（用户 2026-10-05 说「统一记录方式」，
# 挑的是「只加 tap」这一档；从前这一档是按标题写在代码里的 `SINGLE_TAP`，那天搬进表）：
#
#     tap 不写 / "double"  → 双击那一格（选中）→ 7 秒屏没走就**再双击同一格**（确认）
#     "single"             → 只单击、不点第二下
#     别的值               → 不点，停车等人（`event_park_<事件名>_badtap`）
#
# **「第二段确认」不记** —— 它有两种长相（同一格再双击一次 / 浮出「确认选择」点它），
# 脚本当场都认：那一轮 7 秒里一直盯着「确认选择」，两档谁先到算谁（见 `_click_option`）。
# 真龙现身第二页实撞的就是"浮出确认"那一档（debug/maafw.log:2437 双击 (150,382)
# → 0.26s 后 :2566 点 (623,409)），所以"第二段"不必也不该按事件记。
#
# 表里现在只有「游艺」一条是 `"single"`，来历是用户 2026-10-03 那句：
#
#     「翻牌的游艺, **翻牌时不要双击**」
#
# 他看见的就是**进游艺那一下的第二下** —— 这一屏点完，下一屏就是「移形变位」那张
# 牌桌（六张牌正在翻面/换位），第二下落在牌桌上，游戏就弹了一块卡牌信息框；
# 那块框不会自己走，跟着脚本一路走到地图，把标记和标签全挡住（用户当天另一句：
# 「当前页面被上一次的游艺的信息阻挡了」）。
#
# 两张存档帧量过：牌桌六格固定在 x 343~936（左边那一片是空的），进游艺的落点是
# (150,478) —— 单看坐标，第二下落在空白上；但**"第二下落在哪一屏"这件事本来就
# 不该赌**：翻面/换位动画中间牌在哪，没有量过（2026-10-02 就吃过一次"点在动画
# 中间、游戏只弹了个格子详情"）。
#
# 代价说清楚：万一某一屏非要双击才认（2026-10-02 用户在别的屏上说过「单击没反应」），
# 单击两轮都白等（各 7 秒）—— 所以 `_click_option` 在两轮都没反应之后**兜一次双击**：
# 那时候这一屏已经十几秒没动过，第二下还是落在同一屏上，落不到牌桌上去。
TAP_DOUBLE = "double"
TAP_SINGLE = "single"


# ---------- 事件集读写 ----------

def load_book():
    """读事件集。文件不在/读坏了都不抛——返回空表，让流程照常跑完再停下问人。"""
    try:
        with open(BOOK, encoding="utf-8") as f:
            book = json.load(f)
    except FileNotFoundError:
        log(f"    事件集 {BOOK.name} 不在 —— 当空表处理")
        return {}
    except json.JSONDecodeError as e:
        log(f"    事件集 {BOOK.name} 读不动（{e}）—— 当空表处理")
        return {}
    # 文件里 "_说明" / "_pick的取值" 那几条是写给人和给人看的，不是事件，滤掉
    return {k: v for k, v in book.items() if not k.startswith("_")}


def save_book(book):
    """把事件集写回去。**读-改-写整个文件**，所以必须先 load 再改再存。

    保留文件里那些 "_" 开头的说明条目——它们不在 book 里，得从原文件捞回来，
    否则第一次自动入册就会把说明整段抹掉。
    """
    raw = {}
    if BOOK.exists():
        try:
            with open(BOOK, encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            raw = {}
    raw.update(book)
    # **必须显式写 newline="\n"**：文本模式在 Windows 上会把每个 \n 换成 \r\n，
    # 于是"自动入册一个新事件"这一个动作会把整个文件的行尾翻一遍，
    # git 上看着像全文重写。2026-10-02 发现事件集就是这么变成 CRLF 的。
    with open(BOOK, "w", encoding="utf-8", newline="\n") as f:
        json.dump(raw, f, ensure_ascii=False, indent=4)
        f.write("\n")


def record(title, options):
    """把一个没见过的事件记进事件集（pick 留 None = 未定）。"""
    book = load_book()
    if title in book:  # 并发/重复调用时别把已定的策略冲掉
        return book[title]
    book[title] = {
        "options": options,
        "pick": None,
        "note": "**自动入册**：第一次撞上时记下来的，还没定策略。",
        "seen": time.strftime("%Y-%m-%d"),
    }
    save_book(book)
    log(f"    新事件「{title}」已记进 {BOOK.name}（pick 留空待定）")
    return book[title]


# ---------- 读屏 ----------

def _looks_like_title(text):
    """这段字像不像事件名。

    事件名是**短标题**（已知的 9 条：狭缝、游艺、腐化白树、困兽或囚徒、降神仪式厅、
    不曾存在的往昔、碎块，眼，根…，**最长 7 个字**），但标题那块 roi 在别的屏上
    也会读出别的东西。两道判据，都有实测的假阳性垫背：

      1. **至少两个汉字** —— 地图界面上就读出过一个孤零零的「1」，然后 play()
         每转到地图那一步都要喊一声「标题「1」不在策略表里」。
      2. **最多 12 个字** —— 标题界面左上角那行**私服的客服水印**
         「如遇登录或充值问题，请联系客服QQ：800179233。」（26 字）正落在这个 roi 里，
         2026-10-02 扫了 debug/screenshots 下全部存档帧才发现：
         它不光过得了第 1 条，连下面"必须有选项"那道闸都过了
         （选项区 OCR 把「点击任意处开始」的「点」单切出来一个 46px 的字，
         左边极光背景又蓝得够格，被判成了菱形圆点）—— 两道闸全开。
         事件名不会长到 26 个字，12 个字的上限离已知最长的 7 个字还留着余量。
    """
    hanzi = sum(1 for ch in text if "一" <= ch <= "鿿")
    return 2 <= hanzi and len(text) <= 12


def read_title(g, image=None):
    """读左上角的事件标题；读不到、或读出来的不像事件名，返回 None。"""
    if image is None:
        image = g.capture()
    reco = g.probe(事件标题, image)
    if reco is None or not reco.best_result:
        return None
    text = (getattr(reco.best_result, "text", "") or "").strip()
    return text if _looks_like_title(text) else None


def _has_bullet(image, box):
    """这行左边是不是点着一颗菱形圆点（= 它是选项小标题，不是下面的说明行）。

    **这是选项行唯一的一条判据**（2026-10-02 起，见 option_rows 里的量测表：
    13 行真选项全带它，说明行全不带）。实测（BGR，注意截图是 BGR）：
        标题行的菱形  (227,149,160)  B=227  B-G=78  B-R=67
        说明行同位置  ( 54, 21, 18)  B= 54  B-G=33  B-R=36
    两者亮度和蓝通道优势都差一个数量级，判据留得比较松也不会串。
    """
    # 只看框**左边那条窄带**，宽度按菱形的大小取：菱形在文字起点左边约 6~14px
    # （实测标题框 x=110，菱形 x=99~108）。说明行的文字起点更靠右（x≈116），
    # 这条带子会落在它的空白上；就算落在它的字上，字是白的、蓝通道不占优。
    x0, x1 = box[0] - 16, box[0] - 1
    y0, y1 = box[1], box[1] + box[3]
    if x0 < 0 or x1 <= x0 or y1 <= y0 or y1 > image.shape[0] or x1 > image.shape[1]:
        return False

    strip = image[y0:y1, x0:x1].astype(int)
    b, gr, r = strip[:, :, 0], strip[:, :, 1], strip[:, :, 2]
    # **三个条件必须落在同一个像素上**。写成三个独立 .any() 是错的——
    # 实测就这么放过了一行说明：那条带子里有个发白的字（234,224,172）满足"够亮"，
    # 另有个暗蓝的像素满足"蓝占优"，两件不挨着的事凑一起就判成了菱形，
    # 「困兽或囚徒」的说明行「一张特殊卡牌加入卡组。」因此混进了选项列表，
    # 后面的选项下标全会前移一位。
    return bool(((b >= 130) & (b - gr >= 35) & (b - r >= 25)).any())


def option_rows(g, image=None):
    """选项区里的小标题行，按 y 从上到下排序。

    **判据只有一条：左边点着一颗菱形圆点**（见 _has_bullet）—— 选项小标题
    顶格都带它，底下那行小字说明不带。返回 [(box, text), ...]，box 是全屏坐标。

    从前这里还有第二条判据「**以全角引号开头也算**」。2026-10-02 拿掉了，
    因为它**从没单独救下过一个真选项，却放过了一条说明行**：

        「真龙现身」这一屏，三格选项（揭穿他／献上金币／献上魂晶）都带菱形；
        可「揭穿他」底下那行小字说明是**「“我看到你了！”」**——它带引号、
        不带菱形，于是被判成第 4 个选项，事件集里记下了 4 个选项，
        len(options)=4 在 OPTION_SLOTS 里没有这一档 → 停车等人（用户当天报
        「识别错了,就三选项」）。

    拿 5 张存档帧量过（debug/_measure_options.py，逐行的引号/菱形都打出来）：

        now_event2.png     2 选项（不曾存在的往昔）   2 行全带菱形  引号行里没有不带菱形的
        now_event.png      3 选项（腐化白树）         3 行全带菱形  ——
        _park_1002al_dragon.png  3 选项（真龙现身）   3 行全带菱形  **“我看到你了！」（唯一假阳性）
        _park_1002ai_eventsel.png 2 选项（困兽或囚徒）2 行全带菱形  引号版式的两格**也带**菱形
        _park_1002ai_eternal.png  3 选项（永恒之舞）  3 行全带菱形  引号版式的两格**也带**菱形

    合计 13 行真选项**一个不漏**，而引号那条规则的真阳性是 0。所谓"引号版式"
    （选项文字本身带引号）照样有菱形——引号是文案长相，菱形才是控件的标志。

    ⚠️ 去掉之后**万一**撞上"真选项的菱形没认出来"，后果是**少一行**：新事件会
    少记一个选项，固化表也可能对不上档 —— 两条都通向"停车等人"，不会点歪。
    真撞上了再补，别预防性加判据（那一带你正走过：加回来的每条都得有帧垫背）。
    """
    if image is None:
        image = g.capture()
    reco = g.probe(事件选项行, image)
    rows = []
    for r in (reco.all_results or []) if reco else []:
        text = (r.text or "").strip()
        box = tuple(r.box)
        # **至少两个汉字**才可能是选项小标题 —— 2026-10-02 点歪事故后加的：
        # 背景发光被读成 '1'、'2'、'o8' 这类碎屑，还过了菱形闸，把选项序号挤歪。
        # 见过的真选项全是中文（最短的「战斗」也有两个汉字），一个汉字都凑不齐的扔。
        if sum(1 for ch in text if "一" <= ch <= "鿿") < 2:
            continue
        if _has_bullet(image, box):
            rows.append((box, text))
    rows.sort(key=lambda x: x[0][1])
    return rows


# ---------- 动作 ----------

def _click_option(g, y, title=None, marker=None, single=False):
    """在固化位置**双击**这一格；屏没走就**再双击一次同一格**。返回 True 表示走了。

    **判"这一屏还在不在"有两档，二选一**（第 3 个和第 4 个参数只在这一点上有差别）：
      · `title`  —— 屏上有**事件标题**的那几屏（`read_title != title` 就是走了）。
        事件屏走这条路，参数一直是位置传的，一字没改。
      · `marker` —— **没有标题的那几页**（真龙现身的第二页）：`read_title` 在那儿
        恒返回 None，`None != title` **当场就成立**，拿标题判会让"点了一下"
        立刻被当成"屏走了"。所以那一页改拿**标志物节点**判
        （`见得到 marker` = 这一页还在），见 `handle_dragon_page2`。

    **点法**由 `single` 决定 —— 它来自事件集那一条的 `tap`（缺省双击，见 TAP_SINGLE
    那段）：`single=True` 的屏两轮都**只单击**、不点第二下（现在只有「游艺」）。

    双击是用户 2026-10-02 指出的：「都说了，要双击」——单击没反应、也不报错，
    跟地图节点一个脾气（见 auto.py 的 double_click、map.py 的 goto）。
    上一版在标题框四周换着偏移连点好几下，那套"补刀"动作正是把第一次
    "点没点中分不清"补成"确实点出去了"的帮凶。

    **这一屏是两段式，而且它那一档确认不是按钮**（2026-10-02 实撞 + 用户当天定）：
    「困兽或囚徒」双击第 1 格之后，那格**高亮选中了**、右边还浮出了卡牌预览
    （虚空奇点／攻击牌／被消除时造成 40 点伤害），可屏幕就是不走 ——
    整屏 OCR 20 行里**没有「确认选择」**，放大看选项行右侧和下方两处也什么都没有
    （现场 debug/screenshots/_park_1002ai_eventsel.png，脚本当时报「等待事件」停车，
    debug/run_1002ai.log）。问用户这一屏怎么确认，答：**「再双击同一格」**。

    所以现在这一档确认 = **在同一格上再双击一次**，第二下才是交出去。
    第二下**不是补刀**：补刀是"不知道点没点中、换个位置再试"，这里点哪儿是确定的
    （同一格，坐标没变），是用户定过的确认动作本身。

    **「确认选择」那条路照旧留着**（它出现在别的屏上）：本模块 2026-10-02 在
    「秘密实验室」（3 选项）双击第 3 格后见过它浮出来，处理照 fork.py 那套
    （那边「路口」屏同一种控件、已实走多次）：等它浮出来就按一下。
    两档都认，谁先到算谁 —— 判据始终是**这一屏还在不在**。

    **两档 2026-10-02 当天都实撞过**（同一天、同一种控件、不同屏）：
      · 「永恒之舞」（3 选项）→ 双击第 1 格后**浮出了「确认选择」**，按它就走
        （debug/run_1002ai.log 那轮「事件「永恒之舞」→ 选第 1 格」之后）；
      · 「困兽或囚徒」（2 选项）→ 双击第 1 格后**什么都没浮出来**，得**再双击同一格**。
    所以"两段式的第二段长什么样"**是看屏的**，别拿一屏的观察定死另一屏。

    判据只看**标题还在不在**：选项点中了这一屏就会走掉，标题自然消失；
    不比正文/选项文字（它们本来就在变，会误判成功）。每次现截再读。
    过场要时间，所以轮询 7 秒、一轮之内**不再补点**——2026-10-01「降神仪式厅」
    和 2026-10-02 这次都撞过"2 秒没等到过场、日志上写'没反应'是假话"的坑；
    屏没换就是这一下没生效，报信，别拿第三下乱补。

    **只单击的那一档**（`single=True`，= 事件集里写了 `tap: "single"` 的那些屏，
    现在只有「游艺」，2026-10-03 加、2026-10-05 搬进表）：两轮都只**单击**，
    屏不走也**不点第二下**（第二下会落到下一屏的牌桌上）。两轮都没
    反应才兜一次双击 —— 那时这一屏已经十几秒没动过，第二下落在同一屏上。
    """
    x = OPTION_X
    y = int(y)

    # 两轮：第 1 轮 = 选中，第 2 轮同一格 = 确认（用户 2026-10-02 定的）。
    # 每一轮里都盯着「确认选择」——它在别的屏上是第 1 轮就该来的那条路。
    if single:
        rounds = ((1, False), (2, False), (3, True))   # 第 3 轮 = 兜底那一次双击
    else:
        rounds = ((1, True), (2, True))
    for attempt, use_double in rounds:
        if use_double:
            if attempt == 1:
                log(f"    双击选项格 (x={x}, y={y})")
            elif attempt == 2:
                log(f"    屏没走 → 再双击同一格 (x={x}, y={y})")
            else:
                log(f"    两次单击都没反应 → 兜一次双击 (x={x}, y={y})")
            g.double_click(x, y)
        else:
            if attempt == 1:
                log(f"    单击选项格 (x={x}, y={y})（这一屏不点第二下）")
            else:
                log(f"    屏没走 → 再单击同一格 (x={x}, y={y})")
            g.click(x, y)

        # 7 秒：比原来的 4 秒宽 —— 两段式要多等一次"浮出→按下"（fork.py 同值）
        deadline = time.monotonic() + 7.0
        clicked = False
        misses = 0
        while time.monotonic() < deadline:
            image = g.capture()  # 一轮一张，判屏和找按钮复用同一帧
            if marker is not None:
                # 没有标题的那几页：标志物连着 3 帧看不到才算走 —— 退场动画里它会闪
                #（同 handle_battle_confirm 的做法）。一次 miss 就返回，等于把等待
                # 换成更短的假等待：主循环回头看这一页还在，回头又点一下。
                misses = 0 if g.see(marker, image) else misses + 1
                if misses >= 3:
                    return True
            elif read_title(g, image) != title:
                return True
            if not clicked:
                box = g.box_of(确认选择, image)
                if box is not None:
                    g.click_box(box)
                    clicked = True
                    log("    → 确认选择")
            time.sleep(0.4)
    return False


# ---------- 单选项保底 ----------

def _row_gone(g, image, box):
    """刚才点的那一行**不在原位**了吗 —— 单选项保底判"这一屏走了没有"用。

    容差取**半行高**（且不小于 8px）：选中/高亮会让小标题框轻微动一下，
    拿 1px 的位移当"屏走了"，就会在第一帧就退出、还没等到「确认选择」冒出来。
    只比 y，不比文字 —— 同一行在选中前后 OCR 会差一个引号（`_park_1002ai` 那两张
    对照帧就是同屏两次抓拍差一个字），拿文字相等当判据是给自己下绊子。
    """
    cy = box[1] + box[3] // 2
    tol = max(8, box[3] // 2)
    for b, _t in option_rows(g, image):
        if abs((b[1] + b[3] // 2) - cy) <= tol:
            return False
    return True


def handle_single_option(g, hit):
    """**单选项保底** —— 屏上只有一行选项、又没有离开按键时，双击那一行。

    用户 2026-10-03 定的（原话）：

        「设置一个保底机制, 当只有一个选项, 且没有离开按键时, **双击该选项**」

    它和地图那两条保底是同一批东西（「如果只有一条路可以走 直接走」
    「识别不到时滑动屏幕」，见 nav/map_view.py）：都是"没定过策略的分支
    不要停车，走那条唯一可能的走法"。**先说清它不是万能闸**：它只认"恰好一行
    选项"，一行都没有、或认出两行以上，一律不点（`_single_option_check` 的门槛）。

    ---- 现场 ----

    `debug/screenshots/live_probe_3.png`（2026-10-02 存的）：事件「失修封印」选
    第 1 项「尝试破解封印」之后的**叙事结果页** —— 正文讲"符文崩溃、有东西从里面
    跑出来了"，底下**唯一一行选项「战斗」**，**没有标题、也没有「离开地点」**。
    那一屏从前是靠两个一次性手操脚本走掉的（`debug/click_battle_opt.py` /
    `debug/confirm_battle.py`，2026-10-02 写的）—— 正是分工里不许再写的那种
    "替脚本点一下"。这条保底就是把它收编进流程：以后同类屏（想得到的还有各种
    "结果页只剩一个出口"的版式）都不必再停。

    ---- 判据 ----

    · **"只有一个选项"是现读出来的**（`option_rows`，和事件屏同一套菱形控件；
      恰好一行才认），不是记死的坐标；
    · **"没有离开按键"由认屏表的位置保证**：`赶紧离开`（事件结果屏）和
      `离开地点`（通用离开屏）各自在**前面**一行认领了帧，走到本行时它们必然
      不在这一帧上。这条条件不是漏写，是表顺序替它挡住了 —— 见 recognizer.py
      那一行的 note。

    ---- 点法与落点 ----

    和事件屏同一套（用户 2026-10-02「都说了，要双击」）：**双击**那一行；屏不走
    就**再双击同一格**（那一档确认长什么样是看屏的，同 `_click_option`），中间
    盯着「确认选择」—— 失修封印那屏就是"双击选中 → 浮出「确认选择」→ 按它进
    战斗"。**落点用这一帧读到的框中心**，不加 OPTION_DY 那种偏移：偏低会点到
    小标题下面那行黄色说明字上（点出介绍面板来，见 OPTION_DY 上面那段）。
    用"读到的框"而不是固化坐标，理由同 `handle_battle_confirm`：**这一屏上只有
    一行可点的字，没有第二行跟它挤**（选项屏那套固化坐标是"幽灵行把序号挤歪"
    踩出来的，这儿没有序号可挤）。
    量过 live_probe_3.png 那一行：框 (109,369,47,28)、中心 (132,383) ——
    这个 y 正好是 `OPTION_SLOTS` 里标准版式第 1 格的 383，和实跑多年的落点重合。

    点两轮还不走就 snap + 停下等人 —— 不接着点第三轮，也不换别的落点。
    """
    rows = option_rows(g)  # 不传 image = 现截一张（认屏那一刻的帧已经过期了）
    if len(rows) != 1:
        return park(g, WAIT_SINGLE_OPTION, "single_option_mismatch",
                    f"单选项保底：这会儿读到 {len(rows)} 行选项 —— 停下等人（已存 single_option_mismatch.png）")

    box, text = rows[0]
    x, y = box[0] + box[2] // 2, box[1] + box[3] // 2
    log(f"    单选项保底：屏上只有一行选项「{text}」，没有离开按键 → 双击它"
          f"（框 {tuple(box)} 中心 ({x},{y})）")

    for attempt in (1, 2):
        if attempt == 2:
            log(f"    屏没走 → 再双击同一格 (x={x}, y={y})")
        g.double_click(x, y)
        # 7 秒：和 _click_option 同值 —— 两段式要多等一次"浮出 → 按下"，
        # 2026-10-01「降神仪式厅」那次吃过"2 秒没等到过场就判没反应"的亏。
        deadline = time.monotonic() + 7.0
        clicked = False
        while time.monotonic() < deadline:
            image = g.capture()  # 一轮一张，判屏和找按钮复用同一帧
            if _row_gone(g, image, box):
                log(f"    「{text}」这一行不在了 —— 这一屏走了")
                return ""
            if not clicked:
                b = g.box_of(确认选择, image)
                if b is not None:
                    g.click_box(b)
                    clicked = True
                    log("    → 确认选择")
            time.sleep(0.4)

    return park(g, WAIT_SINGLE_OPTION, "single_option_stuck",
        "双击了同一格两轮，那一行还在、屏没走 —— 停下等人（已存 single_option_stuck.png）")


def handle(g, hit):
    """事件屏 → 查事件集，执行策略。

    **"是不是事件屏"由认屏表回答**（recognizer 里的 `_event_check`：标题 +
    选项两道闸）；这里只做策略。标题**现读一遍**（认屏那一刻的 evidence
    只配进日志）；选项**不读**——点哪里由"事件集里记了几个选项 + pick"
    查固化表 OPTION_SLOTS 决定，不拿 OCR 结果算坐标（2026-10-02 点歪的教训）。
    标题读出来了、可事件集里没策略 —— 那是真停下等人，不再往下掉。
    """
    title = read_title(g)
    if not title:
        # 认屏那一刻有标题、现在读不出来了：屏多半在变，这一轮什么都不做，
        # 下一轮重新认（别拿旧标题硬撑）
        log("    事件屏的标题刚才还在、现在读不出来了 —— 这一轮不动它")
        return ""

    # 现场图的名字都按事件名走（Windows 上不能用的那九个符号换成下划线）。
    # **一个事件一张、不覆盖**（用户 2026-10-02 睡前：「记得保留不认识的界面的
    # 截图」），所以下面每条失败路径再各带一个后缀 —— 从前四条都叫
    # `event_park_<事件名>`，同一个事件的不同失败**互相盖掉**，只剩最后一张；
    # 而且其中两条连「已存图」都没写进提示里（2026-10-04 拆开并补齐）。
    tag = _safe_name(title)

    book = load_book()
    entry = book.get(title)

    if entry is None:
        # 没见过的事件：先把它记下来（选项原样存），再停下问人。
        # 顺序很重要——**先记再停**，否则人一走神这屏就白撞了。
        # 只有这条路径还要读选项（为的是把原文存进事件集）。
        rows = option_rows(g)
        if not rows:
            return park(g, WAIT_EVENT, f"event_park_{tag}_norows",
                f"事件屏：标题在、选项行一行都没读到 —— 停下等人（已存 event_park_{tag}_norows.png）")
        record(title, [t for _b, t in rows])
        # 新事件这条路**另起一个前缀**（`event_new_`）而不是 `event_park_`：
        # 它是"入册并问人"，和上面那条"读不出来"不是一回事，混用一个名字会
        # 分不清这张图是哪一种停。从前这条路**一张都不存**，而旧的公共名
        # `event_park.png` 每撞一次就被下一张盖掉 —— 睡一觉起来只剩最后一张。
        return park(g, NEED_STRATEGY, f"event_new_{tag}",
                    f"事件「{title}」不在事件集里 —— 已入册 —— 停下等人（现场图 debug/screenshots/event_new_{tag}.png）")

    pick = entry.get("pick")

    if pick is None:
        opts = "、".join(entry.get("options") or []) or "（当时没读到选项）"
        return park(g, NEED_STRATEGY, f"event_undecided_{tag}",
                    f"事件「{title}」在事件集里但**策略还没定**（{opts}） —— 停下等人（现场图 debug/screenshots/event_undecided_{tag}.png）")

    if pick == "leave":
        # 策略是"什么都不选，走「离开地点」"。出口就是右下角那个按钮。
        # 不带 guard：事件屏是 check 认出来的（matched 为空），而且标题一读出来
        # 就等于屏还在，再加一层 guard 只是多一次 OCR。
        if not g.click_when(离开地点, timeout=3.0):
            return park(g, WAIT_EVENT, f"event_park_{tag}_noleave",
                        f"事件「{title}」：策略是不选就走，但没找到「离开地点」 —— 停下等人（已存 event_park_{tag}_noleave.png）")
        # 事件集那条的 `note` 是**给人看的存档备注**（来历、后果、量过的帧），
        # 不是日志 —— 从前把它整段打进日志，屏幕上就是一坨解释性文字
        # （用户 2026-10-08 报的那条「碎块，眼，根」）。日志只留这一句动作。
        log(f"    事件「{title}」→ 直接离开")
        g.leave_after()
        return ""

    # 位置固化：选项数取事件集里记的（用户定的策略就是按它数的），
    # 查表拿 y，**不问屏幕上这次读到了几行** —— 幽灵行再歪也碰不到点击。
    slots = OPTION_SLOTS.get(len(entry.get("options") or []))
    if slots is None or pick >= len(slots):
        return park(g, WAIT_EVENT, f"event_park_{tag}_noslot",
                    f"事件「{title}」要选第 {pick + 1} 个，但固化位置表里没有{len(entry.get('options') or [])} 个选项这一档（或序号超了） —— 停下等人（已存 event_park_{tag}_noslot.png）")

    # 这一屏该**双击**还是**只单击** —— 事件集每条的 `tap`（见 TAP_SINGLE 那段）。
    # 写歪了（打错字之类）不猜：那一档在「游艺」上点错一次，第二下就落到下一屏的
    # 牌桌上、弹一块信息框跟着脚本走到地图。查不出来的值 = 停下问人。
    tap = entry.get("tap", TAP_DOUBLE)
    if tap not in (TAP_DOUBLE, TAP_SINGLE):
        return park(g, WAIT_EVENT, f"event_park_{tag}_badtap",
                    f"事件「{title}」：事件集里写的点法 tap={tap} 不是这两档（{TAP_DOUBLE} / {TAP_SINGLE}） —— 停下等人（已存 event_park_{tag}_badtap.png）")
    single = tap == TAP_SINGLE

    log(f"    事件「{title}」→ 选第 {pick + 1} 格（固化位置，"
          f"{'只单击' if single else '双击'}）")
    if _click_option(g, slots[pick] + OPTION_DY, title, single=single):
        return ""

    # 退了这一格还有退路吗（事件集里的 `fallback`，0 起、跟 `pick` 同口径）。
    #
    # 来历（2026-10-05，用户定）：「真龙现身」第 2 格「献上金币」**要 15 金币**，
    # 那一局手里只有 10 —— 付不起，游戏**根本不理这一下**（点了两轮都没选中，
    # 现场帧 `event_park_真龙现身_noclick.png` 上「确认选择」hit=False，
    # 而且这一屏**没有「离开地点」**，想走也没那枚按钮），脚本当场停下等人。
    # 问用户这一屏怎么走，他定：**「金币不够就改选第 1 格『揭穿他』」**。
    #
    # 判据是**"这一格点不动"**，不是"金币不够"——脚本读不出那一行小字里的价钱
    # （`option_rows` 只认菱形小标题，不读说明行）。两件事在这一屏上等价：
    # 金币够时第 2 格点得动、退路用不上；金币不够时它必然点不动、退路顶上。
    # 退路**不是"随便再试一格"**：点哪儿仍然由事件集写死（`slots[alt]`），
    # 试完还是不走就照旧停车 —— 那是这一屏真出事了，不猜。
    alt = entry.get("fallback")
    if alt is None:
        return park(g, WAIT_EVENT, f"event_park_{tag}_noclick",
            f"选项格点过了（选中 + 确认两轮），标题还在 —— 停下等人（已存 event_park_{tag}_noclick.png）")
    if not (0 <= alt < len(slots)) or alt == pick:
        return park(g, WAIT_EVENT, f"event_park_{tag}_badfallback",
                    f"事件「{title}」：第 {pick + 1} 格点不动，而事件集里写的退路（fallback={alt}）不是这一屏上的一格 —— 停下等人（已存 event_park_{tag}_badfallback.png）")

    log(f"    事件「{title}」：第 {pick + 1} 格点不动，"
          f"按定的退路改选第 {alt + 1} 格")
    if _click_option(g, slots[alt] + OPTION_DY, title, single=single):
        return ""
    return park(g, WAIT_EVENT, f"event_park_{tag}_noclick",
                f"事件「{title}」：第 {pick + 1} 格和退路（第 {alt + 1} 格）都点过了，标题还在 —— 停下等人（已存 event_park_{tag}_noclick.png）")


def handle_battle_confirm(g, hit):
    """事件里选了「触发战斗」那一项、又确认之后浮出来的那行 —— **双击**它才真进战斗。

    2026-10-03 加，同一天实跑当场停了一次、按用户的话把**点法**改对了。

    ---- 这一屏长什么样 ----

    现场 debug/screenshots/_event_confirm_1003.png（事件「电音歌手」：选第 2 格
    「真是不堪入耳的声音」→「确认选择」之后，还没点过它）：左边一句引号台词
    「“又是一个音乐白痴”」，下面单独一行「触发战斗」(109,369,91,28) score 1.000。
    整屏就这么一个可点的字，脚本当时认不出这一屏，报「未知界面」停下等人。

    **点哪里用这一帧读到的框算，不固化坐标** —— 和选项那边正好相反，理由是这一屏
    上只有它一行可点的字，没有第二行去跟它挤（选项那边的固化坐标是"幽灵行把序号
    挤歪、照着点到了别的格"踩出来的）。真撞上它旁边还有别的行、被挤歪了，再改固化。

    **落点读的是认屏那个节点自己的框**（`事件触发战斗`），**不是 `option_rows`**：
    那一行点着的那颗菱形圆点带呼吸/高亮，`_has_bullet` 的像素阈值会翻 ——
    同一屏的两帧一帧判 1 行、一帧判 0 行（三帧对照表在 recognizer.py 的
    `_battle_confirm_check` docstring 里）。拿一个抖动的量当落点，就是给自己
    下绊子。而"这一屏认出来了"本身要求这个节点命中，所以**它跟认屏同生共死**，
    是最稳的那个框。

    用户 2026-10-03 给的这一屏的走法原话：「选择2, 然后在 3s 后第二个页面点击
    触发战斗」—— 那 3 秒是**游戏自己的节奏**（第二页要缓一下才浮出来），
    认屏表这边本来就只在它真浮出来（`事件触发战斗` 节点 OCR 命中）才认，
    所以这里**不另加 sleep 去凑那 3 秒**：凑了就是"用 sleep 蒙状态"，而状态
    本来就读得到。

    ---- 点法：双击（2026-10-03 实跑停下后，用户给的原话）----

    第一版是**单击**（`click_when` + 等它退场），实跑当场停住 ——
    `debug/run_1003_1951.log`：「事件的「触发战斗」确认行：已点」→
    「点了一下，可这行还赖在屏上没走」，现场帧
    debug/screenshots/event_battle_confirm_stay.png。那张帧说清了为什么：
    单击只把这一行**选中**（左边那条高亮条铺满），右边跟着浮出一个
    「✓ 确认选择」，**屏根本没走**。问用户这一屏怎么进战斗，答：

        「要双击才能进入战斗」

    所以现在照 `handle_single_option` / `_click_option` 同一套两轮双击：
    **双击那一行** → 7 秒不走就**再双击同一格**（"这一屏的第二段确认长什么样"
    是看屏的，见 `_click_option` 里「永恒之舞 / 困兽或囚徒」那段）。中间照旧
    盯着「确认选择」——它在别的屏上是第二段那条路，两档都认、谁先到算谁；
    判据始终是**这一屏还在不在**。

    **退场动画里不会回手再点**：两轮之间隔着整整 7 秒的轮询，只要这一屏连着
    三帧不在了就立刻返回；第二下只在"7 秒过去这一屏纹丝没动"时才落到同一格上。
    2026-10-03 那次「退场那几帧上它还在、主循环立刻重新认屏、回手又点一下」的
    坑，就是这么被隔开的。

    哪一步没读出来（框读不到、两轮点完屏还在）都 snap + 停下等人 ——
    不猜、不换落点、不静默空转。
    """
    # 落点现截现读（不传 image）。刚认出来的那一帧本来就命中了它，这里再读一次
    # 只是防"这一帧恰好没读出来"，所以给它 3 秒，读不到才认输。
    box = None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        box = g.box_of(事件触发战斗)
        if box is not None:
            break
        time.sleep(0.3)
    if box is None:
        return park(g, WAIT_EVENT_CONFIRM, "event_battle_confirm_fail",
            "事件的「触发战斗」确认行在屏上、可这一下没读出它的框 —— 停下等人（已存 event_battle_confirm_fail.png）")

    x, y = box[0] + box[2] // 2, box[1] + box[3] // 2
    log(f"    事件的「触发战斗」确认行 → 双击它（框 {tuple(box)} 中心 ({x},{y})）")

    for attempt in (1, 2):
        if attempt == 2:
            log(f"    屏没走 → 再双击同一格 (x={x}, y={y})")
        g.double_click(x, y)
        # 7 秒：和 _click_option / handle_single_option 同值 —— 两段式要多等一次
        # "浮出 → 按下"，2026-10-01「降神仪式厅」那次吃过"2 秒没等到过场就判没反应"的亏。
        deadline = time.monotonic() + 7.0
        clicked = False
        misses = 0
        while time.monotonic() < deadline:
            image = g.capture()  # 一轮一张，判屏和找按钮复用同一帧
            # "这一屏走了没有" = 认屏那个节点还在不在，**连续 3 帧看不到才算走**
            #（同 wait_gone 的 stable）—— 退场动画里它会闪，一次 miss 就返回
            # 等于把等待换成了更短的假等待，主循环一回头就又点一下。
            reco = g.probe(事件触发战斗, image)
            if not reco or not reco.hit:
                misses += 1
                if misses >= 3:
                    log("    这一行连着三帧不在了 —— 进战斗了")
                    return ""
            else:
                misses = 0
            if not clicked:
                # 第二档照 `_click_option` 那条老规矩留着：它在别的屏上是第二段
                # 那条路（「永恒之舞」见过），两档都认、谁先到算谁。
                b = g.box_of(确认选择, image)
                if b is not None:
                    g.click_box(b)
                    clicked = True
                    log("    → 确认选择")
            time.sleep(0.4)

    return park(g, WAIT_EVENT_CONFIRM, "event_battle_confirm_stay",
        "两轮双击都点过了，这一行还赖在屏上没走 —— 停下等人（已存 event_battle_confirm_stay.png）")


def handle_dragon_page2(g, hit):
    """事件「真龙现身」的**第二页** —— 第一页选了第 1 格「揭穿他」之后翻出来的那一页。

    ---- 这一页长什么样（2026-10-05 第一次见）----

    现场 debug/screenshots/battle_unknown_210237.png：**没有标题**，
    正文「卡兹从雕像后跳出，怒道“想当年！这些地方都是我们龙族先祖建造的！……
    你要从此过，就要给钱！”」，底下两格选项（都带菱形圆点）：
      1.「“招摇撞骗的家伙！”」 底下小字「进入和卡兹的战斗」
      2.「“原来是真龙之子！久仰大名！”」 底下小字「选择至多3卡牌给予财宝印记6」

    它是怎么来的（当天那局的引擎日志逐条对过）：地图 → 事件「真龙现身」第一页 →
    双击第 2 格「献上金币」（**要 15 金币、手里只有 10**，点不动）→ 走事件集里
    定过的退路、双击第 1 格「揭穿他」→ 浮出「确认选择」→ 点它 → **翻到这一页**。
    从前这一页整张认屏表都认不出来（见 recognizer.py 那一行的 note：没有标题、
    没有「离开地点」、有两行选项），脚本空转到「连续多轮认不出当前界面」停下等人。

    ---- 走法（用户 2026-10-05 定的）----

    问的是"这一页该选哪一格"，答：**第 1 格（进入和卡兹的战斗）**。
    落点用**固化坐标**（`OPTION_SLOTS[2][0]` = 382，和事件屏共用那张表）：
    这一页的选项标题实测 (128,371,165,23) / (126,464,278,27)，两格的行心正是
    382 / 477 —— 就是标准的两格版式，`OPTION_X` = 150 也落在标题框里。
    点法走 `_click_option`（双击 → 7 秒不走就再双击同一格，中间盯着「确认选择」）：
    这一页**第一次见**，它的第二段到底是"再双击同一格"还是"浮出「确认选择」"
    **实撞时量到了 —— 是后者**（2026-10-05 21:25 那趟 `debug/play.py`，
    `debug/maafw.log`：21:25:47.894 / .975 双击 (150,382)（`:2437`）→ 0.26s 后
    点 (623,409)、那一帧上「确认选择」已经浮出来了（`:2566`））。
    另一档（"再双击同一格"）没有帧；`_click_option` 两档都认，实撞时走的是这一档。
    判屏交给 `marker`（`进入和卡兹的战斗`）而不是标题：
    这一页没有标题，`read_title` 在这儿恒返回 None，拿标题判会一击即中地"成功"。

    两轮点完还不走就停车等人（`event_dragon_page2_noclick`）—— 不猜、不换落点。
    """
    y = OPTION_SLOTS[2][0] + OPTION_DY
    log(f"    真龙现身·第二页（卡兹）→ 选第 1 格「“招摇撞骗的家伙！”」（进战斗）"
          f"（固化位置 (x={OPTION_X}, y={y})）")
    if _click_option(g, y, marker=进入和卡兹的战斗):
        return ""
    return park(g, WAIT_EVENT, "event_dragon_page2_noclick",
        "真龙现身·第二页：第 1 格点过了（选中 + 确认两轮），这一页还挂着 —— 停下等人（已存 event_dragon_page2_noclick.png）")
