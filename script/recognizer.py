"""认屏 —— **唯一一张「这一帧是哪一屏」的表**，外加"循环读取"那个循环。

它只回答一个问题：**这帧是什么屏**。答完就交给 script/battle.py 分发给对应的
handler（`nav/` `nodes/` `combat/` `system/` 四个包里的屏模块），自己**一个东西都不点**
—— 这一层里不许出现任何点击。

为什么单独立这一层（用户 2026-10-02：「由单独的脚本认屏, 然后再分发给其他脚本」）：
从前"认屏"散在四个地方 —— battle.py 的 SCREENS 顺序、19 个模块 handle() 开头
那几行、debug/play.py 的 HERE、system/settlement.py 里 finish_run 的内部循环；
而"谁必须排在谁前面"只靠注释口口相传（「地点专属必须排在 leave 前面」这一句
在五个文件里各写了一遍）。现在**顺序就是这张表本身**，动它要过
`tools/check_screens.py` 的断言。

**顺序 = 优先级**：identify() 从上往下问，第一个说"是我的"的算数。
动顺序之前先看清楚每条的 note —— 每一处都是有由来的，换一下就会出
"看着正常、其实策略从没执行过"的毛病（篝火踩过）。

**Hit 里不装那一帧**。装了就等于把"拿过期帧动手"从后门放回来 ——
而"动作基于过期帧"正是这次重做要根治的东西（见 docs/zh_cn/架构与流程图.md 的「屏模块四条契约」）。
evidence 里只放**语义事实**（标题、选项文本），只给日志和 describe 用，
handler 不许拿它做动作。
"""

import time
from dataclasses import dataclass, field

from combat import death, fight
from nav import fork, map_view
from nodes import (
    altar,
    amulet,
    amulet_pick,
    arcade,
    campfire,
    card_reveal,
    cardpick,
    deck,
    event as event_screen,
    event_result,
    forge,
    gaze,
    reward,
    shop,
    stone,
    )
from system import confirm, leave, settlement
from strings import (
    主界面,
    仪式结算,
    仪式配置界面,
    公告界面,
    你的回合,
    同化提示,
    夜巡人选项,
    护甲牌选项,
    最后机会,
    敌方选卡提示,
    死亡黑屏,
    化形信使,
    离开确认弹窗,
    自动出牌,
    战斗胜利,
    逃离战斗,
    始源之凝视,
    篝火界面,
    怪石造物界面,
    商店界面,
    你的卡组,
    祭坛界面,
    路口界面,
    锻造使界面,
    护符选择界面,
    选择1个已激活护符,
    点击空白处继续,
    游艺全部奖励,
    游艺大转盘,
    游艺停止,
    游艺转盘,
    游艺发射,
    游艺移形变位,
    游艺最佳轮换,
    游艺拒绝并触发战斗,
    游艺拒绝后,
    选择卡牌,
    事件触发战斗,
    进入和卡兹的战斗,
    赶紧离开,
    离开地点,
    地图界面,
    标题界面,
    获得物品,
    )


# ---------- 表里的两种记录 ----------

@dataclass(frozen=True)
class Screen:
    """一屏。

    name     屏名。**脚本自己的词，不是游戏里的字** —— 所以一律加「屏」后缀：
             不但读起来分得清，还避开了 tools/check_strings.py 的"裸字符串"
             检查（「篝火」「事件」「商店」「战斗」都是 strings.py 里的地图词条）。
    nodes    命中**任一**即算这一屏（pipeline 节点名，从 strings.py 取）。
             空 = 判据全在 check 里。
    handler  认出来之后归谁动手（nav/ nodes/ combat/ system/ 里的函数），签名 handle(g, hit)。
    check    需要读屏再判的（事件屏、死亡屏），返回语义证据 dict，
             **返回 None = 不是这屏**（真闸：nodes 全命中也能被它一票否决）。
             拿不到证据、只想当闸用，返回 `{}` —— 空 dict 是"是这屏，没话可说"。
    modal    遮挡物：盖在别的屏上面，必须排在所有非 modal 之前
             （check_screens.py 会断言这一条）。
    recheck  **兜底屏**：命中之后要拿现帧整表复认一遍才交出去（见 _confirm）。
             判据是「这一屏是靠一个**地点屏家族通用的控件**认出来的」——
             现在只有三行：「通用离开屏」（「离开地点」）、「事件结果屏」
             （「赶紧离开」）、「单选项屏」（"选项区里恰好一行"这条纯兜底），
             由 check_screens.py 钉着。**别顺手往别的行上加**：每加一行，
             它每次命中就多花一次扫掠（约 3 秒）。
    note     为什么排在这个位置。**从 battle.py 的 SCREENS 整段搬来的，不是重写的。**
    """

    name: str
    nodes: tuple = ()
    handler: object = None
    check: object = None
    modal: bool = False
    recheck: bool = False
    note: str = ""


