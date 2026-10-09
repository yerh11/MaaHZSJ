"""《魂坠深境》自定义自动化脚本。

架构分工：
    assets/resource/pipeline/*.json  —— 识别库，定义"每个界面长什么样"
    本文件                            —— **原语层**：Game 类（截图 / 识别 / 点击 / 等待 / 战斗 / 退局）
    流程逻辑                          —— script/battle.py 主循环 + nav/nodes/combat/system 四个屏包

pipeline 中的节点在这里被当作"识别探针"：只取其 recognition 定义，
配合一张截图直接调 Tasker.post_recognition，不执行动作、不走任务调度器。
识别定义仍可用 JSON 维护并享受 save_draw 可视化调试，
而循环、计次、状态判断等复杂逻辑全部由 Python 承担。

性能提示：
    截图 0.01s(EmulatorExtras)，一次识别 TemplateMatch 约 0.09s、OCR 约 0.8s。
    OCR 慢在整屏推理，给 pipeline 节点加 roi 限定区域可显著加速。
    wait_for 每轮只截一次图，对多个节点复用，切忌每个节点各截一次。

**截图的规矩（2026-10-02 重做后）**：`probe()`/`see()`/各读屏方法**不传 image
就是现截一张**（0.01s，便宜）；只有"一次扫掠要问很多节点"的循环才显式把
同一帧传下去（`wait_for`、`recognizer.identify` 都这么做）。反之，
**动手之前必须现读**：点按钮用 `click_when()`，读数字不传 image ——
绝不拿"认屏那一刻"的旧帧去点、去读（三起事故都是这个病）。

运行:
    python script/battle.py
    —— 本文件被它 import、不再是入口。合并进 script/core/ 之后也**不能再直接跑**：
       `python script/core/auto.py` 会把 core/ 当 sys.path 根，`from strings import`
       当场 ModuleNotFoundError。原先那个 Demo `main()` 已随这次搬家删掉。
"""

import io
import re
import sys
import time
from pathlib import Path

# ⚠️ `line_buffering=True` 不能省：这个包装**会把 `python -u` 的效果抵消掉**
# （2026-10-02 实测：`python -u script/battle.py > log` 的日志文件空了一分多钟）。
# `-u` 只作用于**原来的** sys.stdout，换成新 wrapper 之后又变回整块缓冲 ——
# 夜里的运行日志要等攒够 8KB 才落盘，出事了打开是空的。见 battle.py 同款注释。
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

import maa.pipeline as mpl
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

import numpy as np
from PIL import Image
from strings import (
    严酷,
    主界面,
    公告界面,
    点击任意空白处关闭,
    返回,
    仪式结算,
    仪式配置界面,
    关闭评价弹窗,
    每日签到,
    同化提示,
    同化确定,
    夜巡人选项,
    夜巡人选项确认,
    护甲牌选项,
    护甲牌选项确认,
    弃牌提示,
    弃牌确定,
    弃牌选牌,
    敌方选卡提示,
    选卡确定,
    设置,
    放弃此轮游戏,
    暂停菜单,
    关闭暂停,
    最后机会,
    死亡黑屏,
    化形信使,
    挣扎,
    离开地点,
    启动祭坛,
    噩梦1层,
    噩梦2层,
    噩梦3层,
    噩梦4层,
    噩梦5层,
    噩梦6层,
    噩梦7层,
    噩梦8层,
    噩梦9层,
    困难,
    坠入深境,
    战斗胜利,
    普通,
    本局游戏不再提示,
    极难,
    获得物品,
    标题界面,
    直接离开,
    离开确认弹窗,
    自动出牌,
    回合数,
    结束回合,
    逃离战斗,
    地图界面,
    险恶,
    )
from shared.reasons import (
    FINISHED,
    )
# 固化坐标收在 shared/coords.py（1280x720 基准）。这里把模块级四个常量 import 回来，
# 名字不变 —— `debug/quit_run.py` 还 `from core.auto import INFO_BTN, PANEL_BACK`。
from shared.coords import (
    ASSIM_STEP,
    ASSIM_X_LEFT,
    ASSIM_X_RIGHT,
    ASSIM_Y,
    DAILY_X,
    DIFF_ROI,
    DISCARD_CARD_DX,
    DISCARD_CARD_DY,
    ENEMY_PICK,
    INFO_BOX_TAP,
    INFO_BTN,
    PANEL_BACK,
    WHEEL_STEP,
    WHEEL_X,
    WHEEL_Y,
    )
# 输出一律走 `log()`（带 `[HH:MM:SS]` 前缀）—— 全脚本唯一的口，见 shared/kit.py。
from shared.kit import log

GAME_PACKAGE = "com.chillyroom.containerofsoul.yw"
# 本文件在 script/core/ 下 —— 比从前（script/auto.py）深了一层，所以这里要回退**三层**
# 才到仓库根。少退一层会让 ROOT 落在 script/ 上，assets/resource 直接加载失败
# （搬目录时实测到的）。
ROOT = Path(__file__).parent.parent.parent.resolve()
SHOT = ROOT / "debug" / "screenshots"   # 出问题时存的现场图都落在这儿

# fight() 里"空转多久才去点一下屏幕、把残余信息框点掉"（**秒**）。
# 用户 2026-10-02 说了两遍，第二遍是看到「超能之力」那块残余框：
# 「这是卡牌信息(或者如金币等信息)的残余, 点击其他空白地方恢复」
# 「如果屏幕出现残留信息(如本次"超能之力"), 记得点掉」。
#
# ⚠️ **这两个数是拍的，还没量过**：敌人回合的演出本来就会连着好几秒什么都认不出来，
# 门槛太小就会在每次敌人回合都空点一下。但那一格是「结束回合」那枚小按钮，
# **不是我方回合时点了没反应**（实测就是这么空点到 300s 超时的），所以**点不坏**，
# 顶多是噪声 —— 宁可早一点、别让残余框挂着（用户的话：「不点掉就会一直挂着」）。
# 跑几局后拿日志里「连着 N 秒什么都没认出来」那几行对齐：正常演出到不了 6s 就说明拍对。
IDLE_CLEAR_AFTER = 6.0
IDLE_CLEAR_GAP = 8.0    # 两次空点之间至少隔这么久，免得变成连点

# fight() 里「上面那枚『结束回合』点不动了，改点下面那枚」的判据。
# 用户 2026-10-03 定的规矩（原话）：
#     「添加逻辑, 如果自动战斗的"结束回合"无法点击, 就点击下方的"结束回合"」
#
# **怎么知道"点不动"**：拿游戏自己那行「第N回合」当尺子 —— **它一动没动，
# 就说明这一下没生效**。2026-10-03 实测那一场（首领·元素法师，停在「第3回合」）：
# 游戏把上面那枚画成**灰匾**（下面那枚还是亮的金匾，两枚在同一个框里对照着看），
# 脚本连点 88 次毫无反应，而 `click_node` 一路返回 True —— 点空这件事，
# 光看返回值永远发现不了。回合数是这一屏上唯一会说话的证人。
#
# 两个条件**同时满足**才算数：
#   ① 连着 `AUTO_STUCK_CLICKS` 次点它，读到的回合数都一模一样；
#   ② 从"第一次读出没变"那一刻起，已经过去 `AUTO_STUCK_SECONDS` 秒。
# ② 是专门留给**正常情况**的：一回合里脚本本来就可能连点两三下（点完牌还在飞、
# 按钮还没消失，下一轮又点了一次），那几下当然读到同一个回合数 —— 但它们全挤在
# 几秒之内；敌人回合的演出同理。所以门槛压在 20s：正常演出够不着，
# 真卡住了 20 秒后脚本才开始自救。
# 回合数**读不出来**（None）时**不计数**，计数清零重来：宁可漏掉（继续空等到
# 超时，也就是今天这个老毛病），也不拿一次读失败当"回合没动"的证据去点那枚
# 手动按钮 —— 点错是**真的会改游戏状态**（白扔一回合），比空等严重。
#
# ---- 2026-10-03 22:13 **漏掉了第二场**，判据当场补了一条 ----
#
# 那一场（debug/run_1003_2125.log 第 875~968 行，「窃魂者」精英战）脚本连点 90 次
# 空按钮、一次都没改成点下面那枚，最后撞 300s 超时停下；现场帧
# debug/screenshots/fight_timeout.png 上游戏还停在**「敌人回合」**那条大横幅里
# （牌匾被压成 80，比第一场的 113 还暗）。
#
# 病根在**读到的原文不稳**：同一场卡死里，那张存档帧读出来的是 `8`，
# 而第一场那几张读的是 `第3回合` —— 右下角那行小字会被飘过去的伤害数字压住一半，
# OCR 时好时坏。拿原文直接比"有没有变"，就会在 `8` / `第8回合` 之间来回抖，
# **每抖一次计数清零**，于是门槛永远够不着。
# 现在比的是**归一后的数字**（见 `_round_label`）：只认数字，别的一概不算数。
AUTO_STUCK_CLICKS = 4
AUTO_STUCK_SECONDS = 20.0


def _round_label(text):
    """把「第N回合」读到的**原文**归一成那串数字；读不出数字就返回 None。

    为什么非归一不可，见上面 2026-10-03 22:13 那一段：同一场卡死里 OCR 会
    在 `8` / `第8回合` 之间抖，直接比原文 = 计数一直清零、判据从不触发。
    数字才是游戏自己那本账；「第」「回合」这些字是包装，不算信息。
    """
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or None

# capture() 撞上形状不对的坏帧时重截几次（见 capture 的说明）。
# 取 3：MuMu 那一下是偶发的，实测一次就够；留两次富余，又不至于卡在坏状态里空转。
CAPTURE_TRIES = 3

# 「残余信息框」的收掉点 `INFO_BOX_TAP`、「卡牌菜单」面板的返回点 `PANEL_BACK`、
# 战斗屏上那枚「信息」按钮的落点 `INFO_BTN`、「每日签到」面板的关闭 X `DAILY_X`
# —— **四个固化落点都搬进 `shared/coords.py` 了**（量法、存档帧、用户哪天定的，
# 全写在那边）。本文件从那儿 import 回来，名字不变：`debug/quit_run.py` 还
# `from core.auto import INFO_BTN, PANEL_BACK`。


