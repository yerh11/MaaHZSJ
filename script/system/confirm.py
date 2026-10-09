"""「…是否离开？」确认框 —— 全屏**模态**，盖在谁上面都可能。

战斗胜利 / 始源之凝视 / 各个地点界面都见过它。它挡着的时候，底下那屏就算
认得出来也点不动，所以它在 `script/recognizer.py` 的认屏表里排**第一位**。

动作本身在 `Game.leave_confirm()`（先勾「本局游戏不再提示」，再点「直接离开」），
各地点脚本也都调它 —— 同一套动作只写一份，改规则只改那一处。
"""

# 本模块**不 import strings** —— 它一个游戏里的字都不直接需要（动手的是
# `Game.leave_confirm()` 自己）。理由走 shared.reasons 那本字典。
from shared.reasons import WAIT_LEAVE_CONFIRM
from shared.kit import park


def handle(g, hit):
    # 只清弹窗、这一轮不再做别的：清完之后底下是什么屏，下一轮重新看
    if g.leave_confirm():
        return ""
    return park(g, WAIT_LEAVE_CONFIRM, "confirm_stuck",
        "确认弹窗在，但「直接离开」点不到 —— 停下等人（已存 confirm_stuck.png）")