@dataclass
class Hit:
    """认出来的结果。

    screen   哪一屏
    matched  哪些节点命中的（nodes 的子集；check-only 的屏是空元组）——
             给 Game.click_when 的 guard 用：点按钮时要求"认出这屏的那些节点"
             还在这一帧上，把旧代码那层"同一帧耦合"保住
    evidence 语义快照（事件标题/选项文本…），**只给日志和 describe**
    """

    screen: Screen
    matched: tuple = ()
    evidence: dict = field(default_factory=dict)


# ---------- check：需要读屏再判的那几屏 ----------

def _event_check(g, image):
    """事件屏的两道闸（原样搬自 nodes/event.py 的 handle，2026-10-02 之前就在跑）。

    1. 左上角 `事件标题` 的 roi 读得出、且像个人名
       （`_looks_like_title`：≥2 个汉字、≤12 字）；
    2. 选项区 `事件选项行` 至少读出一行小标题。

    **两道闸缺一不可**，都是被假阳性逼出来的：
      · 只有第 1 道的时候，地图界面上一段被读成「1」的地形文字就能冒充事件名，
        play() 每转到地图那一步都要喊一声「标题「1」不在策略表里」；
      · 光加"必须有选项"还不够 —— 标题界面左上角那行 26 字的**客服水印**
        「如遇登录或充值问题，请联系客服QQ：800179233。」两道闸全过了
        （选项区把「点击任意处开始」的「点」单切出来一个 46px 的字，左边极光
        背景又蓝得够格，被判成菱形圆点），最后靠 12 字上限挡住；
      · 刚点完「坠入深境」那一帧还停在「仪式配置」屏，左上角大字读到
        「つ仪式配置」——第二道闸（必须有选项）把它拦下了。

    读不出就返回 None：**事件结果屏没有标题**，它归下一行接（顺序不能反）。
    """
    title = event_screen.read_title(g, image)
    if not title:
        return None
    rows = event_screen.option_rows(g, image)
    if not rows:
        return None
    return {"title": title, "options": [t for _b, t in rows]}


def _battle_confirm_check(g, image):
    """事件里选了「触发战斗」那一项、又确认之后浮出来的确认行（2026-10-03 加）。

    判据只有一个字面的 `事件触发战斗`（expected "触发战斗"）。麻烦在于
    **事件屏的小字说明也写「触发战斗」**（实测事件「电音歌手」第 2 格
    「真是不堪入耳的声音」底下那行小字，event_undecided_电音歌手.png y≈518）。
    不挡的话，"标题没读出来的事件屏"会掉到这一行，脚本就在那行小字上点一下。

    挡法：**读得到事件标题就不是这一屏** —— 真事件屏左上角那行标题读得出来，
    这一屏没有标题。（本屏在认屏表里排在「事件屏」后面，那是第一道；这里是
    第二道，管的是"事件屏没被上面认出来"的那一小段。）

    ---- 这道闸原来写成「读得到**选项行**就不是这屏」，是错的（2026-10-03 实测）----

    那一版当天就在实跑里把本屏自己挡掉了：脚本点完「确认选择」之后连着几轮
    报「认不出当前界面」，现场帧 battle_unknown_110309.png 上
    `identify()` 返回 None，而**离线重放同一张图却认得出来** —— 于是拿三帧
    对了一遍（都是只读）：

        帧                               read_title   option_rows   本节点
        battle_unknown_110309.png(确认屏)  None         1 行(!)      hit
        _now_unknown.png       (确认屏)    None         0 行         hit
        event_undecided_电音歌手.png(真事件屏) '电音歌手'    2 行         hit=False

    两处：
      1. **确认行自己就点着一颗菱形圆点**（截图里 `✦触发战斗`），
         `option_rows` 认的就是那颗圆点 —— **同一屏的两帧，一帧判 1 行、
         一帧判 0 行**（圆点小、带呼吸/高亮，`_has_bullet` 的像素阈值会翻）。
         拿它当闸 = 拿一个抖动的量当闸，时灵时不灵。
      2. 真事件屏上本节点本来就 **hit=False** —— 那行小字 y≈505 落在 roi
         (y 340~470) 外面。也就是说第一道闸之外，roi 本身已经挡着一层；
         这道闸真正要管的是"小字恰好落进 roi 的那些版式"（比如选项 1 就写
         「触发战斗」的事件）。

    `read_title` 在这三帧上干净利落地分开：确认屏 None、真事件屏「电音歌手」。
    它用 `_looks_like_title`（≥2 汉字、≤12 字）卡过一道，也是 事件屏 那道闸
    的同一个判据，两处不会打架。

    返回 {}（是这屏，没什么可说的）或 None（不是）。
    """
    if event_screen.read_title(g, image):
        return None
    return {}