class Game:
    """把"截图/识别/点击/等待"收敛成几个直觉方法的薄封装。"""

    def __init__(self):
        self.controller = None
        self.resource = None
        self.tasker = None

    # ---------- 初始化 ----------

    def connect(self):
        """连接 MuMu 并加载资源。adb 路径与截图方式由 Toolkit 自动探测。"""
        Toolkit.init_option(str(ROOT) + "/")

        devices = [d for d in Toolkit.find_adb_devices() if "MuMu" in d.name]
        if not devices:
            raise RuntimeError("未找到 MuMu 设备，请确认模拟器已启动")
        device = devices[0]
        log(f"设备: {device.name} @ {device.address}")

        self.controller = AdbController(
            adb_path=device.adb_path,
            address=device.address,
            screencap_methods=device.screencap_methods,
            input_methods=device.input_methods,
            config=device.config,
        )
        self.controller.post_connection().wait()
        if not self.controller.connected:
            raise RuntimeError("控制器连接失败")

        self.resource = Resource()
        self.resource.post_bundle(str(ROOT / "assets" / "resource")).wait()
        if not self.resource.loaded:
            raise RuntimeError("资源加载失败")

        self.tasker = Tasker()
        self.tasker.bind(self.resource, self.controller)
        if not self.tasker.inited:
            raise RuntimeError("Tasker 初始化失败")

        # resolution 需在首次截图后才有效，否则返回 (0, 0)
        image = self.capture()
        self._frame_shape = image.shape[:2]      # 见 capture 的形状闸
        h, w = image.shape[:2]
        log(f"分辨率: {w}x{h}")
        # 全脚本的坐标一律按 **1280x720 基准**写（收在 shared/coords.py）。
        # 这一帧之所以在别的 16:9 分辨率上也恰好是 1280x720，是**框架**干的：
        # 截图那一刻被归一成短边 720（ControllerAgent 的 image_target_short_side_，
        # 本项目没改过；见 shared/coords.py 文件头）。所以 16:9 一律没问题，
        # 非 16:9（4:3 / 21:9）会把帧变成别的尺寸、x 方向坐标全错 —— 这里**说一声**，
        # 不静默地拿歪坐标去点。
        if (w, h) != (1280, 720):
            log(f"    ! 非 16:9（归一后是 {w}x{h}，不是 1280x720）："
                  f"全脚本坐标按 720p 基准写，x 方向可能不准 —— 不假装支持")
        return self

    # ---------- 基础能力 ----------

    def capture(self):
        """截取当前屏幕，返回 numpy 数组 (H, W, 3)。

        **不缓存**（2026-10-02 改）。从前这里把最新一帧存进 self._img、
        probe() 不传图时复用它 —— 于是"忘了传图"就从"多截一张（0.01s）"
        变成"拿旧帧做判断"，三起事故（点空坠入深境 / 公告页连点两下 /
        篝火三项全没认出来）都是这一个病。
        现在**不传图 = 现截一张**：贵 0.01s，换掉一整类坑。
        需要"一次扫掠只截一张"的循环（wait_for / recognizer 那种）
        **显式传图**，让"共用一帧"变成一个看得见的决定。

        ⚠️ **形状闸（2026-10-03 加）**：MuMu 偶尔会回一帧**转了 90° 的**截图
        （实测 run_1003b.log：一路走得好好的，某一下截图变成 720x1280），
        而 pipeline 的 roi 全是按 1280x720 写的 —— 于是每个节点都"整块落在图外"，
        认屏连续多轮认不出，整局就这么停下来等人（现场见那条日志）。
        **那不是"认不出的界面"，是坏掉的一帧**，所以在这里就挡掉、重截，
        而不是往上抛给认屏层。重截一张 0.01s，比重启一局便宜得多。
        形状按 connect() 第一次截到的那张定；对不上就重试，重试完还是不对
        就原样返回（让上层照常报错，不在这里假装成功）。
        """
        want = getattr(self, "_frame_shape", None)
        if want is None:
            return self.controller.post_screencap().wait().get()
        for i in range(CAPTURE_TRIES):
            image = self.controller.post_screencap().wait().get()
            if image.shape[:2] == want:
                return image
            log(f"    ! 截图形状不对（拿到 {image.shape[1]}x{image.shape[0]}，"
                  f"该是 {want[1]}x{want[0]}）—— 重截 第 {i + 1}/{CAPTURE_TRIES} 次")
        return image

    def probe(self, node, image=None):
        """识别 pipeline 节点，返回 RecognitionDetail（含 .hit / .best_result）。

        image 为 None 时**现截一张**（见 capture 的说明）；要多个节点共用
        同一帧就显式把图传进来。

        节点若写了 roi，这里会自己裁剪再识别，然后把结果框坐标加回全屏——
        因为 post_recognition 不吃 roi（会整屏识别），而 roi 既是正确性需要
        （难度轮盘只认居中那一档，整屏 OCR 会把左右相邻档的名字一起读出来），
        也能把 OCR 的耗时压到最低。
        """
        if image is None:
            image = self.capture()

        rec = self.resource.get_node_data(node)["recognition"]
        param = dict(rec["param"])
        # roi 是调度器层的字段，不属于 J* dataclass，得摘掉自己处理
        roi = param.pop("roi", None) or [0, 0, 0, 0]
        param.pop("roi_offset", None)
        ox, oy, rw, rh = roi
        if rw > 0 and rh > 0:  # 未写 roi 时 get_node_data 会给出全零，别当成裁剪区
            ih, iw = image.shape[:2]
            # 裁之前先夹到图内。**roi 落在图外不能悄悄裁成空图**——空图喂给 OCR
            # 只会静默返回"没认到"，和真没认到长得一模一样，是标准的假判据。
            # （2026-10-02 全量帧回放时暴露：小裁剪图撞上整屏 roi，日志刷满
            #   `img is empty`，识别结果却只是"没命中"。）
            x0, y0 = max(ox, 0), max(oy, 0)
            x1, y1 = min(ox + rw, iw), min(oy + rh, ih)
            if x1 <= x0 or y1 <= y0:
                log(f"    ! probe({node})：roi={list(roi)} 整块落在图外"
                      f"（图只有 {iw}x{ih}）—— 返回 None")
                return None
            if (x0, y0, x1, y1) != (ox, oy, ox + rw, oy + rh):
                log(f"    ! probe({node})：roi={list(roi)} 超出图 {iw}x{ih}，"
                      f"已夹到 ({x0},{y0})-({x1},{y1})")
            ox, oy = x0, y0
            image = image[y0:y1, x0:x1]
        else:
            ox = oy = 0

        # get_node_data 返回 v2 格式 {type, param}，正好对应 post_recognition 的入参；
        # param 的字段与 maa.pipeline 中的 J* dataclass 一一对应
        cls = getattr(mpl, "J" + rec["type"])
        detail = self.tasker.post_recognition(
            rec["type"], cls(**param), image
        ).wait().get()
        # detail 可能是 **None**：post_recognition 认不出任务时，
        # Tasker.get_task_detail() 直接返回 None（maa/tasker.py 的 `if not ret: return None`）。
        # 什么时候认不出？最常见的是**控制器掉线** —— 引擎在 post_task() 里
        # `if (!inited())` 就 `return MaaInvalidId`，而 inited() 要求 controller 处于
        # connected 状态（MuMu 被关 / adb 被踢就会掉）。2026-10-08 那一局（第 32 局、
        # 258 场战斗）就是这么炸的：守卫写的是 `detail.node_id_list`，可 detail 自己
        # 是 None ⇒ AttributeError（现场 debug/run_1007_resume.log:11364）。
        # 这里先补 None 闸，再顺手给掉线一次自救机会（见 _recover_engine）。
        if detail is None:
            self._recover_engine()
            return None
        # 识别跑完但没命中时，没有可用的节点详情，拿不到 reco
        if not detail.node_id_list:
            return None
        node_detail = self.tasker.get_node_detail(detail.node_id_list[0])
        if node_detail is None or node_detail.recognition is None:
            return None
        reco = node_detail.recognition

        if ox or oy:
            # 三张表都得搬（都是 roi 内的坐标）：漏一张的话用它的调用方会拿到偏了
            # (ox, oy) 的框 —— 这是最阴的那种错，点下去看着"差不多在那儿"。
            boxes = [r for r in (reco.all_results or [])]
            boxes += [r for r in (reco.filtered_results or [])]
            if reco.best_result is not None:
                boxes.append(reco.best_result)
            for r in boxes:
                r.box[0] += ox
                r.box[1] += oy
        return reco

    def _recover_engine(self):
        """识别失败且引擎"未初始化"时，试着重连一次；连不上就**响**（抛 RuntimeError）。

        只在 `probe()` 拿到 `detail is None` 时被叫到 —— 那意味着引擎**根本没收下这次
        识别任务**（`Tasker::post_task` 里 `if (!inited()) return MaaInvalidId`）。
        `inited()` = resource 有效 **且 controller 处于 connected**
        （`MaaFramework/Tasker/Tasker.cpp:70-74`），所以最现实的原因是**控制器掉线**：
        MuMu 被关、adb 连接被踢，`AdbControlUnitMgr::connected()` 当场变假。

        **为什么不能就这么返回 None 算了**：从前掉线是**无声**的 —— 每个 `probe()` 都
        返回 None ⇒ `see()` 恒假 ⇒ 认屏认不出 ⇒ 主循环空转到「连续多轮认不出当前界面」
        停车。日志上看起来像"撞上了不认识的界面"，其实是掉线，**判据被伪装**。
        所以这里先自救一次，救不回来就把话说清楚（抛异常），别让它继续装死。

        **热路径零开销**：`inited` 为真时第一步就返回 —— 正常一帧几十次 probe 也
        只多一次廉价的属性查询。`inited` 为假时第一次就抛了，不会重连几十次（幂等）。
        """
        # 引擎好着呢 ⇒ 这次 detail=None 另有原因（比如识别任务本身失败），
        # 不归这里管，交回 probe 照常返回 None。
        if self.tasker.inited:
            return
        log("    ! 控制器掉线（tasker 未初始化）—— 尝试重连一次")
        self.controller.post_connection().wait()
        if self.controller.connected:
            self.tasker.bind(self.resource, self.controller)
            if self.tasker.inited:
                log("      重连成功，接着跑")
                return
        raise RuntimeError(
            "控制器掉线且重连失败 —— tasker 仍未初始化。"
            "多半是模拟器被关掉 / adb 连接断了：把 MuMu 拉起来，再 python script/battle.py 接着跑。"
        )

    def see(self, node, image=None):
        """节点是否命中，返回 bool。"""
        reco = self.probe(node, image)
        return bool(reco and reco.hit)

    def matches(self, node, image=None):
        """节点上**过了它自己写的 threshold** 的全部命中：[(box, score), ...]。

        要和 `probe()` 的 `all_results` 分清 —— 对着引擎源码核过
        （`MaaFramework/source/MaaFramework/Vision/TemplateMatcher.cpp`，`add_results`）：

          · `all_results` 是**没筛过的**候选：内部只挡了 0.5 这一条底线，一个都没过底线时
            还会把"最像的那一个"塞进来 —— 所以 0.38 这种分数也会躺在里面；
          · `filtered_results` 才是**过了 threshold** 的那批，`best_result` 就是从这儿挑的，
            引擎的 `hit` 也看它。
        拿 `all_results` 当"命中表"就是读到明明没过线的东西。2026-10-04 在这上面栽过一次：
        `debug/_cardtpl_check.py` 把"最像的一个"（0.3837）数成了命中，报出一堆假不符。

        框是全屏坐标（roi 由 `probe()` 裁、这里搬回来）。分数从高到低。
        """
        reco = self.probe(node, image)
        if reco is None:
            return []
        out = [(tuple(r.box), float(r.score)) for r in (reco.filtered_results or [])]
        return sorted(out, key=lambda bs: -bs[1])

    def wait_for(self, nodes, timeout=30.0, interval=0.3):
        """轮询等待多个节点中任意一个命中。

        返回命中的节点名；超时返回 None。nodes 顺序即优先级。
        每轮只截一次图，对全部候选节点复用。
        """
        deadline = time.monotonic() + timeout
        while True:
            image = self.capture()
            for node in nodes:
                if self.see(node, image):
                    return node
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)

    def click_when(self, node, timeout=3.0, interval=0.25, guard=()):
        """**现截现验**地按下一个按钮：guard 全在、node 也在**同一帧**上，才点。

        返回是否点到了。这是屏模块（nav/ nodes/ combat/ system/）里"点按钮"的标准写法 ——
        从前是 `click_node(节点, image)`，那个 image 是**认屏那一刻**的帧，
        而按钮可能还没画出来（「坠入深境」点空那次）、屏可能已经在退场
        （公告页被连点两下那次）。这里每轮重新截图，
        **用哪一帧验的，就用那一帧的框点**。

        guard 是"点它的时候，这一屏的标志物也得在"——维持住旧代码那层
        "同一帧耦合"（点「离开地点」时要求「篝火界面」也在这帧上）。
        handler 里的通用写法是 `guard=hit.matched`：点按钮时要求
        "认出这屏的那些节点"还在，免得屏都换了还在按旧坐标点。
        找不到就等，超时返回 False —— **不猜、不硬点**。
        """
        deadline = time.monotonic() + timeout
        while True:
            image = self.capture()
            if all(self.see(n, image) for n in guard):
                box = self.box_of(node, image)
                if box is not None:
                    # 落点用节点自己声明的（框中心 + target_offset）——
                    # 「升变确认」那种"框中心不是按钮"的节点全靠它，见 node_offset
                    self.click_box(box, self.node_offset(node))
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def click_at(self, point, guard=(), timeout=3.0, interval=0.25):
        """按一个**量出来的固定坐标**：`guard` 全在的那一帧，才点。返回点没点。

        与 `click_when` 只差"点哪儿"：那个点的是**节点自己认出来的框**（框跟着
        识别结果动），这个点的是写死的点 —— 屏上那东西**没有可识别的框**。
        第一个用它是「已激活护符屏」那一列护符名：名字每局都不一样（没有模板），
        而这一屏的版式是固定的，量一次就行，不值得为此现 OCR。
        `guard` 的作用一模一样：**点它的那一帧，这一屏的标志物还得在**
        （免得屏都换了还在按旧坐标点），所以调用点照旧写 `guard=hit.matched`。
        """
        deadline = time.monotonic() + timeout
        while True:
            image = self.capture()
            if all(self.see(n, image) for n in guard):
                self.click(*point)
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def wait_gone(self, node, timeout=5.0, stable=3, interval=0.3):
        """等一个节点**连续 stable 帧**都看不见了，才返回 True。

        **一次问不到就返回是错的**：退场动画里它还会闪回来一两帧 ——
        那就是「公告」页被连点两下的第二下：调用方以为已经走了，
        回头看它"还在"，又点一次。连续缺席才算走（stable=3、0.3s 一档
        ≈ 稳定缺席 0.6~0.9s），超时返回 False（它可能一直没走，调用方自己看着办）。
        """
        gone = 0
        deadline = time.monotonic() + timeout
        while True:
            if self.see(node):
                gone = 0
            else:
                gone += 1
                if gone >= stable:
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def box_of(self, node, image=None):
        """取节点识别结果框 (x, y, w, h)；未命中返回 None。

        ⚠️ **必须先判 `reco` 是不是 None**：`probe()` 会返回 None（roi 整块在图外 /
        没命中 / recognition 为空）。从前这里直接 `reco.hit`，reco 为 None 时当场
        AttributeError —— 而 `click_when` / `click_node` 都经这里，所以那一处漏判
        等于让它们**全部 ~50 个调用点**都埋着同一颗雷（2026-10-08 那次掉线就是这么
        炸出来的：`map.py:1335 _match_frame` → `probe` 返回 None → 这里没机会执行，
        先炸在 probe 里面）。返回 None 之后调用方本来就写着 `if box is not None` /
        `return False`，走的是它们自己那条"点不着"的路 —— 加固，不改语义。
        """
        reco = self.probe(node, image)
        if not reco or not reco.hit or not reco.best_result:
            return None
        return tuple(reco.best_result.box)

    def read_number(self, node, image=None):
        """读一个只含数字的识别节点（金币/魂晶/层数），返回 int；认不出返回 None。

        不直接用 OCR 的原文，而是正则抠出数字：这类 roi 紧贴图标，
        经常捎带一个被认成数字的图标字符（实测魂晶读出过「越6」「69」）。
        """
        reco = self.probe(node, image)
        if not reco or not reco.hit:
            return None
        text = "".join(r.text for r in (reco.all_results or []))
        m = re.search(r"\d+", text)
        return int(m.group()) if m else None

    def read_fraction(self, node, image=None):
        """读一个「当前/上限」格式的节点（生命值），返回 (当前, 上限)；认不出返回 None。

        认不出返回 None 而**不是** (0, 0)：调用方要靠 None 区分"读不到"和"真的是 0"，
        判"满血"时尤其 —— 读不到就当作未知，照旧走老路，别把未知当成"不满"。
        """
        reco = self.probe(node, image)
        if not reco or not reco.hit:
            return None
        text = "".join(r.text for r in (reco.all_results or []))
        m = re.search(r"(\d+)\s*/\s*(\d+)", text)
        return (int(m.group(1)), int(m.group(2))) if m else None

    def click(self, x, y):
        """点击绝对坐标。"""
        self.controller.post_click(int(x), int(y)).wait()

    def double_click(self, x, y, gap=0.08):
        """双击。

        地图上的节点**必须双击**才进得去（用户确认）——单击落在图标上毫无反应，
        也不报任何错，看着就像"点了没用"。实测就是这样白点了一发。

        不要用两次 post_click：那是两趟独立下发，间隔不受控，很容易超出游戏的
        双击判定窗口、被判成两次单击。这里自己拼 touch_down/up，间隔可控。
        """
        x, y = int(x), int(y)
        for i in range(2):
            if i:
                time.sleep(gap)
            self.controller.post_touch_down(x, y).wait()
            self.controller.post_touch_up().wait()

    def clear_info_box(self):
        """把挂着的**残余信息框**点掉（单击空白处，落点见 INFO_BOX_TAP）。

        这不是新规矩 —— 用户 2026-10-02 说过两遍：「这是卡牌信息(或者如金币等信息)
        的残余, **点击其他空白地方恢复**」「不点掉就会一直挂着」，fight() 里那条
        IDLE_CLEAR 就是照它写的。2026-10-03 它**骑到地图上**了：游艺结果面板上
        弹的那块奖励说明框（「蓄力印记4 / 伤害+4，但战斗开始时处于弃牌堆」，
        现场 debug/screenshots/_now_question.png）跟到地图，把可前往标记和标签
        全挡住 —— map_view 连读 3 次都是 0 个可前往，停车「等待选路」。
        用户当天：「当前页面被上一次的游艺的信息阻挡了」，并补了一条
        「翻牌时不要双击」——所以这一下**是单击**，理由见 INFO_BOX_TAP。

        **不返回真假**：收没收掉由调用方再读一眼说了算（地图那边就是"再读一次，
        看读不读得到节点"）。这里只说点过了 —— 框没上屏时点它也无害。
        """
        log(f"    点一下空白处，收掉残余信息框（单击 {INFO_BOX_TAP[0]},{INFO_BOX_TAP[1]}）")
        self.click(*INFO_BOX_TAP)

    def node_offset(self, node):
        """这个节点在管线里声明的 `target_offset` 前两位 —— **相对识别框中心的偏移**。

        从前脚本层**完全没用过它**，点的一律是识别框正中心。而声明它的两个节点
        恰恰都是"框中心不是按钮"的：

        | 节点 | offset | 为什么 |
        |---|---|---|
        | `点击空白处继续` | (0, -30) | 提示文字**上方**那条空带才是该点的地方（提示就叫你点空白） |
        | `升变确认` | (10, +73) | 那行「付出」只是**提示文字**，真按钮在它下面 73px（按钮上没字，OCR 认不到，才拿提示定位） |

        2026-10-02 用户报「当前锻造间,无畏斧升级没成功」——查下来就是这条：
        脚本点的是「付出」那四个字本身，按钮纹丝不动，于是"金币没减"，
        被当成"没得升"静静走掉；`debug/run_*.log` 里这样停了 **9 次，一次都没升成**。

        认不出来 / 没声明就返回 (0, 0)。**这条只读管线，不猜坐标。**
        """
        try:
            data = self.resource.get_node_data(node)
        except Exception as e:  # 节点名写错等
            # 这里从前是**静默** `return (0, 0)`，注释还写着「让 probe 那边去炸」
            # —— 可它自己不炸、probe 也不炸：节点名写错就等于**悄悄按识别框中心点**，
            # 点歪了日志里一个字都没有。2026-10-04 起先吱一声再降级，行为不变。
            log(f"    ⚠ 读管线节点「{node}」失败：{e!r} —— 偏移按 (0, 0) 降级")
            return (0, 0)
        param = ((data or {}).get("action") or {}).get("param") or {}
        off = param.get("target_offset") or []
        return (int(off[0]), int(off[1])) if len(off) >= 2 else (0, 0)

    def click_box(self, box, offset=(0, 0)):
        """点击识别框中心。box 为 (x, y, w, h)；offset 是相对中心的偏移。

        给"框中心不是按钮"的节点用（见 node_offset）。**认框的偏移要在这里一并算上**，
        否则识别对了、点错地方，还一声不吭 —— 那正是锻造那条路的病灶。
        """
        x, y, w, h = box
        self.click(x + w // 2 + offset[0], y + h // 2 + offset[1])

    def click_point_of(self, node, box):
        """这个节点对这个识别框会点到哪里 —— `click_box` 的算式，但**只算不点**。

        给"点完还要用同一个位置再点一次"的场合：现在唯一的用处是 fight() 里
        点掉残余信息框（用户 2026-10-02：「用来恢复信息的点击位置与自动战斗位置
        相同即可」），所以那边先记下这一场真正点「自动出牌」的坐标，别处照抄。
        """
        x, y, w, h = box
        ox, oy = self.node_offset(node)
        return (x + w // 2 + ox, y + h // 2 + oy)

    def node_roi_center(self, node):
        """这个节点在管线里声明的 `roi` 中心 —— **只读管线，不猜坐标**；没声明就返回 None。

        给"东西还没画出来、但要点它平常待的那一片"的场合（同上：点残余信息框）。
        识别框拿不到时才用到它，所以它只是**兜底**，首选永远是现认出来的框。
        """
        try:
            data = self.resource.get_node_data(node)
        except Exception as e:  # 节点名写错等（同上：先吱声，再降级到 None）
            log(f"    ⚠ 读管线节点「{node}」失败：{e!r} —— roi 按 None 降级")
            return None
        param = ((data or {}).get("recognition") or {}).get("param") or {}
        roi = param.get("roi")
        if not roi or len(roi) < 4:
            return None
        x, y, w, h = (int(v) for v in roi[:4])
        return (x + w // 2, y + h // 2)

    def click_node(self, node, image=None):
        """识别节点并按它声明的落点点击（框中心 + target_offset）。命中并点击则返回 True。"""
        box = self.box_of(node, image)
        if box is None:
            return False
        self.click_box(box, self.node_offset(node))
        return True

    def text_of(self, node, image=None):
        """取 OCR 节点的最佳文本；未命中返回 None。

        和 `box_of` 同一个雷：`reco` 可能是 None（probe 的三条返回 None 的路），
        必须先判它 —— 否则 `reco.hit` 直接 AttributeError。
        """
        reco = self.probe(node, image)
        if not reco or not reco.hit or not reco.best_result:
            return None
        return getattr(reco.best_result, "text", None)

    def snap(self, name):
        """把当前画面存成 debug/screenshots/<name>.png，出问题时回头看。

        **现截一张** —— 存的是"案发当时"的样子。
        """
        Image.fromarray(self.capture()[:, :, ::-1]).save(SHOT / f"{name}.png")

    def leave_confirm(self):
        """清掉「…是否离开？」确认弹窗：先勾「本局游戏不再提示」，再点「直接离开」。

        用户 2026-10-01 的规则。这个弹窗是**模态**的，盖在谁上面都可能
        （战斗胜利 / 始源之凝视 / 地点界面都见过），所以每个想落地点的调用方
        都得先过它。放在这里是因为几个地点脚本 + battle.py 都要用同一套动作。

        勾选框**见到就点**：它还在，就说明还没勾上——真勾上了弹窗压根不出现。
        **顺序不能反**：先勾（那是"本局不再提示"的设置），再点「直接离开」。

        每一步都现截现验（click_when）：从前是"点完勾 sleep(0.8) 再点离开"，
        那个 0.8s 是猜的；现在等「直接离开」真的画出来才点，点完等弹窗真的退场
        才返回（wait_gone）——不然调用方回头一看弹窗还在，又会点一次。
        """
        if not self.see(离开确认弹窗):
            return False

        if self.click_when(本局游戏不再提示, timeout=2.0, guard=(离开确认弹窗,)):
            log("    勾「本局游戏不再提示」")
        if self.click_when(直接离开, timeout=2.0, guard=(离开确认弹窗,)):
            log("    直接离开")
            self.wait_gone(离开确认弹窗, timeout=10)
            return True
        return False

    def leave_after(self, timeout=3.0):
        """点完「离开地点」之后：等一下确认弹窗，浮出来了就清掉。

        这个两行套路在六个屏里各抄了一遍 —— 石像 / 凝视 / 通用离开 / 祭坛 /
        篝火 / 锻造 —— 而且**每次都要想一遍 timeout 写几**。收在这儿，
        各处只写 `g.leave_after()`。

        **弹窗本来就可能不出现**（勾过「本局游戏不再提示」之后就不再弹），
        所以这里不返回"清没清掉"：等不到就是正常情况，不是失败。
        清不掉由 `leave_confirm()` 自己那两道 `click_when` 去报。
        """
        if self.wait_for([离开确认弹窗], timeout=timeout):
            self.leave_confirm()

    # ---------- 业务流程 ----------

    def start_game(self):
        """启动游戏并确保进入主界面。

        冷启动会经过标题界面；游戏已在运行时 StartApp 只是切前台，
        直接就是主界面。两条路径都要覆盖。
        """
        log("启动游戏...")
        self.controller.post_start_app(GAME_PACKAGE).wait()

        if self.wait_for([主界面], timeout=5):
            log("  游戏已在主界面")
            self.close_blockers()
            return True

        # 冷启动：先到标题界面、点进去，再经登录与加载到主界面。
        # **这一段不能写成"先 wait_for 标题、再 wait_for 主界面"两段**：
        # 公告页 / 获得物品弹窗 / 评价弹窗都会**盖在底下那一屏上面**，
        # 底下就算已经到位了，它的字也一个都认不出来 —— 于是两段都会各自空等到超时。
        # 2026-10-02 两次实测都是这么卡在开局的：
        #   一次是公告页盖着**标题界面**，「点击任意处开始」整屏被挡，
        #     `wait_for([标题界面])` 90 秒一次没命中；
        #   一次是登录时弹的「获得物品」（月卡奖励）盖着**主界面**，同样认不出来。
        # 所以这里合成一段循环：每轮**先清遮挡物、再看底下是哪一屏**。
        deadline = time.monotonic() + 150
        last_title_click = 0.0
        while True:
            # 顺序不能反：遮挡物盖着的时候，底下的判断全是假的
            if self.close_one_blocker():
                continue

            image = self.capture()
            if self.see(主界面, image):
                log("  已进入主界面")
                break

            # 点过一次就别每轮都点；隔几秒还没走说明那一下没落上，允许再点
            if self.see(标题界面, image) and time.monotonic() - last_title_click > 6:
                log("  到达标题界面，点击进入")
                self.click_node(标题界面)
                last_title_click = time.monotonic()
                # 等它真的退场（登录/加载可能好几十秒——那是"走了"，
                # 等到了就继续下一轮看底下到了哪一屏）
                self.wait_gone(标题界面, timeout=8)
                continue

            if time.monotonic() >= deadline:
                log("  未能进入主界面")
                return False
            time.sleep(0.5)

        self.close_blockers()
        return True

    def close_one_blocker(self):
        """认到一个遮挡物就清掉它，返回是否清掉了。

        遮挡物 = 盖在底下那一屏上面、不点掉就永远看不见底下内容的东西。目前四种：
          · 「公告」页       热更之后首次冷启动自动弹，出口是左上角那支返回箭头
          · 「获得物品」弹窗  登录时弹（月卡奖励那一版，整屏），出口是底部「点击任意空白处关闭」
          · 「评价邀请」弹窗  每日首次启动弹，出口是右上角的红 X
          · 「每日签到」面板  2026-10-05 一整局收尾回主界面时盖上来（现场帧
            `loop_notmain.png`），出口是右上角那枚蓝 X —— **点固定坐标**（见 DAILY_X）

        四个都不是"要选"的东西：「获得物品」只是把已经发到手的东西摆出来给人看，
        它自己写着唯一的出口是"点击任意空白处关闭"，点那行提示就是照它说的办
        （节点「点击任意空白处关闭」在 结算.json，本来就为这类弹窗量过 roi）。

        **这份局部判据子集留在这里，不并进 recognizer 的主表** —— 并进去就等于
        局内遇到公告/获得物品会被自动点掉，而现在是"未知 → 停车等人"，
        那是策略变化，用户没定过。

        **点完要等它真的退场再返回**（wait_gone：连续缺席才算走）。
        退场动画那几帧上它还在，调用方立刻回头看就会当它没被点掉、再点一次 ——
        2026-10-02 实测「公告」页就是这么被连点两下的，第二下落在已经退回去的
        标题界面左上角。
        """
        if self.see(公告界面) and self.click_when(返回, guard=(公告界面,)):
            log("  关掉「公告」页（点左上角返回）")
            self.wait_gone(公告界面, timeout=10)
            return True
        if self.see(获得物品) and self.click_when(点击任意空白处关闭, guard=(获得物品,)):
            log("  关掉「获得物品」弹窗（点底部提示关掉）")
            self.wait_gone(获得物品, timeout=10)
            return True
        if self.see(关闭评价弹窗) and self.click_when(关闭评价弹窗):
            log("  关掉评价弹窗")
            self.wait_gone(关闭评价弹窗, timeout=10)
            return True
        # 2026-10-05 加：那一整局收尾时盖在主界面上的「每日签到」面板（现场图
        # loop_notmain.png）。走独立方法是因为**收尾那条路也要它**（见 close_daily_panel）。
        if self.close_daily_panel():
            return True
        return False

    def close_daily_panel(self, image=None):
        """清掉「每日签到」面板，返回是否清掉了（2026-10-05 加）。

        **出口用户当天定**：「点右上角 X 关掉（**不领**）」—— 照「评价弹窗」那枚
        红 X 的先例。所以这里点的是 `DAILY_X` 那个量出来的固定坐标（`click_at`），
        识别只拿来判"这一屏在不在"（`guard` 就是它：点下去的那一帧标题还得在）。

        **两个调用点共用这一个方法**：启动那条路（`close_one_blocker`）和收尾那条路
        （`settlement.finish_run`）。收尾那边把**手上现成的那一帧**传进来（`image`）——
        它的循环里每轮本来就截一张，不能让这里再各截一张（`close_one_blocker`
        一次要过四个遮挡物，全走 `see()` 自己截图的话一轮多花三秒多）。
        """
        if self.see(每日签到, image) and self.click_at(DAILY_X, guard=(每日签到,)):
            log("  关掉「每日签到」面板（点右上角 X，不领）")
            self.wait_gone(每日签到, timeout=10)
            return True
        return False

    def close_blockers(self, max_count=5):
        """反复清遮挡物，直到清不动为止，返回清掉的数量。

        每轮都现截现问（close_one_blocker 自己现截）——这个循环问的正是
        "点掉这个之后还有没有下一个"，拿同一帧反复问只会一直得到第一次的答案，
        于是要么一次都不清，要么闭着眼睛连点 max_count 次（后几次点在空处）。

        退场等待在 close_one_blocker 里，这里不重复等。
        """
        count = 0
        while count < max_count:
            if not self.close_one_blocker():
                break
            count += 1
        return count

    # ---------- 开局流程 ----------

    # 难度轮盘由易到难，与 pipeline 中的节点一一对应。
    # 14 档**一个个写全**，不用 `f"噩梦{i}层"` 推 —— 这串名字就是游戏印在轮盘上的字，
    # 字本身归 strings.py 管（第二节，顺序与这里一致），这里只是把它们按难易排好队。
    DIFFICULTIES = [
        普通, 困难, 险恶, 严酷, 极难,
        噩梦1层, 噩梦2层, 噩梦3层, 噩梦4层, 噩梦5层,
        噩梦6层, 噩梦7层, 噩梦8层, 噩梦9层,
    ]

    # 难度轮盘的几何（居中项图标中心、左右项间隔）与 `DIFF_ROI`（居中项名字那条窄
    # 区域，用来确认当前选中的是哪一档）已搬进 `shared/coords.py`。**保留同名类属性**
    # —— `debug/test_wheel.py` 直接引 `Game.WHEEL_X` / `WHEEL_STEP` / `WHEEL_Y`。
    WHEEL_X = WHEEL_X
    WHEEL_STEP = WHEEL_STEP
    WHEEL_Y = WHEEL_Y
    DIFF_ROI = DIFF_ROI

    def current_difficulty(self, image=None):
        """当前选中的难度（轮盘正中那一档），认不出返回 None。

        只对居中项名字那一小块 roi 做一次 OCR，再拿文本去匹配名字。
        挨个难度节点试最坏要 14 次 OCR（约 3 秒），而选难度时要反复调用它，太慢。

        不带 image 时现截一张（probe 的通行语义）——这是个"查当前状态"的接口，
        从前 probe 复用缓存帧，拿旧图查会一直返回上一次的结果，那类坑已经拆了。
        """
        if image is None:
            image = self.capture()
        ox, oy, rw, rh = self.DIFF_ROI
        detail = self.tasker.post_recognition(
            "OCR", mpl.JOCR(), image[oy:oy + rh, ox:ox + rw]
        ).wait().get()
        # 同 probe()：detail 可能是 None（引擎没收下任务，多半是掉线）——
        # 先补 None 闸，再给掉线一次自救机会。
        if detail is None:
            self._recover_engine()
            return None
        if not detail.node_id_list:
            return None
        node_detail = self.tasker.get_node_detail(detail.node_id_list[0])
        if node_detail is None or node_detail.recognition is None:
            return None
        text = "".join(r.text for r in (node_detail.recognition.all_results or []))

        # 先按完整名字匹配（噩梦2~9层都带数字，互相不会误伤）
        for name in self.DIFFICULTIES:
            if name != 噩梦1层 and name in text:
                return name
        # OCR 有时把「严酷」拆成两半，只读出其中一个字
        if "严" in text or "酷" in text:
            return 严酷
        # 剩下的「噩梦」两个字没带数字，那就是 1 层——它的标签本来就只有两个字
        if "噩梦" in text:
            return 噩梦1层
        return None

    def select_difficulty(self, target, max_clicks=30):
        """把难度轮盘切到 target。

        用点击不用滑动：实测滑动会被游戏吞——连滑 13 次只走了 12 档，
        中间还有一档完全没动，最后停在「噩梦7层」而不是「噩梦9层」。
        点击则是"点哪个哪个立刻居中"，而且每点一次都重新识别居中项再决定下一步，
        某次点击被吞了也会自己纠正回来。

        **一次只点一档**（±142px），绝不跨档点远处的项——比如从噩梦7层
        直接点噩梦9层那一下，即使目标在屏幕上可见也不许点，
        必须 7→8→9 一档一档走。跨档点击的落点依赖"当时那一项正好在哪个位置"，
        轮盘一旦有滚动惯性或动画位移就会点偏，且偏了还不知道停在哪一档；
        一档一档走每步都能被 current_difficulty() 验证，错了立刻纠正。
        """
        if target not in self.DIFFICULTIES:
            raise ValueError(f"未知难度 {target!r}")
        want = self.DIFFICULTIES.index(target)

        for _ in range(max_clicks):
            cur = self.current_difficulty()
            if cur is None:
                raise RuntimeError("认不出当前难度，界面可能不在仪式配置")
            delta = want - self.DIFFICULTIES.index(cur)
            if delta == 0:
                log(f"  难度已选: {cur}")
                return True
            self.click(
                self.WHEEL_X + self.WHEEL_STEP * (1 if delta > 0 else -1),
                self.WHEEL_Y,
            )
            time.sleep(0.7)

        raise RuntimeError(
            f"点了 {max_clicks} 次也没到「{target}」，当前是「{self.current_difficulty()}」"
        )

    def enter_run(self, difficulty=普通):
        """主界面 → 仪式配置 → 选难度 → 坠入深境。"""
        if not self.see(仪式配置界面):
            if not self.click_node(启动祭坛):
                raise RuntimeError("主界面上找不到「启动祭坛」")
            if not self.wait_for([仪式配置界面], timeout=15):
                raise RuntimeError("没进到仪式配置界面")
        self.select_difficulty(difficulty)

        # **现截现验地点它**。从前这里是 wait_for + click_node 两步，
        # 还带一段"再 wait 一次坠入深境"的补丁；病根是那两步之间夹着的残影帧：
        # wait_for 一命中就返回，它留在缓存里的是**转场刚开始**的那一帧，
        # 横幅还没画出来，拿它点的这一下必然落空 —— 整个 run 卡在开局
        # 报"坠入深境失败"，而下一帧它明明就好好地在那儿（battle_norun.png 为证）。
        # click_when 每轮重新截图：**验到横幅的那一帧，才用那一帧的框点**。
        # guard 要「仪式配置界面」也在：横幅是这一屏上的东西，屏不在了就别点。
        return self.click_when(坠入深境, timeout=10, guard=(仪式配置界面,))

    def quit_run(self):
        """**局内退出这一局**：卡牌菜单 → 设置 → 「放弃此轮游戏」 → 结算屏。True = 已到结算屏。

        用户 2026-10-02 睡前定的：「如果遇到不认识的事件, 直接记录下来, 然后退出这把
        游戏, 重新开始」。这条链**从前一直没做成脚本**（battle.ensure_main 里那句
        "局内反向退出要连过 卡牌菜单 → 设置 → 放弃此轮 → 继续 → 结束探索 一长串界面，
        分支多、还容易卡在某个确认弹窗上"就是它），所以每一步都**现截现验**、
        认不出就把现场图存下来交回上层 —— 只有第 1 步例外（点固定坐标，见下）。

        ---- 2026-10-04：第 1 步改成**点固定坐标**，不再做识别 ----

        那枚「信息」图标的位置是固定的（用户原话：「"信息" 选项, 是固定位置的」，
        量法见 INFO_BTN）。原先要求 `卡牌菜单` 模板命中，可它在某些战斗屏上整枚
        发亮、模板分掉到 0.43；2026-10-04 窃魂者那场打满 5 分钟触发这条退出链时，
        就卡死在第一步，存 `quit_run_nomenu.png` 停下等人 —— 而图标明明就在那儿。
        现在直接点 INFO_BTN，开没开由下一步的齿轮兜住（点空了也就是退回上层，
        同一个失败方式，不会乱点别处）。

        **为什么不能拿"杀进程重开"代替**（2026-10-02 21:57 实测）：局内有一局没打完时，
        冷启动会**接着那一局继续**，永远是局内 —— 想退出只能在游戏里退出。

        四个节点早就在管线里（通用.json 的 `卡牌菜单`/`设置`、暂停.json 的
        `暂停菜单`/`放弃此轮游戏`），是照用户 2026-10-01 给的走法建的。
        顺序照旧（先开面板、再点面板里的齿轮）—— 虽然地图屏右上角本来就摆着一枚
        齿轮，但"直接点它是不是同一个暂停菜单"没人验过，不抄那条近路。
        （2026-10-02 修正一条旧话：从前写的是「齿轮只出现在卡牌菜单面板里」，
        不对，证据见 通用.json 的 `设置` 节点注释。）

        只负责走到**结算屏**为止。后面那串收尾（「继续」→ 星空过场 →「结束此次探索」
        ×2 →「获得物品」弹窗 → 主界面）是 system/settlement.py 的 finish_run() 的活
        —— 那边幂等、从哪一屏接上都能走完，退出和正常打完走的是同一条收尾。

        ⚠️ **「放弃此轮游戏」点下去之后会先弹什么，没验过**（这条链第一次做成脚本）。
        这里只等「结算屏 / 主界面」两种结果：等不到就存图停下，**不猜那个框上有什么按钮**。

        ---- 2026-10-02 第一次真跑（debug/quit_run.py dry）撞出来的两件事 ----

        1. **`设置` 的 roi 是那次加的**：卡牌菜单点下去后面板要淡入，那几帧上面板还
           没盖住右上角，地图屏自己那枚齿轮先命中，脚本照着**它的**位置点了一下 ——
           点空，面板开了也没人点里面那枚。见 通用.json 的 `设置` 节点注释。
        2. **「关闭暂停」退回的是那个面板，不是游戏**。面板不在认屏表里，留着它
           主循环下一轮会认成「地图屏」（地图节点照样命中）却把点击全打进面板里 ——
           所以下面退出来之后**必须再点一下面板左上角**把它也收掉（见 PANEL_BACK）。
        """
        log("    退出这一局：信息（固定位置）→ 设置 → 放弃此轮游戏")
        # 第 1 步**不识别了**：那枚「信息」图标的位置是固定的（见 INFO_BTN，
        # 用户 2026-10-04：「"信息" 选项, 是固定位置的」）。原先要求 `卡牌菜单`
        # 模板命中，可它在某些战斗屏上整枚发亮、模板分掉到 0.43（0.7 才过线），
        # 位置却一动不动 —— 2026-10-04 窃魂者那场超时就卡死在这一步。
        self.click(*INFO_BTN)

        # 点的是**面板里**那枚齿轮。面板开没开，看这一步能不能命中就知道 ——
        # 这一步同时兜住"上面那一点落在空处"（战斗屏右上角这一带只有它）。
        if not self.click_when(设置, timeout=8.0):
            self.snap("quit_run_nogear")
            log("      点了右上角固定位置的「信息」图标，但面板里没找到齿轮「设置」"
)
            return False

        if not self.wait_for([暂停菜单], timeout=10.0):
            self.snap("quit_run_nopause")
            log("      点了齿轮，但「暂停」菜单没上来")
            return False

        # 「放弃此轮游戏」就在这一屏上（暂停.json 的头注释：内含放弃此轮游戏、
        # 游戏速度、自动出牌、画质帧率…）。guard 挂「暂停菜单」= 屏还在才点。
        if not self.click_when(放弃此轮游戏, timeout=8.0, guard=(暂停菜单,)):
            self.snap("quit_run_noabandon")
            log("      「暂停」菜单里没找到「放弃此轮游戏」")
            # **原路退出来**，别把这一局留在"暂停菜单开着"的状态上：认屏表里
            # 没有这一屏，主循环下一轮只会报「未知界面」再停一次，多一层假故障。
            # 只在这一条路上退 —— 后面那条（点了放弃却没等到结算屏）屏上是什么
            # 还不知道，闭眼点「关闭暂停」可能点到别的东西上。
            #
            # 退出要走**两级**：先「关闭暂停」退回**卡牌菜单面板**（实测，
            # 2026-10-02 dry：不是退回游戏），再点面板左上角把它也收掉才是地图。
            # 少收一级的代价不是"多一层假故障"那么轻：面板盖住的右半屏里，
            # 地图节点文字还认得出（`地图界面` 照样命中），主循环会当成地图屏
            # 去点那些坐标 —— 全打进面板里。
            if self.click_when(关闭暂停, timeout=5.0):
                log("      已点「关闭暂停」，再收掉卡牌菜单面板")
                self.click(*PANEL_BACK)
                time.sleep(0.8)
                # 判"面板收掉没"要看**面板里那枚齿轮还在不在**（`设置` 带 roi，
                # 只认面板里那一枚），**不能**再用 `卡牌菜单` 那枚图标 —— 2026-10-04
                # 实测：它在战斗屏上会整枚发亮、模板分掉到 0.43，面板明明已经收干净了
                # 它照样认不出，当场报出一个**假故障**（现场图 quit_dry_back.png 是
                # 干干净净的战斗屏，脚本却在喊"没收掉"）。
                if self.see(设置):
                    self.snap("quit_run_panel")
                    log("      点面板左上角没收掉（面板里那枚齿轮还在）—— 存图")
                else:
                    log("      面板已收掉，回到游戏里")
            return False

        # 点完之后：等结算屏（下面交给 finish_run 收尾）或直接回主界面。
        # 这一步是**第一次真跑**，所以等不到就存图 —— 现场图比猜有用。
        if not self.wait_for([仪式结算, 主界面], timeout=20.0):
            self.snap("quit_run_nosettle")
            log("      点了「放弃此轮游戏」，但既没等到结算屏也没等到主界面"
                " 存图，停下等人")
            return False
        log("      已在结算屏/主界面 —— 这一局算放弃了")
        return True

    # ---------- 战斗 ----------

    # 极星水母「同化」框：**从右到左依次试**点哪张牌（用户 2026-10-03 定的走法）。
    # 横扫的几何 `ASSIM_Y` / `ASSIM_X_RIGHT` / `ASSIM_X_LEFT` / `ASSIM_STEP` 已搬进
    # `shared/coords.py`（量法、两张存档帧的来历都在那边）。**保留同名类属性** ——
    # `debug/assim_cards.py` 直接引 `Game.ASSIM_*`。
    ASSIM_Y = ASSIM_Y
    ASSIM_X_RIGHT = ASSIM_X_RIGHT
    ASSIM_X_LEFT = ASSIM_X_LEFT
    ASSIM_STEP = ASSIM_STEP

    # 模态框点完到复验之间等多久。**这个数只有一份**：三个模态框
    # （夜巡人 / 护甲牌 / 最后的机会）原来各自写了一遍 1.2。
    # 1.2s 是"框退场动画 + 下一次截图"的余量，实测点完不到一秒框就走了；
    # 宁多勿少 —— 短了会把"已经关掉了"误判成"没关"，然后交回上层白点一次。
    MODAL_SETTLE = 1.2

    def _modal_click(self, box, button, what, *, miss, ok, stuck, image=None):
        """三个「你必须选择一项」式模态框的公共体：认框 → 点那一下 → 复验框关没关。

        返回 True/False = 框**点掉了没有**（`False` 有两种：框不在、或点了没关上，
        由调用方那几句日志分辨）。

        为什么值得并：三个方法（`nightwatch_option` / `armor_option` /
        `last_chance`）的**控制流逐行相同**，只有"认哪个框、点哪个键、日志怎么写"
        不同。真正怕的不是啰嗦，是**复验那一步被漏抄** —— roi 是照一张现场量的，
        框位一变就点空，而点空**不报错**（`click_node` 一路返回 True）。
        那一步写在公共体里，第四个模态框就不会忘了。

        `what` / `miss` / `ok` / `stuck` 四句日志原样打出来（**一个字不改**）——
        里面带着"别点哪一枚"这类现场知识，比如最后的机会那条
        「尤其不点左边的「放弃」」。策略与量测依据在各调用点的 docstring 里。

        **不并 `assimilate`**：它不从右到左试一排牌、判据是 `wait_gone` 连续两帧，
        形态不一样。
        """
        if image is None:
            image = self.capture()
        if not self.see(box, image):
            return False

        log(what)
        if not self.click_node(button):
            log(miss)
            return False
        time.sleep(self.MODAL_SETTLE)   # 等框退场，再复验
        if not self.see(box, self.capture()):
            log(ok)
            return True
        log(stuck)
        return False

    def assimilate(self, image=None):
        """清掉极星水母的「选择一张牌转化为同化。」框，返回是否清掉了。

        **这是小怪的专属机制，不是通用弹窗。** 极星水母每回合弹一次：提示一行字，
        下面卡牌区只留两张候选牌，中间一个「确定」。它盖住整个右侧，
        「自动出牌」那枚按钮**整个不见** —— 不处理，fight() 就一路空等到超时
        （实测卡死在 301s、第 2 回合，人看着就像脚本挂了）。

        两个坑：
          · 候选牌**不点，「确定」是灰的**，点下去毫无反应。必须先点牌。
          · 点完牌点「确定」之后，这一回合的牌是重发的（手牌会变），
            所以调用方不能拿弹框前那张截图继续往下判断。

        选牌规则：**从右到左依次试**（用户 2026-10-03 定的）。当天补的理由：

            「一部分卡牌无法"同化", 应该从右到左依次尝试」

        已经同化过的牌（牌面就是同化那张「敌方选择队列中一张牌变化为同化」）再点
        也不给确定 —— 所以不能认准一张了事，得一张一张往左试，试到某一张把框关掉。
        实测把 虚空奇点（6 费）转化成了 **0 费 36 伤**：同化未必是坏事，
        但"哪张转化最划算"没有定论，顺序就按用户定的右→左。
        落点怎么来的、为什么可以扫，全在 `ASSIM_X_RIGHT` 那一段注释里。

        **每一下都是"点牌 → 按确定 → 看框关没关"**，判据始终是**提示行还在不在**
        （`wait_gone`，连续两帧看不到才算走）—— 不比牌面、不比手牌数：
        那些本来就是每回合在变的东西。一整排试完框还在就返回 False，
        交给 fight() 自己那层超时去停车，不在这儿死循环。
        """
        if image is None:
            image = self.capture()
        if not self.see(同化提示, image):
            return False

        xs = list(range(self.ASSIM_X_RIGHT, self.ASSIM_X_LEFT - 1, -self.ASSIM_STEP))
        log(f"    极星水母「选择一张牌转化为同化」→ 从右到左试，共 {len(xs)} 个落点")
        for n, x in enumerate(xs, 1):
            self.click(x, self.ASSIM_Y)
            time.sleep(0.4)          # 等"选中"生效（选中的牌会在左边弹出详情面板）
            if not self.click_node(同化确定):
                log(f"      {n}/{len(xs)} ({x},{self.ASSIM_Y})：「确定」没认出来，往左挪")
                continue
            if self.wait_gone(同化提示, timeout=1.6, stable=2, interval=0.3):
                log(f"      {n}/{len(xs)} ({x},{self.ASSIM_Y})：选到了，框已关掉")
                return True
            log(f"      {n}/{len(xs)} ({x},{self.ASSIM_Y})：点了但框没关，往左挪")
        return False

    def nightwatch_option(self, image=None):
        """夜巡人的「你必须选择一项」框 —— 弹出就点**第一项**，返回是否点掉了。

        **用户 2026-10-02 定的策略**（原话）：
        「记录该敌人(夜巡人)特殊策略, 如果弹出选项, 直接选第一项」。

        现场是精英战，对手「夜巡人 等级: 11 精英」，面板写着二阶段效果
        「进入二阶段时，迷惑。对方卡组随机卡牌 3 次」。弹出的两行是
        「失去15点生命。」（第一项）和「选择队列中2张卡牌移除。」（第二项）。

        和极星水母那个「同化」框同类：**模态**。弹出时「自动出牌」整个不见，
        fight() 里那三个结局判据一个都配不上 —— 不处理就一路空等到超时
        （实测 2026-10-02 卡死在 313s、第 2 回合，日志停在「第 2 回合 → 自动出牌」）。

        点的是**第一项那行的「确认」**，不是第一项的文字：两行的「确认」长得
        一模一样，靠 `夜巡人选项确认` 节点的 roi 只留上面那一行（量法与余量
        见 战斗.json 那个节点的注释）。

        **判据是这一框的标题，不是敌人名**：脚本从头到尾没在认「夜巡人」是谁，
        只认「你必须选择一项」这行字。所以别的敌人弹出同样的一框，这里照样点
        第一项 —— 用户给的规矩就是"弹出选项就选第一项"，没有加敌人这个条件。
        哪天发现别的敌人弹同样的框、而第一项不是想要的，这条就得改成按敌人名分
        （那要先有认敌人名的节点，目前没有）。
        """
        return self._modal_click(
            夜巡人选项, 夜巡人选项确认,
            "    夜巡人「你必须选择一项」→ 按定的策略点第一项",
            miss="      第一项的「确认」没认出来 —— 不猜别的位置，交回上层",
            ok="      已选第一项，框关掉了",
            stuck="      点了但框没关（框位也许挪了）—— 交回上层，不接着点",
            image=image,
        )

    def armor_option(self, image=None):
        """「你必须选择一项」的**卡牌类型三选一**框 —— 按定的策略点第 2 行「护甲牌」，返回是否点掉了。

        **用户 2026-10-02 定的**：「对于贪婪之怒, 如果出现选项, 选择第二个"护甲牌"选项」。
        （用户说的是"贪婪之怒"，答的是"第 2 行"；这一框长什么样、现场量到哪几枚
          「确认」、为什么不能复用夜巡人那对节点，都写在 战斗.json 的 `护甲牌选项` 头注释里。）

        和「同化」「夜巡人选项」「最后的机会」同类：**模态**。它盖着的时候
        「自动出牌」照画不误（实测点下去游戏毫无反应、`click_node` 还一路返回 True），
        三个结局判据也一个都配不上 —— 不处理就是空点到 300s 上限
        （2026-10-02 23:02 实测：日志停在「第 2 回合 → 自动出牌」再没动过）。

        ⚠️ **别和夜巡人那个框串了**：抬头字一样，但那一框是**两行**（失去生命 /
        移除卡牌）、策略是"选第一项"；这一框是**三行**、策略是"选第 2 行"。
        两处用的是各自的一对节点，roi 只框自己那一行。

        点完复验框有没有关掉 —— roi 是照一张现场量的，框位一变就会点空，
        而点空**不报错**（同夜巡人那条的理由）。
        """
        return self._modal_click(
            护甲牌选项, 护甲牌选项确认,
            "    卡牌类型三选一（你必须选择一项）→ 按定的策略点第 2 行「护甲牌」的「确认」",
            miss="      「护甲牌」那行的「确认」没认出来 —— 不猜别的位置"
                 "（尤其不点上下两行的确认），交回上层",
            ok="      已选「护甲牌」，框关掉了",
            stuck="      点了但框没关（框位也许挪了）—— 交回上层，不接着点",
            image=image,
        )

    def last_chance(self, image=None):
        """生命值归零后的「最后的机会」框 —— 按定的策略点「挣扎」，返回是否点掉了。

        **用户 2026-10-02 定的**：问「①放弃 ②挣扎 点哪个」，答就一个字——「挣扎」。

        现场是生命值 0/133 时弹的，中央三行叙述，末行「你仍有机会，最后的机会。」，
        下面并排两个按钮：**左「放弃」(492,603)、右「挣扎」(786,603)**。
        注意「挣扎」在**右边**——夜巡人那个框是"选第一项"（在左），两个别串。

        和「同化」「夜巡人选项」同类：**模态**。它盖着时「自动出牌」不见，
        fight() 里三个结局判据也一个都配不上，不处理就是空等到超时
        （实测 2026-10-02 第 178 回合撞 300s 上限停车）。

        「挣扎」之后会发生什么**还没见过**：这一版只负责把框点掉，然后交回
        fight() 的循环看下一屏是什么。
        """
        return self._modal_click(
            最后机会, 挣扎,
            "    生命值归零「最后的机会」→ 按定的策略点「挣扎」",
            miss="      「挣扎」没认出来 —— 不猜别的位置（尤其不点左边的「放弃」）",
            ok="      已点「挣扎」，框关掉了",
            stuck="      点了但框没关 —— 交回上层，不接着点",
            image=image,
        )

    # 手牌那一排里 **费用徽章中心 → 牌面中心** 的偏移 `DISCARD_CARD_DX` /
    # `DISCARD_CARD_DY` 已搬进 `shared/coords.py`（量法与"为什么用相对偏移"在那边）。
    DISCARD_CARD_DX = DISCARD_CARD_DX
    DISCARD_CARD_DY = DISCARD_CARD_DY

    def discard_card_box(self, image=None):
        """定位手牌里**最右那张牌**的费用徽章框，返回 (x, y, w, h)；定位不到返回 None。

        不认牌面、不认数字 —— 认的是每张牌左上角那枚费用徽章（蓝菱形底 + 白数字）。
        为什么不能刻模板：徽章里的数字每张牌都不一样（实测同一手 0/2/4 三种），
        刻一个数字去配别的，分数掉到 0.60；而且**有的牌压根不画徽章**
        （这一手第 2 张盾牌牌就没有，见 debug/screenshots/_zoom_dim.png），
        所以"数徽章 = 数牌"也不成立。这里只要最右那一枚，够用。

        节点 `弃牌选牌` 是 ColorMatch（徽章那条蓝，roi 定死在徽章横带 y500~548）。
        引擎自己的排序（order_by/index）不拿来当依据：实测 all_results 里除了
        6 枚真徽章，还夹着一堆 1x1 的噪点，谁排最右得由这里说了算 —— 按尺寸
        （宽≥20 且高≥15，真徽章实测 41x40、被白数字切成两半时最小 31x40）筛掉噪点，
        再取**右边缘最靠右**的那一枚。
        """
        reco = self.probe(弃牌选牌, image)
        if not reco:
            return None
        boxes = {(r.box[0], r.box[1], r.box[2], r.box[3]) for r in (reco.all_results or [])}
        if reco.best_result is not None:
            boxes.add(tuple(reco.best_result.box))
        boxes = [b for b in boxes if b[2] >= 20 and b[3] >= 15]
        if not boxes:
            return None
        return max(boxes, key=lambda b: b[0] + b[2])

    def discard_card(self, image=None):
        """黑市行医的「丢弃队列中1张牌换取6点虚质生命。」框 —— 选**最右那张牌**丢掉，
        返回是否清掉了。

        **用户 2026-10-03 定的策略**（原话）：
        「对于这个敌人, 需要特殊处理, 当选择时, 需要选择最后一张(最右)卡牌丢弃」。

        现场（庸医事件选「坚定拒绝」触发的那一场，对手「黑市行医 等级: 6」37/199）：
        屏幕中央一行提示语，下面一枚「确定」，再下面整排手牌。存图
        debug/screenshots/fight_timeout.png。

        和「同化」「夜巡人选项」「护甲牌选项」「最后的机会」同类：**模态**。
        弹出时右侧上下两枚「结束回合」整个不见，fight() 里三个结局判据也一个都
        配不上 —— 不处理就是一路空点「自动出牌」到 300s 上限
        （2026-10-03 实测：空点到第 147 回合才撞超时，人看着就像脚本挂了）。

        先点牌再点「确定」：同 `assimilate()` 那套（牌没选，「确定」是灰的，
        点下去什么都不会发生）。

        **点不动就停下，不换别的牌**：用户给的规矩是"最后一张"，右边那张要是
        选不了（比如它没画徽章、是张打不出去的牌），那是新的情况，该停下问 ——
        这里不去替他改成"从右往左一张张试"（`assimilate` 那边有兜底，是因为
        那条规矩当初就是这么定的："默认最右，试不中轮过去试别的"）。

        ⚠️ **判据是这行提示语，不是敌人名**：用户原话开头是「对于这个敌人」，
        但脚本从头到尾没在认「黑市行医」是谁（也没有认敌人名的节点），只认
        「丢弃队列中1张牌换取6点虚质生命」这行字。所以**别的敌人弹出同样一行、
        而"丢最右"不是想要的**，这里会照丢不误（`nightwatch_option` 那条同理 ——
        当天用户给的规矩就是"弹出选项就选第一项"，没加敌人这个条件）。
        真到了那一步，得先有认敌人名的节点，这条才能按敌人名分开。
        """
        if image is None:
            image = self.capture()
        if not self.see(弃牌提示, image):
            return False

        log("    黑市行医「丢弃队列中1张牌换取6点虚质生命」→ 丢最右那张")
        box = self.discard_card_box(image)
        if box is None:
            log("      手牌上没定位到费用徽章")
            return False
        x = box[0] + box[2] // 2 + self.DISCARD_CARD_DX
        y = box[1] + self.DISCARD_CARD_DY
        log(f"    最右那张牌：徽章框 {box} → 点牌面 ({x},{y})")
        self.click(x, y)
        time.sleep(0.6)
        if not self.click_node(弃牌确定):
            log("      「确定」没认出来别的位置")
            return False
        time.sleep(1.2)
        if not self.see(弃牌提示, self.capture()):
            log("      已丢最右那张，框关掉了")
            return True
        log("      点了最右那张但框没关")
        return False

    # 敌方选卡面板里**第一张牌**（左上角那一格）的中心 `ENEMY_PICK` 已搬进
    # `shared/coords.py`（实测自 fight_timeout.png；与事件那条 `选卡屏` 的格位表
    # 同一套 —— 两屏共用同一副卡组 UI，差的只是左半边背后是谁）。
    ENEMY_PICK = ENEMY_PICK

    def enemy_card_pick(self, image=None):
        """战斗中弹出的「选择卡牌 / 选择敌方卡组中的1张牌移除」面板 —— 点第一张再点
        「确定」，返回是否清掉了。

        **用户 2026-10-07 定的策略**（原话）：
            「点击位置是固定的, 只需要识别出什么时候需要进行敌方卡牌移除而已」
        问走法答三个字：「默认选第一张」。

        现场：战斗打到一半，**面板盖在战斗屏右半边**（左边那半屏还是战斗画面），
        标题「选择卡牌」、副标题「选择敌方卡组中的1张牌移除」、底下一枚「确定」。
        存图 debug/screenshots/fight_timeout.png（2026-10-07 19:26 那次停车，
        同一次还写了 quit_run_nogear.png / battle_end.png，三张是同一屏）。

        和「同化」「夜巡人选项」那五个同类：**模态**。它盖着时「自动出牌」整枚不见，
        fight() 里三个结局判据也一个都配不上 —— 不处理就是一路空等到 300s 上限；
        更糟的是撞了上限之后，退出链第一步那记固定坐标 `INFO_BTN (1203,48)`
        **同样落在面板里**，于是连"退出这一局"都退不出去（2026-10-07 就是这么停下的）。

        **判据是副标题那行字**（`敌方选卡提示`），不是标题「选择卡牌」——
        标题是 `事件.json` 那条选卡屏的判据，两处各认一份就成了同一个东西两处维护。

        「确定」复用 `事件.json` 的 `选卡确定` 节点（两屏共用同一套卡牌 UI，
        实测两处都在 (908,653) 一带），不为这一屏另开一个。

        ⚠️ **两处没量过**（照现状写死，撞上再补现场）：① 第一张那格是照事件那条
        选卡屏的格位表取的，**没在这一屏上单独核过**；② 点掉之后这一屏自己走不走
        没量过。所以判据始终是**副标题还在不在** —— 点了没走就交回上层，不补第二下。
        """
        if image is None:
            image = self.capture()
        if not self.see(敌方选卡提示, image):
            return False

        log("    敌人机制「选择敌方卡组中的1张牌移除」→ 选第一张")
        self.click(*self.ENEMY_PICK)
        time.sleep(0.6)
        if not self.click_node(选卡确定):
            log("      「确定」没认出来别的位置")
            return False
        time.sleep(self.MODAL_SETTLE)
        if not self.see(敌方选卡提示, self.capture()):
            log("      已选第一张，面板关掉了")
            return True
        log("      点了第一张但面板没关")
        return False

    def fight(self, timeout=300.0):
        """自动打完当前这场战斗，返回 "胜利" / "逃离" / "结算" / "离开" / "死亡" /
        "回地图" / None（超时）。

        "离开" = 打完了、停在结果屏上、标题被残余信息框盖住读不出胜负（见下）。
        调用方**不用区分这几种非 None 的值**（combat/fight.py 只判 None），
        它存在的意义是让日志能说清"这一场是怎么结束的"。

        右侧上下两个按钮文字都是「结束回合」，上面那个（小）才是自动出牌，
        靠 pipeline 里的 roi 区分，这里点的是「自动出牌」节点。
        注意它**只自动出当前这一回合**（出完牌顺带自动结束回合），
        所以要一回合点一次，不能点一下等到底。

        第四种出口是**结果屏的标题读不出来**：打完停在奖励/结果屏上，可标题被
        一块**残余信息框**（卡牌信息、金币信息之类）盖住 —— 上面三个锚点全不中，
        从前就在这儿空转到超时。这时候屏上有「离开地点」，**有就等于打完了**，
        直接返回 "离开"，由主循环的「通用离开屏」点掉它。用户 2026-10-02：
        「这是卡牌信息(或者如金币等信息)的残余, 点击其他空白地方恢复。
          遇到这种情况,有"离开地点",直接点击就可以了」。

        四种结局：
            「战斗胜利」   打死了 → "胜利"
            「逃离战斗」   打到一半转成逃跑结算（实测精英战第 7 回合转的）
                           → "逃离"。**这个不认出来就会空等到超时**：
                           它和胜利一样有奖励界面，但锚点完全不同。
            「仪式结算」   本局到头了 → "结算"。**这一屏不分胜负**——
                           节点 `仪式结算` 的 expected 是左上角那四个字
                           「统计数据」，而 结算.json 的头部注释写着这屏是
                           「仪式失败 / **仪式成功**」共用的总览屏。
                           2026-10-01 打通首领（护封骑士-帕特拉姆，噩梦9层
                           第36层）走的正是这一支，当时这里印的是「战斗失败」、
                           返回 "失败"，**报反了**。本函数现在**没有**区分
                           胜负的判据，要分得另找（别拿这一屏硬猜）。

                           另：那场 42 回合里，0.3s 一轮的轮询**一次都没见到
                           「战斗胜利」横幅**，也没经过奖励界面，打完直接是
                           这一屏 —— 所以「打穿首领」可能压根不走
                           "胜利横幅 → 奖励" 那条路（普通战斗是走的），
                           别把 战斗胜利 当成收尾的必经判据。

        还有一类**按钮在、可就是点不动**的：上面那枚「结束回合」（自动出牌）
        被游戏画成**灰匾**（下面那枚还是亮的金匾）。2026-10-03 实测那一场
        （首领·元素法师，游戏停在「第3回合」，敌人血 45/198、玩家 9/93+94）：
        脚本连点 88 次、右侧按钮区两帧相隔半小时 diff = 0.0（一个像素都没动），
        而 `click_node` 一路返回 True —— 光看返回值永远发现不了点空。
        用户当天定的规矩：「添加逻辑, 如果自动战斗的"结束回合"无法点击,
        就点击下方的"结束回合"」。判据与门槛见 `AUTO_STUCK_CLICKS` 上面那一段
        （尺子是游戏自己那行「第N回合」，不是按钮的颜色 —— 颜色只是同一件事的
        旁证，钉在 debug/round_probe.py 里）。**只在点不动时才用**：
        正常情况下下面那枚是"手动结束回合"，点它就是白扔一回合。

        还有一类**不是结局、但会让这一轮走不下去**的东西：战斗里弹的模态框。
        见过六个，每一轮开头都过一遍（**排在点「自动出牌」前面**，原因见循环里
        那段注释——其中「最后的机会」框是按不住按钮的，差点让脚本空点到超时）：
          · 极星水母的「同化」框        → assimilate()
          · 夜巡人的「你必须选择一项」  → nightwatch_option()   ← 两行，选第一项
          · 贪婪之怒的卡牌类型三选一框  → armor_option()        ← 三行，选第 2 行「护甲牌」
          · 生命值归零的「最后的机会」  → last_chance()
          · 黑市行医的弃牌框            → discard_card()        ← 丢最右那张牌
          · 敌方「选择敌方卡组中的1张牌移除」→ enemy_card_pick() ← 选第一张

        再有一类**什么都没认出来、但也不该干等**的：一块**残余信息框**
        （卡牌信息 / 金币信息之类）挂在屏上不走。用户 2026-10-02 说了两遍：
        「这是卡牌信息(或者如金币等信息)的残余, 点击其他空白地方恢复」
        「用来恢复信息的点击位置与自动战斗位置相同即可」「不点掉就会一直挂着」。
        所以闲着够久（`IDLE_CLEAR_AFTER` 秒）就照这一场点「自动出牌」的那个坐标
        空点一下 —— 见 else 分支末尾那段。

        第五个出口是**打完直接回到地图**（2026-10-03 加的，用户当天确认
        「打完回地图」）：事件里选「触发战斗」那一项打的那一场，打完**没有**
        胜利横幅、也**没有**带「离开地点」的结果屏，屏幕就回到地图了。
        详见循环里那条 `地图界面` 的注释。

        第四个出口是**死透之后的黑屏**：点掉「挣扎」之后玩家又死了一次，屏幕整个
        变黑、停住不动，要**点一下屏幕**才往下走（用户 2026-10-02 定的）。
        它由 `died` 那道闸管着，只在本场点过「挣扎」之后才认 —— 判据为什么这么窄
        见循环里那段注释。认出来就返回 "死亡"，**点击不在这里做**，
        交给主循环的「死亡屏」（combat/death.py）。

        超时返回 None，并存一张图——空等 300s 什么都看不到，等于白等。
        """
        deadline = time.monotonic() + timeout
        rounds = 0
        died = False      # 点过「挣扎」= 玩家已经死了，接下来那一下黑屏要接住
        auto_pos = None        # 这一场真正点到「自动出牌」的坐标（点残余框时照抄它）
        idle_since = None      # 从什么时刻起"什么都没认出来"；认出东西就清空
        last_clear = 0.0       # 上次为残余框空点的时刻（防连点）
        # 「自动出牌」点空了的账（判据见 AUTO_STUCK_CLICKS 上面那段）：
        #   auto_round   上一次读到的回合数（**归一后的数字**，不是原文 —— 见 _round_label）
        #   auto_stuck   连着几次读到同一个回合数
        #   stuck_at     这一串的起点时刻（算够不够 20s）
        auto_round = None
        auto_stuck = 0
        stuck_at = None
        while True:
            image = self.capture()

            # **模态必须排在「自动出牌」前面**（2026-10-02 改的判序，此前排在
            # else 分支里，是错的）。
            #
            # 原来的理由写在下面那句"这两个框都盖着按钮"——对「同化」是对的，
            # 但**对「最后的机会」框不成立**：那一屏上按钮照画，
            # `自动出牌` 节点照样命中右上那枚小的「结束回合」
            # （2026-10-02 23:16 实测落点 (1219,271)；更早记过 (1182,259)，
            #   那是"整个按钮"还是"文字框"的差别 —— 以脚本自己报的落点为准），
            # 点下去游戏毫无反应，而 click_node 一路返回 True。
            # 结果就是模态那几行永远轮不到：实测空点 43 次、回合数虚涨，
            # 然后撞 300s 上限停车（日志停在「第 43 回合 → 自动出牌」，人在旁边
            # 看见的是"脚本在点一个点不动的按钮"）。
            #
            # 这几个 see() 都是小 roi 的 OCR（弃牌那个还多一次 ColorMatch），
            # 代价远小于一次空转的回合。
            #
            # ⚠️ **夜巡人排在贪婪之怒前面**：两个框的抬头都是「你必须选择一项」，
            # 而两处「确认」的 x 几乎重合（784 / 785），只靠 y 分。
            # 夜巡人那框先判，判中就轮不到这边（策略也不同：那边选第一项）。
            if self.assimilate(image):
                idle_since = None
                continue
            if self.nightwatch_option(image):
                idle_since = None
                continue
            if self.armor_option(image):
                idle_since = None
                continue
            if self.last_chance(image):
                died = True
                idle_since = None
                continue
            if self.discard_card(image):
                idle_since = None
                continue
            if self.enemy_card_pick(image):
                idle_since = None
                continue

            # 死了之后的黑屏。**这里只认出来、交出去**，点击由主循环那一步干
            # （认屏表里的「死亡屏」→ combat/death.py）：那一屏不带"刚才死没死"
            # 这个语境，play() 从别处走进来照样能处理，点击逻辑只有一份。
            #
            # `died` 这道闸是判据的一部分：黑屏本身不稀罕 —— 过场淡入淡出也会
            # 整屏全黑（存档帧 gone_1.png / gaze_left.png 就是），那是在战斗中
            # 正常会碰上的。只有"点过「挣扎」"之后的黑屏才是这一屏。
            # ⚠️ 哪天出现"没走最后的机会就死了"的路子，这道闸会漏，得放宽。
            if died and self.see(死亡黑屏, image):
                log("  死透了 —— 屏幕黑了")
                return "死亡"

            # 模态都不在，再谈回合：按钮在就说明轮到我方了。
            # 不用 click_node 而自己拿框，是为了**记住这一下点到哪**
            # （`auto_pos`）—— 点掉残余信息框时要照抄同一个位置
            # （用户 2026-10-02：「用来恢复信息的点击位置与自动战斗位置相同即可」）。
            # 落点算法与 click_node 完全一样（click_box 的算式 + target_offset）。
            box = self.box_of(自动出牌, image)
            if box is not None:
                idle_since = None
                auto_pos = self.click_point_of(自动出牌, box)

                # 这一下到底点不点得动？拿游戏自己那行「第N回合」当尺子 ——
                # 连着几次读到同一个回合数、且拖够了秒数，就是"上面那枚点不动"。
                # 判据为什么这么定、数为什么取 4 次 / 20 秒，见 AUTO_STUCK_CLICKS
                # 上面那一段；比的是**归一后的数字**（`_round_label`），
                # 不是 OCR 原文 —— 原文会在 `8` / `第8回合` 之间抖，抖一次清零一次。
                raw = self.text_of(回合数, image)
                label = _round_label(raw)
                if label is None or label != auto_round:
                    auto_stuck, stuck_at = 0, None
                else:
                    if auto_stuck == 0:
                        stuck_at = time.monotonic()
                    auto_stuck += 1
                auto_round = label

                if (auto_stuck >= AUTO_STUCK_CLICKS
                        and time.monotonic() - stuck_at >= AUTO_STUCK_SECONDS):
                    # 用户 2026-10-03：「添加逻辑, 如果自动战斗的"结束回合"
                    # 无法点击, 就点击下方的"结束回合"」
                    log(f"    上面那枚「自动出牌」点了 {auto_stuck} 次、"
                          f"{time.monotonic() - stuck_at:.0f}s 里回合数一动没动"
                          f"（还停在「{raw}」）"
                        "改点下面那枚「结束回合」")
                    if self.click_node(结束回合, image):
                        rounds += 1
                        log(f"    第 {rounds} 次 → 结束回合（下方那枚）")
                    else:
                        log("    下面那枚「结束回合」这一帧也没认出来位置，"
                            "不点，下一轮再看")
                    # 重新起算：别一轮接一轮地砸同一枚按钮
                    auto_stuck, stuck_at = 0, None
                    time.sleep(1.5)
                else:
                    self.click(*auto_pos)
                    rounds += 1
                    log(f"    第 {rounds} 回合 → 自动出牌 点 {auto_pos}")
                    # 等出牌动画走一段，免得按钮还没消失就被重复点到
                    time.sleep(1.5)
            else:
                # 按钮不在：敌人回合、演出动画，或者已经打完了。
                if self.see(战斗胜利, image):
                    log(f"  战斗胜利，共 {rounds} 回合")
                    return "胜利"
                if self.see(逃离战斗, image):
                    log(f"  逃离战斗，共 {rounds} 回合")
                    return "逃离"
                if self.see(仪式结算, image):
                    log(f"  本局结束，已进结算总览屏（共 {rounds} 回合；胜负此屏分不出）")
                    return FINISHED
                # 打完停在结果屏上、**标题却被"残余信息框"盖住** —— 上面那三个
                # 锚点全不中，从前就在这儿一圈圈空转到 300s 超时（2026-10-02
                # 22:57 那次实测：OCR 把标题读成「超能之ガ斗胜」/「之力斗胜」，
                # 而 `战斗胜利` 的 roi [540,125,200,55] 正好被那块卡牌信息框盖满）。
                # 用户 2026-10-02 定的规矩：
                #   「这是卡牌信息(或者如金币等信息)的残余, 点击其他空白地方恢复。
                #     遇到这种情况, 有"离开地点", 直接点击就可以了」
                # 这里**只认出来、不点它**：真正那一下由主循环的「通用离开屏」干
                # （「通用离开屏」的判据就是 `离开地点`），点击逻辑只有一份。
                # 战斗中不会出现「离开地点」（战斗屏上是「结束回合」），所以这条
                # 不会把"还在打"误判成"打完了"。
                if self.see(离开地点, image):
                    log(f"  战斗结束（结果屏标题被残余信息框盖住，共 {rounds} 回合）")
                    return "离开"

                # **死透之后的「化形信使」屏**（顶部抬头「化形信使」、中间
                # 「你要，留下，些什么」、底下并排「不留下遗物」/「留下遗物」）。
                # 它既不是战斗屏、也不黑、更不是上面那几条锚点中的任何一个，
                # 从前就卡在这儿一圈圈空转到 300s：2026-10-03 00:45 实测，
                # 第 7 回合之后连着点了几十下「自动出牌」的位置全无反应，
                # 停在的就是这一屏（现场图 debug/screenshots/fight_timeout.png
                # ——**就是它**，不是我方回合没画完的帧；debug/run_1003a.log:632 起）。
                #
                # 按既有的分工：**这里只认出来、交出去**，点哪儿由主循环那一步干
                # （认屏表「化形信使屏」→ combat/death.py:handle_relic，
                # 用户 2026-10-02 定的"不留下遗物"）。点击逻辑只有一份。
                #
                # ⚠️ 这一条**故意不挂 `died` 那道闸**（上面黑屏那条挂着它，
                # 因为过场淡入淡出也会整屏全黑）：化形信使是这一屏独有的抬头，
                # 战斗中配不上；而"没走最后的机会就死了"的路子上面已经警告过会漏
                # （见黑屏那条的注释），这里不再给自己加一道同样会漏的闸。
                if self.see(化形信使, image):
                    log(f"  死透了 ——「化形信使」屏（共 {rounds} 回合）")
                    return "死亡"

                # **打完直接回到地图**（2026-10-03 实测加）。
                #
                # 来由：事件「电音歌手」里选第 2 格「真是不堪入耳的声音」→ 第二页
                # 点「触发战斗」打的那一场，打完之后**既没有「战斗胜利」横幅、
                # 也没有带「离开地点」的结果屏**，屏幕直接回到了地图
                # （用户 2026-10-03 答「打完了」；现场图 debug/screenshots/
                #   _now_afterfight.png：人还站在「事件」那个点上、青色箭头指向
                #   上下两个「战斗」节点，金币/魂晶/生命/神智与进事件之前
                #   一模一样 —— 只有人的位置从「起点」挪到了「事件」）。
                #
                # 上面那五个出口在这屏上一个都不中，从前就在这儿空转到 300s；
                # 而且兜底那条"点掉残余信息框"会**照着「自动出牌」的位置
                # (1219,270) 在地图上连点** —— 那个点附近正好压着「迷雾区」
                # 的节点标签，那是在点地图，不是在点按钮（2026-10-03 实测
                # 两分钟里点了十几次）。这条认出来就在它前面把循环收掉。
                #
                # 战斗屏上不会出现地图（战斗中地图整个不显示），所以这条不会
                # 把"还在打"误判成"打完了"。胜负在这一屏上照样分不出（不猜）。
                if self.see(地图界面, image):
                    log(f"  回到地图了 —— 这一场结束了（共 {rounds} 回合）")
                    return "回地图"

                # 还是什么都没认出来：敌人回合、演出动画，或者**一块残余信息框
                # 挂着不走**。用户 2026-10-02 说了两遍，第二遍是看着「超能之力」
                # 那块框说的：「如果屏幕出现残留信息(如本次"超能之力"), 记得点掉」
                # 「不点掉就会一直挂着」。
                # 干等不是办法 —— 闲着够久就照**这一场点「自动出牌」的那个坐标**
                # 空点一下（那一格是空白时点它没有副作用；是按钮时本来也该点它）。
                # 首选现认出来的框（`auto_pos`），没点过这一场才退到节点声明的 roi 中心。
                # 计时用**秒**不用轮数：这一圈要跑 9 个左右的识别，一轮多久说不准。
                now = time.monotonic()
                if idle_since is None:
                    idle_since = now
                else:
                    idle = now - idle_since
                    if idle >= IDLE_CLEAR_AFTER and now - last_clear >= IDLE_CLEAR_GAP:
                        last_clear = now
                        idle_since = now     # 重新起算，别连着点
                        pos = auto_pos or self.node_roi_center(自动出牌)
                        if pos is None:
                            log(f"    连着 {idle:.0f}s 什么都没认出来，想点掉残余信息框，"
                                "可这场的「自动出牌」没点到过、节点也没声明 roi位置")
                        else:
                            log(f"    连着 {idle:.0f}s 什么都没认出来 —— 照「自动出牌」的位置"
                                  f"{pos} 空点一下")
                            self.click(*pos)
                            time.sleep(0.5)
                time.sleep(0.3)

            if time.monotonic() >= deadline:
                log(f"  战斗超时，已打 {rounds} 回合 —— 存图看当时停在哪一屏")
                Image.fromarray(self.capture()[:, :, ::-1]).save(
                    ROOT / "debug" / "screenshots" / "fight_timeout.png"
                )
                return None
