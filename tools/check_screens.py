#!/usr/bin/env python3
"""认屏表与屏模块的机器检查 —— 把"只靠注释口口相传"的规矩变成断言。

**屏住在哪四个包**：`nav/`（地图屏、路口屏）、`nodes/`（23 行）、
`combat/`（战斗屏、死亡屏、化形信使屏）、`system/`（确认弹窗屏、通用离开屏、结算屏）。
判据不写死目录名，而是**从认屏表反推**（`{s.handler.__module__}`）——
所以「把某屏 handler 放错包」当场会被下面第 1b 条拦下。

盯七件事（都是硬断言，错了退出码 1）：

  1. **屏模块之间不许互相 import，也不许 import recognizer / battle** ——
     屏是一堆叶子：认出哪一屏归认屏表说，动手只动自己那一屏。
     谁 import 谁都会在将来某天变成环，环在 import 期就炸。
  1b. **扫描面自检**：扫到的屏模块（定义了 handle 的那些）与认屏表里的 handler 模块
     **必须一一对上**；`core/` 与 `shared/` 里**不许有 handle**。
     专治"门禁换了目录却漏扫了某个包，还照样报全过"——`glob` 不递归就栽在这。
  2. **认屏表的顺序不变量**：确认弹窗屏第一；modal 全在非 modal 之前；
     地点专属全在「通用离开屏」之前；选卡屏 < 事件屏 < 事件结果屏；
     事件屏 < 真龙现身·第二页屏；游艺·结果屏 < 游艺·转盘屏；
     销毁卡牌屏 < 商店屏、选卡屏 < 篝火屏（面板排在它盖住的那屏前面）；
     地图屏 < 单选项屏，且单选项屏为最后一行。
     失败时把涉及那几行的 note 原文打出来 —— 那些注释就是"为什么排在这"。
  3. **handle 不许 `return None`、不许裸 `return`** —— 新契约是
     `handle(g, hit) -> str`："" = 处理完，非空 = 停下等人的理由。
     从结构上消灭"认出来了却返回 None"（旧的 None 语义是"不是这屏"，
     现在那句话只归认屏表说）。
  3b. **停车理由不许再写回字面量** —— 一律走 `shared/reasons.py` 的常量。
     判据是"这个字符串**正好等于** reasons.py 里某个常量值"，所以
     `print("    停下等人…")` 那种长句不会被误伤。从前 26 个理由散在
     16 个文件里、共 55 处，同一个理由抄四遍，改一处漏三处。
  4. **屏名唯一、带「屏」后缀、且不等于 strings.py 的任何常量值** ——
     重名 = 两行抢答；撞车 = tools/check_strings.py 会把屏名判成裸字符串
     （「篝火」「事件」「商店」「战斗」都是 strings.py 里的地图词条）。
  5. **每个 Screen 都有 handler、有 note、有判据**（nodes 或 check 至少一样）。
  6. **兜底屏（`recheck`）的名单是对的** —— 只有「通用离开屏」「事件结果屏」
     「单选项屏」这三行标它（判据是"靠一枚地点屏家族通用的控件认出来的"），
     多标一行 = 每次命中白花一次整表扫掠（约 3 秒），少标一行 = 过渡帧
     又会被它抢走。见 recognizer._confirm 那段。

另外出两份**报告**（只打印，不判负 —— 等收尾阶段再收紧成断言）：
    · 屏模块里没带 guard 的 click_when 调用点
    · 屏模块里残留的 time.sleep

用法：`python tools/check_screens.py`（无参数，退出码 0 = 全过）
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
SCRIPT_DIR = ROOT / "script"

# 屏模块住在哪四个包里 —— 认屏表里的 handler 指到哪儿，哪儿就是屏。
# 从前这里是 `SCRIPT_DIR / "screens"` + `glob("*.py")`；搬成四个包之后
# `glob` **不递归**，会一个屏都扫不到、门禁还照样"全过" —— 那条静默漏检
# 由下面 1b 的「扫到的 ⊇ 表里的」自检钉住。
SCREEN_DIRS = [SCRIPT_DIR / d for d in ("nav", "nodes", "combat", "system")]
NON_SCREEN_DIRS = [SCRIPT_DIR / d for d in ("core", "shared")]

sys.path.insert(0, str(SCRIPT_DIR))
import recognizer  # noqa: E402
import shared.reasons as reasons  # noqa: E402
import strings  # noqa: E402

table = recognizer.SCREENS

# "停车理由"的全部取值 —— 第 3b 条拿它当判据。**从模块里读**而不是抄一份，
# 这样 `reasons.py` 加/删一条，门禁自动跟上，不会两边对不上。
REASON_VALUES = {
    v for k, v in vars(reasons).items()
    if not k.startswith("_") and k.isupper() and isinstance(v, str)
}

SCREEN_FILES = sorted(
    p for d in SCREEN_DIRS for p in d.rglob("*.py") if p.name != "__init__.py"
)

# 认屏表里的 handler 住在哪些模块 —— 这是"谁是屏模块"的**唯一判据**。
# 从前这里写死字面量 `"screens"`：搬家后那种写法不会报错，只会永远不匹配。
SCREEN_MODULES = {s.handler.__module__ for s in table}

errs: list[str] = []

# ---------------------------------------------------------------- 1. import 禁令

FORBIDDEN_ROOTS = {"recognizer", "battle"}

for p in SCREEN_FILES:
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                root = a.name.split(".")[0]
                if root in FORBIDDEN_ROOTS:
                    errs.append(f"{p.name}:{n.lineno}: 屏模块不许 import {a.name} —— 认屏层只进不出，import 就成环")
                if a.name in SCREEN_MODULES:
                    errs.append(f"{p.name}:{n.lineno}: 屏模块之间不许互相 import（{a.name}）")
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if n.level and n.level > 0:
                errs.append(f"{p.name}:{n.lineno}: 同包相对 import（level={n.level}）—— 屏模块之间不许互相 import")
            if mod in FORBIDDEN_ROOTS:
                errs.append(f"{p.name}:{n.lineno}: 屏模块不许 import {mod} —— 认屏层只进不出，import 就成环")
            if mod in SCREEN_MODULES:
                errs.append(f"{p.name}:{n.lineno}: 屏模块之间不许互相 import（from {mod} import ...）")

# ------------------------------------- 1b. 扫描面自检：屏模块与认屏表必须一一对上

defining: set[str] = set()
for p in SCREEN_FILES:
    for fn in ast.parse(p.read_text(encoding="utf-8")).body:      # 只看模块级 def
        if isinstance(fn, ast.FunctionDef) and (fn.name == "handle" or fn.name.startswith("handle_")):
            defining.add(f"{p.parent.name}.{p.stem}")

for mod in sorted(defining - SCREEN_MODULES):
    errs.append(f"{mod}: 定义了 handle 却没进认屏表 —— 要么漏接线，要么搬错了包")
for mod in sorted(SCREEN_MODULES - defining):
    errs.append(f"{mod}: 认屏表的 handler 指向它，扫描面里却没有它 —— 门禁漏扫了这个包")

# 另外两个包里**不许有屏** —— 钉住"只有 nav/nodes/combat/system 放屏"这条分界
for d in NON_SCREEN_DIRS:
    for p in sorted(d.rglob("*.py")):
        if p.name == "__init__.py":
            continue
        for fn in ast.parse(p.read_text(encoding="utf-8")).body:
            if isinstance(fn, ast.FunctionDef) and (fn.name == "handle" or fn.name.startswith("handle_")):
                errs.append(f"{d.name}/{p.name}:{fn.lineno}: {d.name}/ 里不许有 {fn.name}() —— 只有 nav/nodes/combat/system 放屏")

# ---------------------------------------------------------------- 2. 表的顺序

names = [s.name for s in table]
notes = {s.name: s.note for s in table}


def at(name):
    """屏名在表里的下标；不在表里返回 None（并记一条错——多半是改名没同步）。"""
    if name not in names:
        errs.append(f"认屏表里没有「{name}」—— check_screens.py 的顺序断言对不上表了（改名了？）")
        return None
    return names.index(name)


def ordered(before, after, why):
    i, j = at(before), at(after)
    if i is None or j is None:
        return
    if not i < j:
        errs.append(f"顺序反了：{before}（第 {i + 1} 行）必须在 {after}（第 {j + 1} 行）之前 —— {why}")
        for name in (before, after):
            errs.append(f"    「{name}」的 note：{notes.get(name, '（没写）')}")


if names:
    if names[0] != "确认弹窗屏":
        at("确认弹窗屏")
        errs.append(f"第一行是「{names[0]}」不是「确认弹窗屏」—— 模态弹窗盖在谁上面都可能，必须最先清")
        errs.append(f"    「{names[0]}」的 note：{notes.get(names[0], '（没写）')}")

    modal_idx = [i for i, s in enumerate(table) if s.modal]
    plain_idx = [i for i, s in enumerate(table) if not s.modal]
    if modal_idx and plain_idx and max(modal_idx) > min(plain_idx):
        bad = table[max(modal_idx)]
        errs.append(f"modal 屏「{bad.name}」（第 {max(modal_idx) + 1} 行）排在非 modal 屏后面 —— 遮挡物要排最前")
        errs.append(f"    「{bad.name}」的 note：{bad.note}")

    for name in ("篝火屏", "怪石屏", "销毁卡牌屏", "商店屏", "祭坛屏", "路口屏",
                 "锻造屏", "护符屏", "已激活护符屏"):
        ordered(name, "通用离开屏", "每个地点界面右下角都有「离开地点」，通用分支抢先点掉，专属策略就永远轮不到")
    ordered("销毁卡牌屏", "商店屏",
            "销毁卡牌屏是**盖在**商店屏右半边上的面板（左边那半屏还是商店屏的立绘和那两个"
            "选项）—— 先判盖在上面那张。今天在两帧面板存档上实测两屏**并不同时命中**"
            "（商店屏的锚点在面板上读不出来）；顺序仍钉着当保险：面板左半边就是商店屏，"
            "锚点哪天读得出来就会同时命中，反了的话商店会在面板上再点一次「移除卡牌」")
    ordered("选卡屏", "篝火屏",
            "选卡屏是**盖在地点屏右半边**上的卡组面板（左边那半屏还是地点屏），所以它站在"
            "「地点专属」那一块的最前头、钉着「必须在块首」。2026-10-06 在篝火上撞到面板版："
            "篝火先认领就会一直点「激活护符」、一直等不到「确认选择」，原地空转 375 轮"
            "（debug/run_1006_0433.log:2452 起，现场帧 debug/screenshots/"
            "_stuck_campfire_panel.png）—— 面板左半边那两枚选项照样读得出来，两屏真同时命中")
    ordered("选卡屏", "事件屏",
            "选卡屏左边那半屏就是事件正文：点中一张卡之后详情面板会在标题区写上卡片**类型**"
            "「诅咒牌」、选项区写上卡名，事件屏那两道闸全过 —— 2026-10-03 它就这么被当成"
            "一个叫「诅咒牌」的新事件自动入册。必须让「选择卡牌」这个标题先认领")
    ordered("事件屏", "事件结果屏", "事件结果屏没有标题，事件屏的判据读不出时才轮到它")
    ordered("事件屏", "真龙现身·第二页屏",
            "真龙第二页没有标题，和事件屏是同一个控件家族 —— 有标题的那一页归事件集管，"
            "先认领的仍是事件屏（第一页的选项小字本来也不撞本行的判据）")
    ordered("游艺·结果屏", "游艺·转盘屏", "结果面板上「发射」还在屏上（实测 0.9998），先判转盘就会误点发射")

    # 「单选项屏」是**最兜底**的一条（用户 2026-10-03 定的单选项保底），所以地图
    # 不再是最后一行；但地图仍必须在它**前面** —— 兜底的规则要是抢在地图前面，
    # 地图上一记误双击就等于脚本自己挑了一条路，而挑路是策略（只按优先表走）。
    ordered("地图屏", "单选项屏",
            "单选项保底不能抢在地图前面：地图上一记误双击 = 脚本自己挑路")
    if names and names[-1] != "单选项屏":
        at("单选项屏")
        errs.append(f"最后一行是「{names[-1]}」不是「单选项屏」—— 它是最兜底的一屏"
                    f"（兜底规则排在谁后面就是谁优先，见那一行的 note）")

# ------------------------------------------------------------- 2b. 兜底屏（recheck）
#
# `recheck=True` 的屏命中后要拿现帧整表复认一道（recognizer._confirm）——
# 治的是「过渡帧」那一类：`identify` 一轮只截一张图、31 行扫下来约 3 秒，
# 靠后的行判的是 3 秒前那一帧；屏正在换时地点屏的壳先画出来、新屏的字还没画，
# 兜底屏就凭一枚**地点屏家族通用的控件**抢先认领（2026-10-06 第一例：
# 「通用离开屏」抢走「已激活护符屏」，又丢了一次「狭缝」→直面首领）。
#
# 判据是"这一屏是靠通用控件/纯兜底认出来的"，**不是"它排在后面"** ——
# 每加一行，它每次命中就多花一次扫掠（约 3 秒）。所以这里把它钉成清单：
# 名单对不上就报错，逼着改的人回来看这段话。
RECHECK_EXPECT = {
    "通用离开屏": "「离开地点」每个地点屏都有，过渡帧上会先于真屏的字画出来",
    "事件结果屏": "「赶紧离开」和「离开地点」同族，都是地点屏家族通用的控件",
    "单选项屏": "判据只有「选项区里恰好一行」，本来就是最弱的一条，又排在最后一行",
}
recheck = {s.name for s in table if s.recheck}
for name, why in RECHECK_EXPECT.items():
    if name not in recheck:
        at(name)
        errs.append(f"「{name}」没标 recheck —— {why}；它命中后会凭一枚通用控件抢先认领"
                    f"（见 recognizer._confirm 那段）。要摘掉这条，先改这段清单")
for name in sorted(recheck - set(RECHECK_EXPECT)):
    errs.append(f"「{name}」标了 recheck，但不在兜底屏清单里 —— 每加一行，"
                f"它每次命中就多花一次扫掠（约 3 秒）。真要加，把这段清单改了、"
                f"并把理由写进那行的 note")

# ---------------------------------------------------------------- 3. handle 的返回

class _ReturnScan(ast.NodeVisitor):
    """抓 handle 里 `return None` 和裸 `return`。**不下钻嵌套函数**（那些是助手）。"""

    def __init__(self):
        self.bad: list[ast.Return] = []

    def visit_Return(self, node):
        if node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None):
            self.bad.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        pass

    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_Lambda(self, node):
        pass


for p in SCREEN_FILES:
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        if not (fn.name == "handle" or fn.name.startswith("handle_")):
            continue
        scan = _ReturnScan()
        for stmt in fn.body:
            scan.visit(stmt)
        for r in scan.bad:
            errs.append(
                f"{p.name}:{r.lineno}: {fn.name}() 里 {r.lineno} 行 return None/裸 return"
                f" —— 契约是 \"\"（处理完）或非空理由（停下等人），没有 None"
            )

# ---------------------------------------------------- 3b. 停车理由不许写回字面量
#
# 判据是「这个字符串**正好等于** shared/reasons.py 里某个常量的值」，不是
# "看着像理由" —— 所以 `print("    停下等人：…")` 那种整句、以及任何游戏原词
# 都不会被误伤。真·理由是**会被原样打印给用户**的，抄四份 = 改一处漏三处。

for p in SCREEN_FILES:
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not isinstance(n, ast.Constant) or not isinstance(n.value, str):
            continue
        if n.value in REASON_VALUES:
            errs.append(
                f"{p.name}:{n.lineno}: 停车理由写成了字面量 {n.value!r}"
                f" —— 一律 `from shared.reasons import ...` 取常量"
            )

# ---------------------------------------------------------------- 4/5. 屏名与字段

const_values = {v for k, v in vars(strings).items() if not k.startswith("_") and isinstance(v, str)}
seen_names: dict[str, int] = {}
for i, s in enumerate(table, 1):
    if not s.name:
        errs.append(f"第 {i} 行没有屏名")
        continue
    if s.name in seen_names:
        errs.append(f"屏名「{s.name}」重了（第 {seen_names[s.name]} 行和第 {i} 行）—— 两行会抢答")
    seen_names[s.name] = i
    if not s.name.endswith("屏"):
        errs.append(f"屏名「{s.name}」没带「屏」后缀 —— 屏名是脚本自己的词，要和游戏里的字区分开")
    if s.name in const_values:
        errs.append(f"屏名「{s.name}」撞上了 strings.py 的常量值 —— check_strings.py 会把它判成裸字符串")
    if not callable(s.handler):
        errs.append(f"「{s.name}」没有 handler —— 认出来没人动手")
    if not s.note.strip():
        errs.append(f"「{s.name}」没写 note —— 顺序为什么排在这，注释就是唯一的凭证")
    if not s.nodes and s.check is None:
        errs.append(f"「{s.name}」既没有 nodes 也没有 check —— 永远认不出来")

# ---------------------------------------------------------------- 报告

report_gaps: list[str] = []
report_sleeps: list[str] = []
for p in SCREEN_FILES:
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if n.func.attr == "click_when" and not any(k.arg == "guard" for k in n.keywords):
            report_gaps.append(f"{p.name}:{n.lineno}")
        if n.func.attr == "click_node":
            report_gaps.append(f"{p.name}:{n.lineno} 用了旧原语 click_node（动手应走 click_when）")
        if n.func.attr == "sleep" and isinstance(n.func.value, ast.Name) and n.func.value.id == "time":
            report_sleeps.append(f"{p.name}:{n.lineno}")

# ---------------------------------------------------------------- 输出

if errs:
    print(f"\n{len(errs)} 处不对：\n")
    for e in errs:
        print(" -", e)
    sys.exit(1)

print(
    f"认屏表 {len(table)} 行，屏名 / handler / note / 顺序断言全过；"
    f"{len(SCREEN_FILES)} 个屏模块（{'+'.join(d.name for d in SCREEN_DIRS)}）无环 import；"
    f"屏模块与表一一对上。"
)
if report_gaps:
    print(f"\n报告（不判负）：{len(report_gaps)} 处 click_when 没带 guard：")
    for r in report_gaps:
        print("  ·", r)
if report_sleeps:
    print(f"\n报告（不判负）：{len(report_sleeps)} 处残留 time.sleep：")
    for r in report_sleeps:
        print("  ·", r)