def _single_option_check(g, image):
    """单选项屏的唯一判据：选项区里**恰好一行**小标题。

    用的还是事件屏那套控件（`nodes/event.py` 的 `option_rows`：左边点着菱形
    圆点 + 至少两个汉字），所以两张屏的"选项"是同一个东西 —— 差别只在一屏有标题
    （归事件集管）、一屏没有（归保底管）。

    **门槛写死成"恰好一行"**：多读出一行就当不是这屏（往下掉给别的屏，或停车
    等人），**绝不挑一行来点**。那样写的话，幽灵行就只能让这屏认不出来、不能让
    脚本点错地方 —— 2026-10-02 的"点歪事故"正是"照着手读到的行算坐标 + 序号被
    幽灵行挤歪"两件事凑出来的，这里只留前一半、把后一半摁死。

    evidence 只放**选项原文**（认屏那一刻的语义事实，给人看日志用），
    **不放那个框** —— 放了就等于把"拿过期帧算点击坐标"从后门放回来，
    落点由 handler 现读现算（见 `nodes/event.py` 的 `handle_single_option`）。
    """
    rows = event_screen.option_rows(g, image)
    if len(rows) != 1:
        return None
    return {"option": rows[0][1]}


# ---------- 认屏表：**顺序 = 优先级** ----------
#
# 下面每条的 note 是原 battle.py 的 SCREENS 注释整段搬过来的（那份注释现在
# 只剩这里一份，别再往别处抄）。地点那七条共用的一段话放在组前面。

SCREENS = [
    Screen(
        "确认弹窗屏",
        nodes=(离开确认弹窗,),
        handler=confirm.handle,
        modal=True,
        note="模态弹窗：盖在谁上面都可能，必须最先清",
    ),
    Screen(
        "结算屏",
        nodes=(仪式结算,),
        handler=settlement.handle,
        note="整局结束（胜负同屏）→ 收尾回主界面，终局",
    ),
    Screen(
        "战斗屏",
        # 几个模态框也算这一屏：它们弹出时右侧「自动出牌」整个不见，
        # **只认按钮就认不出这是战斗屏**，fight() 根本进不去 —— 那几框的解法
        # 全在 fight() 里（assimilate / nightwatch_option / armor_option），
        # 进不去就等于没有。2026-10-02 实测：夜巡人选项框弹着时，脚本报
        # 「未知界面」停车；当天晚些时候贪婪之怒的卡牌类型三选一框弹着时，
        # 脚本在 fight() 里面空等到超时 —— 同一个道理（外面进不来 vs 里面出不去，
        # 两条都得管）。
        nodes=(自动出牌, 你的回合, 同化提示, 夜巡人选项, 护甲牌选项, 最后机会,
               敌方选卡提示),
        handler=fight.handle,
        note="轮到我方 → 点「自动出牌」，这一场打完才回主循环"
             "（同化/夜巡人/贪婪之怒的模态框也算这一屏，见 nodes）",
    ),
    Screen(
        "战斗奖励屏",
        nodes=(战斗胜利, 逃离战斗),
        handler=reward.handle,
        note="战斗结算（胜利 / 逃离是两屏）→ 不拿奖励，直接走",
    ),
    Screen(
        "死亡屏",
        nodes=(死亡黑屏,),
        handler=death.handle,
        check=death.is_death_black,
        note="死透之后的黑屏 → **点一下屏幕**（用户 2026-10-02 定的）。"
             "判据是「屏幕黑没黑」，不是认画面 —— 用户当天明确"
             "「死亡画面不固定」「下一次死亡不一定时这个画面」，那天停着的是一团"
             "紫色水晶（debug/screenshots/fight_timeout.png），下次换个画面照样得认。"
             "**但光「黑」不够**（2026-10-02 补）：还有第二道闸「屏上没有字」，"
             "见 check（用户当天给的原话：「死亡黑屏是没有任何文字的」）。"
             "原来这儿的说法是「正常战斗里屏幕不黑，抢不到上面那几行的屏」——"
             "**那句话是错的，已经换掉**：2026-10-02 停在一张暗事件屏上"
             "（「困兽或囚徒」，亮度<60 的像素占 0.9178），它黑得够，"
             "就真抢在了事件屏前面命中，脚本对着插图正中连点了十来下"
             "（debug/run_1002ai.log、debug/screenshots/_park_1002ai.png）。"
             "排在这儿本身没问题 —— 现在靠 check 把暗事件屏挡回去，"
             "它落回下面的「事件屏」接（那张图正是事件屏的两道判据全过）。"
             "黑度 0.60 那条线的量法见 战斗.json 的 `死亡黑屏` 注释；"
             "「先等它停住 1.5 秒再点」「点够 5 下不换屏就停车」的理由见 combat/death.py。",
    ),
    Screen(
        "化形信使屏",
        nodes=(化形信使,),
        handler=death.handle_relic,
        note="死透之后的下一屏（黑屏点一下进来）→ **点「不留下遗物」**"
             "（用户 2026-10-02 定的，问「该点哪个」答左边那枚）。"
             "判据用标题「化形信使」：两个按钮是选项、不是判据。"
             "排在死亡屏后面，同一条链；它只出现在死亡收尾之后，"
             "战斗里的屏抢不到它（标题是这一屏独有的抬头）。"
             "现场存图 debug/screenshots/_death_relic.png、"
             "当时停车的那次跑 debug/run_1002af.log。",
    ),
    Screen(
        "凝视屏",
        nodes=(始源之凝视,),
        handler=gaze.handle,
        note="始源之凝视 → 挑赐福（用户 2026-10-06）：三张里有「宝石收集者」就"
             "接受它，没有就点下方**右边**那颗「刷新」—— **只点这一次**"
             "（左边那颗一下都不点）；刷过还是没有（或点了卡面不动）就"
             "**一张都不拿、直接点「离开地点」**。判据是**卡名那一行**"
             "（`宝石收集者-左/中/右`，祭坛.json 的窄 roi），不是卡面。"
             "取代 2026-10-01 的「不拿、直接离开地点」，也取代同一天早些时候那句"
             "「换到出为止」（`刷新(N/M)` 的 N 是已用次数，两颗加起来只够 4 次）。"
             "这一屏只在开局出现一次，顺序上没有邻居要顾。",
    ),
    # ↓ **盖在地点屏右半边**上的那张卡组面板，**必须排在地点屏前面** ——
    #   理由与「销毁卡牌屏 → 商店屏」同一条，见下面那一行。
    Screen(
        "选卡屏",
        nodes=(选择卡牌,),
        handler=cardpick.handle,
        note="卡组网格：**同一副卷面有两种出现方式** —— 满屏版（左边那半屏是事件正文/"
             "卡牌详情）和**只盖住右半边的面板版**（左边那半屏还是刚才那个地点屏）。"
             "2026-10-06 在篝火上撞到面板版，现场帧 debug/screenshots/"
             "_stuck_campfire_panel.png：标题「选择卡牌」在 (869,23)、副标题"
             "「选择卡组中1张牌升级」、右半边一格一格的卡、「确定」在 (908,653) —— "
             "后两个坐标与满屏版 cardchoice_now.png **一模一样**，两副卷面共用同一套 UI，"
             "差的只是左半边背后是谁。**所以它必须排在地点屏前面**：面板版上左半边那枚"
             "「激活护符」/「坐下休息」照样读得出来（篝火那行的判据就是左侧正文，实测"
             "0.9991），篝火先认领的话就会一直点「激活护符」、一直等不到「确认选择」，"
             "原地空转（那一局转了 375 轮，debug/run_1006_0433.log:2452 起；面板还把"
             "「离开地点」盖掉了，连退路都没有）。**也必须排在「事件屏」前面** —— "
             "2026-10-03 逮到一次：卡组屏左边那半屏就是事件正文，点中一张卡之后详情面板"
             "还在标题区写上卡片**类型**「诅咒牌」、选项区写上**卡名**，`_event_check` "
             "两道闸全过，于是它被当成一个叫「诅咒牌」的新事件自动入册（脚本自己停着、"
             "屏上留着一张选中的卡时就复发）。「选择卡牌」这个标题是这一屏独有的，"
             "排前面把它挡掉。怎么挑见 nodes/cardpick.py（按副标题分派）。",
    ),
    # ↓ 地点专属。**必须排在「通用离开屏」前面**：每个地点界面右下角都有
    #   「离开地点」，通用分支排在前面就会把它抢先点掉，地点策略永远轮不到 ——
    #   篝火就踩过这个坑：策略写好了却没接线。
    Screen(
        "篝火屏",
        nodes=(篝火界面,),
        handler=campfire.handle,
        note="地点专属（排在通用「离开地点」之前，见上面那段）",
    ),
    Screen(
        "怪石屏",
        nodes=(怪石造物界面,),
        handler=stone.handle,
        note="地点专属（同上）",
    ),
    Screen(
        "销毁卡牌屏",
        nodes=(你的卡组,),
        handler=deck.handle,
        note="商店点「移除卡牌」弹出的**销毁卡牌面板**（2026-10-04 第一次见，"
             "现场 debug/screenshots/play_not_here.png）。"
             "**必须排在紧跟着的「商店屏」前面**：面板只盖住屏幕右半边，"
             "左半边还是商店那一屏（神秘商人 + 那两个选项原样都在）——"
             "两屏真同时命中时先判的该是**盖在上面**这张"
             "（今天在两帧面板存档上实测：商店屏的锚点在面板上读不出来，"
             "两屏**并不总是**同时命中；顺序仍然钉着当保险）。排反了的话，面板刚上来那一两帧"
             "会归商店管，商店就会在面板上再点一次「移除卡牌」。"
             "判据只有标题「你的卡组」：它一打开就在（副标题「选择需要销毁的卡牌」"
             "只在没选中牌时读得出，不当判据）。走法见 nodes/deck.py：卡面模板先筛出"
             "名单外的格子、再点开读名字核实，两张判据都说过才销毁。"
             "⚠️ 点完「移除卡牌」到面板画出来之间隔着几帧，那几帧仍归商店那行 —— "
             "商店据此**等一眼**再判「到底进没进面板」（见 nodes/shop.py 的第三行出口）。",
    ),
    Screen(
        "商店屏",
        nodes=(商店界面,),
        handler=shop.handle,
        note="地点专属（同上）。**2026-10-04 起这里真动手了**：点「移除卡牌」把保留名单"
             "之外的卡一张张清掉，没得移/金币不足才走（用户那天的话在 nodes/shop.py "
             "开头）。它和销毁卡牌屏之间那两格跨屏的旗住在 shared/gridstate.py"
             "（**排在销毁卡牌屏后面**，理由见那一行）。",
    ),
    Screen(
        "祭坛屏",
        nodes=(祭坛界面,),
        handler=altar.handle,
        check=altar.is_altar,
        note="地点专属（同上）。**第二道闸（2026-10-02 加）**：锚点读到的字必须"
             "正好是节点声明的那个词，不能只是**包含**它 —— `祭坛界面` 的 roi 是"
             "按真祭坛屏的标题位置卡的，可别的屏正文里也有「祭坛」二字"
             "（那天栽在事件屏「残垣壁画」的正文「这祭坛前的墙绘…」上，"
             "读回 `这祭坛前的墙` score 0.9999），祭坛排第 10、事件屏排第 19，"
             "先命中就轮不到事件屏。判据怎么量的见 nodes/altar.py 的 is_altar。",
    ),
    Screen(
        "路口屏",
        nodes=(路口界面,),
        handler=fork.handle,
        note="地点专属；路口没有「离开地点」，不选边出不去",
    ),
    Screen(
        "锻造屏",
        nodes=(锻造使界面,),
        handler=forge.handle,
        note="地点专属（同上）",
    ),
    Screen(
        "护符屏",
        nodes=(护符选择界面,),
        handler=amulet.handle,
        note="地点专属；篝火「激活护符」之后那一屏",
    ),
    Screen(
        "卡牌展示屏",
        nodes=(点击空白处继续,),
        handler=card_reveal.handle,
        note="新到手的卡牌展示屏：唯一的出口是「点击空白处继续」",
    ),
    Screen(
        "事件屏",
        handler=event_screen.handle,
        check=_event_check,
        note="靠标题认；标题读不出或没有选项行就不是这屏，往下掉给别的屏",
    ),
    Screen(
        "真龙现身·第二页屏",
        nodes=(进入和卡兹的战斗,),
        handler=event_screen.handle_dragon_page2,
        note="**「真龙现身」的第二页**（2026-10-05 第一次见，用户当天定的走法："
             "选第 1 格「“招摇撞骗的家伙！”」＝进战斗）。事件第一页选「揭穿他」→"
             "「确认选择」之后翻出来的那一页：**没有标题**、正文是卡兹跳出来要钱、"
             "底下两格选项。那一天整张表都认不出它（没有标题 ⇒ 事件屏的两道闸不过；"
             "没有「离开地点」⇒ 通用离开屏不认；两行选项 ⇒ 单选项保底不认），"
             "脚本空转到「连续多轮认不出当前界面」停下等人"
             "（现场 debug/screenshots/battle_unknown_210237.png）。"
             "判据是**第 1 格底下那行小字**「进入和卡兹的战斗」"
             "（实测 (116,411,152,23) score 0.9975；选项标题「“招摇撞骗的家伙！」"
             "在同屏 y=371，不拿它当判据是因为小字那一行读得更稳、"
             "而且和点击落点分开）。"
             "**排在「事件屏」后面**：这一页和事件屏是同一个控件家族，"
             "有标题的那一页归事件集管 —— 第一页的选项小字里要是哪天也出现这句话，"
             "先认领的仍是事件屏，本行抢不走（第一页的小字实测是「“我看到你了！」"
             "与「消耗15金币，恢复30生命」那两条，本来也不撞）。",
    ),
    Screen(
        "游艺·结果屏",
        nodes=(游艺全部奖励, 游艺拒绝并触发战斗),
        handler=arcade.handle_result,
        note="游艺链第 3 屏。**必须排在转盘屏前面判**：实测 spin2/spin3 那两帧上"
             "「发射」还在屏上（0.9998 命中）而且看着还是可用的，先判发射就会"
             "在结果面板上点它一下，那一下是「白点」还是又转一次没实测过，别赌。"
             "2026-10-02 补：也认「拒绝并触发战斗」——移形变位那一支的结果面板上，"
             "标题「全部奖励」被一个物品提示框（魂晶/获得6魂晶）整个盖住读不出来，"
             "两个按钮倒是 1.000 —— 那两枚按钮只在这块面板上出现，不会认到别处。",
    ),
    Screen(
        "事件·触发战斗屏",
        nodes=(事件触发战斗,),
        handler=event_screen.handle_battle_confirm,
        check=_battle_confirm_check,
        note="事件里选了「触发战斗」那一项、又按了「确认选择」之后浮出来的确认行，"
             "点它才真进战斗（2026-10-03 加：事件「电音歌手」选第 2 格之后脚本"
             "报「未知界面」停在这一屏，现场 _now_unknown.png）。"
             "**排在这里是为了躲「拒绝并触发战斗」**：本屏的 expected「触发战斗」"
             "是它的子串，排在结果屏后面就永远不会抢在它前面。"
             "另有一道 check 挡事件屏的小字说明，见 _battle_confirm_check。",
    ),
    Screen(
        "移形变位屏",
        nodes=(游艺移形变位,),
        handler=arcade.handle_morph,
        note="游艺链第 2 屏的**另一支**（2026-10-02 第一次见：地点屏之后来的"
             "不是转盘、是「移形变位」小游戏）。用户 2026-10-02：「游艺事件,"
             "有三种, 均为拒绝」——这一支按 开始→**等 5s**→固定第 1 格 走"
             "（那一等 2026-10-03 由\"等就绪字 + 等画面停稳\"改成固定 5 秒，"
             "见 arcade.SPIN_WAIT），之后的「拒绝并触发战斗」照旧归上面的结果屏那行。"
             "判据只认标题「移形变位」：「开始」是个通用词，别的屏也可能有，"
             "只当点击目标、不当判据（点它时用 guard 拴回标题）。"
             "也排在结果屏后面：面板若盖上来，先判结果屏（同转盘屏的道理）。",
    ),
    Screen(
        "最佳轮换屏",
        nodes=(游艺最佳轮换,),
        handler=arcade.handle_rotation,
        note="游艺链第 2 屏的**第三支**（2026-10-02 第一次见：地点屏点完"
             "「“被迫加入”」直接跳进这一屏，标题「最佳轮换」在顶部中间）。"
             "用户 2026-10-02 定的走法：「点开始, 然后等6s, 点击选定了, 然后拒绝」"
             "（先说 3s，当场改成 6s；那一屏**按完「开始」不换屏**，只在原地换成"
             "「剩余2次机会 / 换一个 / 选定了！」）。"
             "**2026-10-03 用户把这一等统一定成 5 秒**（「c 最佳轮换…均改为等5s」）"
             "—— 实现从此是固定 sleep，不再等就绪信号（见 arcade.SPIN_WAIT）。"
             "判据只认标题「最佳轮换」——「开始」是通用词，别的屏也可能有，"
             "只当点击目标、不当判据（点它时用 guard 拴回标题）。"
             "也排在结果屏后面：面板若盖上来，先判结果屏（同转盘屏的道理）。"
             "实跑证据 debug/run_1002v.log：选定了！→ 拒绝并触发战斗 → 22 回合胜 → 离开。",
    ),
    Screen(
        "游艺·转盘屏",
        nodes=(游艺转盘, 游艺发射),
        handler=arcade.handle_wheel,
        note="游艺链第 2 屏（含刚进来还没转的那帧：「发射」是亮的）",
    ),
    Screen(
        "大转盘屏",
        nodes=(游艺大转盘, 游艺停止),
        handler=arcade.handle_bigwheel,
        note="游艺链第 2 屏的**第四支**"
             "（2026-10-02 第一次见，脚本当场报「未知界面」停下，"
             "现场 debug/screenshots/battle_unknown.png）。"
             "**不专属「盛大游艺」** —— 2026-10-03 用户：「大转盘并不是盛大游艺独有」"
             "「\"盛大游艺\"与普通\"游艺\"没有区别」；此前这里写的"
             "\"只有「盛大游艺」走得进来\"是一次样本的推断，已推翻。"
             "用户 2026-10-02 定的走法是"
             "「转动轮盘」→ **转起来要手动停**（按钮写「停止」）→ 照旧拒绝；"
             "中间那一等 2026-10-03 改成固定 5 秒（三支统一，见 arcade.SPIN_WAIT）。"
             "判据收两个：标题「大转盘」（没转时）和「停止」（转起来之后）——"
             "后者是**转着的那一帧上唯一能认的字**，脚本若在转动中途重启，"
             "靠它才接得回来（进入姿势两种都接，同 handle_morph）。"
             "也排在结果屏后面：面板盖上来先判结果屏，"
             "免得在面板上又按一次「转动轮盘」（同转盘屏的道理）。"
             "⚠️ 它和「游艺·转盘屏」的按钮**不在一个位置**（「转动轮盘」在右边 "
             "(981,358)，「发射」在底下 (585,550) 一带），别混。",
    ),
    Screen(
        "游艺·拒绝后屏",
        nodes=(游艺拒绝后,),
        handler=arcade.handle_refuse,
        note="游艺链第 4 屏：标题读不出来，只能靠屏上的字认",
    ),
    Screen(
        "事件结果屏",
        nodes=(赶紧离开,),
        handler=event_result.handle,
        # 兜底屏：「赶紧离开」和「离开地点」同族 —— 地点屏家族通用的控件，
        # 过渡帧上会先于真屏的字画出来，所以照样复认一道。
        recheck=True,
        note="事件结果屏：没有标题，只能靠「赶紧离开」认（所以排在事件屏后面）",
    ),
    Screen(
        "已激活护符屏",
        nodes=(选择1个已激活护符,),
        handler=amulet_pick.handle,
        note="**「选择1个已激活护符，…」那一屏**（2026-10-04 第一次见）：三行护符名 + "
             "右下角「离开地点」。它出现在事件「狭缝」选“坠入”＋「确认选择」之后"
             "（那一局 6 次「狭缝」：2 次直接进首领战、1 次进选卡屏、3 次先落到这里）。"
             "**必须排在「通用离开屏」前面** —— 那行的判据只有「离开地点」，"
             "排在前头就把这一屏抢走：2026-10-04 就是这么丢了三次首领战"
             "（debug/run_1004_new_1123.log 第 348 / 535 / 751 行，现场帧 "
             "debug/_probe_lu2/113739_*、114609_*、120042_* 三组）。"
             "走法**没定过策略**，用户那天选的是「停下等你」——"
             "本行只停车，见 nodes/amulet_pick.py。",
    ),
    Screen(
        "通用离开屏",
        nodes=(离开地点,),
        handler=leave.handle,
        # 兜底屏：「离开地点」**每个地点屏都有**，屏正在换的那一两帧上，
        # 新屏的字还没画出来、这枚按钮先画出来了 —— 它就会凭这一枚控件抢先
        # 认领。要用整表复认挡一道，见 _confirm（2026-10-06 那一停就是它）。
        recheck=True,
        note="通用「离开地点」——兜住所有没专属策略的地点；必须排在地点专属之后",
    ),
    Screen(
        "地图屏",
        nodes=(地图界面,),
        handler=map_view.handle,
        note="地图：报出可前往的节点，停车等人选路",
    ),
    Screen(
        "单选项屏",
        handler=event_screen.handle_single_option,
        check=_single_option_check,
        # 兜底屏：判据只有"选项区里恰好一行"，本来就是最弱的一条，
        # 又排在最后一行（帧最旧），所以照兜底屏的规矩复认一道。
        recheck=True,
        note="**单选项保底**（用户 2026-10-03）：「设置一个保底机制, 当只有一个选项, "
             "且没有离开按键时, **双击该选项**」。判据只有一条 —— 选项区里恰好一行"
             "小标题（和事件屏同一套菱形控件，见 `_single_option_check`）；"
             "现场是「失修封印」那条战斗支线的叙事结果页，"
             "debug/screenshots/live_probe_3.png：正文 + 唯一一行「✦战斗」，"
             "**没有标题、没有「离开地点」**。从前它是靠两个一次性手操脚本走掉的"
             "（debug/click_battle_opt.py / debug/confirm_battle.py）。"
             "排在这里的四条理由，每条都不能动："
             "① 在**事件屏**后面 —— 有标题的单选项屏（游艺、先行者）归事件集，"
             "那是定过策略的路；② 在**事件结果屏**后面、③ 在**通用离开屏**后面 —— "
             "这两行先认领，本行走到时 `赶紧离开`/`离开地点` 必然不在这一帧上，"
             "用户那句「且没有离开按键」就是靠这个位置兑现的，本行自己没有这条判据；"
             "④ 在**地图屏**后面（也就是全表最后一行）—— 兜底的规则**绝不能抢在"
             "地图前面**：地图上一记误双击 = 脚本自己挑了一条路，而挑路是策略"
             "（只按优先表走、定不了的停下问人）。这一条由 "
             "tools/check_screens.py 的顺序断言钉着。"
             "量过的两件事（2026-10-03，离线帧、只跑识别不点击）："
             "① 15 张地图整屏帧上 `option_rows` **全是 0 行** —— 兜底在地图上没有"
             "可点的一行；② 存档里唯一一张「恰好一行」的非本屏帧是 map_not_here.png"
             "（路口屏「“前往旧城-山坡”」），它前面隔着路口屏、事件屏两道；"
             "真万一本行接住了它，双击第 1 行也正是 fork.py 定的规矩"
             "（ROW_INDEX=0、「均选择1」），不会走岔道。",
    ),
    ]


def identify(g, image=None):
    """看一眼这一帧是哪一屏。**纯识别，一个东西都不点。**

    image=None 时**只截一张**、全表复用 —— 一次扫掠一帧，这是性能铁律
    （截图 0.01s，识别 0.09~0.8s/节点，多截几张纯属浪费）。
    """
    if image is None:
        image = g.capture()
    for screen in SCREENS:
        hit = _match(screen, g, image)
        if hit is not None:
            return hit
    return None


def _match(screen, g, image):
    """这一帧是不是 `screen`。是就返回 Hit，否则 None。

    两道判据都要过：**nodes**（命中任一即算）和 **check**（返回 None = 不是这屏）。
    从前 nodes 命中之后，check 的结果只被当成"证据"、拦不住 —— `dict(x or {})`，
    于是"光看节点不够、还得再补一条"的屏写不进来。死亡屏 2026-10-02 就栽在这：
    它的第二条判据（屏上没有字）根本没法表达。
    现在 check 是**真闸**：返回 None 就是不认这一屏，哪怕 nodes 全命中。
    只靠 nodes 的、只靠 check 的、两道都要的，走的是同一条逻辑。
    """
    matched = tuple(n for n in screen.nodes if g.see(n, image)) if screen.nodes else ()
    if screen.nodes and not matched:
        return None
    if screen.check is None:
        return Hit(screen, matched, {}) if matched else None

    evidence = screen.check(g, image)
    if evidence is None:
        return None
    return Hit(screen, matched, dict(evidence))


def _identify_before(g, stop):
    """现截一帧，**只扫 `stop` 那一行前面的屏**，返回第一屏命中的 Hit（没有就是 None）。

    和 `identify` 的关系一句话说得清：整表扫到 `stop` 就停。
    **结果与整表扫的"第一屏命中"逐条相同** —— `identify` 本来就是按表序取
    第一个命中，而 `stop` 那一行自己（以及它后面的）由调用方负责，不在这儿重判。
    省下来的是短的那一段：真屏排在前面时扫到它就返回，不必走到底。
    """
    image = g.capture()
    for screen in SCREENS:
        if screen is stop:
            break
        hit = _match(screen, g, image)
        if hit is not None:
            return hit
    return None


def _confirm(g, hit, times, gap):
    """**复验**：隔一下再截一张，先重跑命中那屏的判据；兜底屏再多一道整表复认。

    第一道（每一屏都过）：**命中那屏还在不在**。挡的是单帧噪声与退场残帧 ——
    OCR 把「仪式配置」读成「つ仪式配置」那种，以及"刚点完、屏还在退场"那一两帧。
    代价是毫秒级的一次 probe，不是整表翻倍。
    **挡不住"屏是真的、按钮还没画出来"** ——那是 handler 的准备度问题，
    见 docs/zh_cn/架构与流程图.md 的「屏模块四条契约」第 4 条（篝火事故就是它）。

    第二道（**只有 `screen.recheck` 的兜底屏**才过）：现帧上**整表复认一遍**，
    认到比这一屏更靠前的屏就**改判成它**。返回值从 bool 改成 `Hit | None`
    就是为了它 —— 复验不只会说"还算数"，也得能说"你认错了，是那一屏"。

    它治的是「**过渡帧**」这一整类（2026-10-06 逮到第一例）：
    `identify` 一轮只截一张图（快路径那条铁律），而 31 行扫下来要约 3 秒，
    所以**靠后的行判的是一张 3 秒前的帧**。屏正在换的时候，地点屏的壳
    （顶栏 + 右下那枚「离开地点」）先画出来了、新屏的字还没画：
    第 29 行「通用离开屏」凭「离开地点」命中，而真屏「已激活护符屏」（第 28 行，
    判据是左上角那行「选择1个已激活护符」）在旧帧上**一个字都没有**
    （`all_results_=[]` + `Wrong ocr_result size`）。第一道复验拦不住这件事 ——
    「已激活护符屏」**自己也有「离开地点」**，0.15 秒后再看照样在。
    现场就是 debug/screenshots/leave_generic.png：离线拿本表认它，
    认出来的正是「已激活护符屏」。代价是每次命中兜底屏多一次扫掠
    （量到约 2.8 秒；那一局 106 秒里兜底屏命中 4 次）。
    """
    for _ in range(times - 1):
        time.sleep(gap)
        if _match(hit.screen, g, g.capture()) is None:
            return None
    if hit.screen.recheck:
        better = _identify_before(g, hit.screen)
        if better is not None:
            return better
    return hit


def watch(g, unknown_limit=10, interval=0.8, deadline=None,
          confirm_times=2, confirm_gap=0.15):
    """**循环读取**：反复现截现认，认出（且连续 confirm_times 帧都在）才返回。

    这就是"读取一帧后必须等待处理"的反面 —— 认不出不是拿旧帧硬判，
    而是**再读一帧**；过场、加载、退场动画都靠这个循环自然吸掉。

    unknown_limit 是"连续多少次没认出来就认输"（返回 None），
    这是**轮数**语义、不是墙钟：老的 battle.play() 是"10 轮 ×(整轮扫掠+0.8s)"，
    量级在半分钟上下。deadline 只是兜底，防"两屏闪烁、永远命不中也不落空"。
    """
    misses = 0
    started = time.monotonic()
    while True:
        hit = identify(g)
        if hit is not None:
            # `_confirm` 可能**改判**（兜底屏复认认到更靠前的屏）——
            # 交回的是它给的那一屏，不是刚才 `identify` 认的那一屏。
            confirmed = _confirm(g, hit, confirm_times, confirm_gap)
            if confirmed is not None:
                return confirmed
        misses += 1
        if misses >= unknown_limit:
            return None
        if deadline is not None and time.monotonic() - started >= deadline:
            return None
        time.sleep(interval)


# describe() 兼收的**展示专用**节点：它们不是主表的一部分（不在局内流程里
# 驱动动作），只是让"现在停在哪"印得清楚些。debug/play.py 用它代替从前那份
# 手抄的 HERE 清单 —— 那份清单已经漏过一次（游艺三屏）。
# 顺序即优先级，和主表同理。
DISPLAY_ONLY = (
    标题界面,
    仪式配置界面,
    公告界面,
    获得物品,
    主界面,
    )


def describe(g, image=None):
    """现在停在哪一屏。给 debug/play.py 印一行"当前停在:"用。

    先问主表；主表都不认（局外屏：主界面/标题/仪式配置/弹窗…）再看
    DISPLAY_ONLY。都认不出返回 None —— **不猜**。
    """
    if image is None:
        image = g.capture()
    hit = identify(g, image)
    if hit is not None:
        title = hit.evidence.get("title")
        return f"{hit.screen.name}「{title}」" if title else hit.screen.name
    for node in DISPLAY_ONLY:
        if g.see(node, image):
            return node
    return None
