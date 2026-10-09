#!/usr/bin/env python3
"""核对 script/strings.py：它说的字，游戏/管线里真的有；脚本用的字，都从它来。

它盯六件事（前三条防"名字是假的"，后三条防"名字是死的 / 躲着不用的"）：

  1. **一、里的每个节点名必须真存在**于 assets/resource/pipeline/*.json ——
     写错一个字，运行时 `probe()` 会拿一个空节点去识别，什么也认不出来，
     而且**不报错**，只是静静超时。这是最难查的一类错。
  2. **二、里的每档难度必须对应一个 `难度-<名字>` 节点**（仪式.json 那 14 个）。
  3. **三、里的每个地图词条必须出现在 map.py 的 NODE_KINDS 里**。
  4. **脚本里不许再有裸字符串**：等于某常量值的字面量、或直接传给
     `Game.click_node/see/probe/...` 的字符串字面量，一律报出来。
  5. **用到的常量必须 import 过**——少了会 NameError，但只在跑到那条分支时才炸。
  6. **strings.py 里不许有死名字**：没人引用的常量，多半是改名后留下的残骸。

用法：`python tools/check_strings.py`（无参数，退出码 0 = 全过）
"""

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
SCRIPT_DIR = ROOT / "script"
PIPELINE_DIR = ROOT / "assets" / "resource" / "pipeline"
STRINGS_PY = SCRIPT_DIR / "strings.py"
MAP_PY = SCRIPT_DIR / "nav" / "map.py"

# 这些方法的名字参数**必须是常量**。写在别处的字面量（print、路径、编码）不管。
# click_when / wait_gone 是 2026-10-02 加的原语 —— 它们的节点参数同样走 strings.py。
NODE_METHODS = {
    "click_node", "see", "probe", "box_of", "read_number", "text_of", "wait_for", "enter_run",
    "click_when", "wait_gone", "node_offset",
}

errs: list[str] = []


def docstring_ids(tree):
    """所有 docstring 那一个 Constant 节点的 id（它们不算"游戏词条"）。"""
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = n.body[0] if n.body else None
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant):
                ids.add(id(b.value))
    return ids


def parents_of(tree):
    par = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            par[id(c)] = n
    return par


def convertible(node, par, docs):
    """这个字符串字面量是不是"该被常量替掉"的那种。

    和 debug/_migrate_strings.py 用的是同一条判据 —— 当初就是按它把字面量
    换成常量的，所以这里等于在问"迁移有没有漏网"。docstring、f-string 里的一段字、
    `print(...)`/`RuntimeError(...)` 这类 Name 调用的实参都是文案，不算。
    """
    p = par.get(id(node))
    if id(node) in docs or isinstance(p, ast.JoinedStr):
        return False
    if isinstance(p, ast.Call):
        return not isinstance(p.func, ast.Name)
    return isinstance(p, (ast.Compare, ast.List, ast.Tuple, ast.Dict, ast.BoolOp, ast.If, ast.Return,
                          ast.Assign, ast.Set, ast.Subscript, ast.IfExp, ast.arguments))


def str_consts(node):
    """实参里嵌着的字符串字面量 —— 包括 list/tuple/set 里层的。

    只查"直接是 Constant 的实参"不够用了：`click_when(节点, guard=["篝火界面"])`
    里那个裸字符串藏在一层 list 下面（2026-10-02 加 guard 参数时发现的）。
    """
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n


def strip_jsonc_comments(text):
    """去掉 // 与 /* */ 注释，字符串里的不算。和 tools/validate_schema.py 同一套规则。"""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif text.startswith("/*", i):
            i = text.find("*/", i)
            i = n if i < 0 else i + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_jsonc(path):
    return json.loads(strip_jsonc_comments(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- strings.py

src = STRINGS_PY.read_text(encoding="utf-8")
lines = src.splitlines()

# 常量 → 它落在第几节（靠 `# 一、xxx` 这类小标题切）
section_of_line: dict[int, str] = {}
cur = "(没有归属)"
for i, ln in enumerate(lines, 1):
    m = re.match(r"^#\s*([一二三四五六七八九十]+)、(\S+)", ln)
    if m:
        cur = m.group(1)
    section_of_line[i] = cur

consts: dict[str, str] = {}      # 名字 → 值
where: dict[str, int] = {}       # 名字 → 行号
section: dict[str, str] = {}     # 名字 → 节
for node in ast.parse(src).body:
    if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
        continue
    if not isinstance(node.value.value, str) or len(node.targets) != 1:
        continue
    t = node.targets[0]
    if not isinstance(t, ast.Name):
        continue
    consts[t.id], where[t.id], section[t.id] = node.value.value, node.lineno, section_of_line[node.lineno]

VALUES = set(consts.values())
# 两个常量共用一个值 —— 反查（值→名字）会分不清是谁
for d, c in sorted(Counter(consts.values()).items()):
    if c > 1:
        errs.append(f"strings.py: 值 {d!r} 被 {c} 个常量共用，反查（值→名字）会分不清是谁")

# ---------------------------------------------------------------- 管线节点

nodes: dict[str, str] = {}       # 节点名 → 哪个 json
for p in sorted(PIPELINE_DIR.glob("*.json")):
    for k in load_jsonc(p):
        if k in nodes:
            errs.append(f"管线: 节点名 {k!r} 在 {nodes[k]} 和 {p.name} 里各有一份")
        nodes[k] = p.name

# 三节词条必须真被 map.py 的词典用到（2026-10-02 起只有 NODE_KINDS 一本表：
# 用户当天「不要使用别名了」，每个写法各成一类，不再折到别的类上）
map_names: set[str] = set()
for node in ast.walk(ast.parse(MAP_PY.read_text(encoding="utf-8"))):
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
            and node.targets[0].id == "NODE_KINDS":
        map_names |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

# 名字里带 `-` 的节点常量（`卡牌_无畏斧 = "卡牌-无畏斧"`、`卡面_隐痛 = "卡面-隐痛"`…）：
# 标识符写不出减号，只能写成下划线，于是"值必须与管线一字不差"这条**自己核**（见下面
# 那一轮）。凡是第一节能这样反推的都在这里，别再写死某个名字。
DASHED = {n for n, s in section.items() if s == "一" and "-" in consts[n]}

# 按 strings.py 里的先后逐条核 —— 报出来的顺序就和翻文件一样
for name, sec in section.items():
    val, at = consts[name], where[name]
    if sec == "一" and val not in nodes and name not in DASHED:
        errs.append(f"strings.py:{at}: 节点 {val!r}（常量 {name}）在管线里不存在")
    elif sec == "二" and f"难度-{val}" not in nodes:
        errs.append(f"strings.py:{at}: 第二节的 {val!r} 没有对应的「难度-{val}」节点")
    elif sec == "三" and name not in map_names:
        errs.append(f"strings.py:{at}: 词条 {val!r} 没出现在 map.py 的 NODE_KINDS 里")
    elif sec == "(没有归属)":
        errs.append(f"strings.py:{at}: {name} 掉在三节小标题外面了，挪进对应那节")

# 「标识符换过字」的那批：`卡牌_无畏斧` 的值必须正好是 `卡牌-无畏斧`，而且真在管线里。
# （只核"值在不在管线里"是不够的 —— 标识符和值**对不上**时，脚本点的是另一个节点，
#   而那多半是打错字：`卡面_隐痛 = "卡面-隐通"` 只要管线里真有 卡面-隐通 就一路查不出来。）
for name in sorted(DASHED):
    if name.replace("_", "-") != consts[name]:
        errs.append(f"strings.py:{where[name]}: 常量 {name} 的值是 {consts[name]!r}，"
                    f"照标识符该写 {name.replace('_', '-')!r} —— 两者对不上")
    if consts[name] not in nodes:
        errs.append(f"strings.py:{where[name]}: 节点 {consts[name]!r} 在管线里不存在")

# ---------------------------------------------------------------- 脚本

used: set[str] = set()           # 被脚本引用过的常量
# rglob：script/ 下还有 nav/ nodes/ combat/ system/ 四个包（一屏一个模块），一个都不能漏
for p in sorted(SCRIPT_DIR.rglob("*.py")):
    if p.name == "strings.py":
        continue
    tree = ast.parse(p.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "strings":
            imported |= {a.name for a in n.names}

    refs = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in consts}
    used |= refs

    # 5. 用了却没 import
    for name in sorted(refs - imported):
        errs.append(f"{p.name}: 用了 {name} 但没 import —— 跑到这条分支才 NameError")

    # 4. 裸字符串
    docs = docstring_ids(tree)
    par = parents_of(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and n.value in VALUES and convertible(n, par, docs):
            errs.append(f"{p.name}:{n.lineno}: 还是裸字符串 {n.value!r} —— 换成 strings.py 的常量")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in NODE_METHODS:
            # 位置参数与关键字参数一起扫（guard=[...] / nodes=[...] 里的字也算）
            for a in list(n.args) + [k.value for k in n.keywords]:
                for c in str_consts(a):
                    errs.append(
                        f"{p.name}:{c.lineno}: {n.func.attr}() 收到裸字符串 {c.value!r}"
                        f" —— 游戏里的字一律走 strings.py 常量"
                    )

deads = sorted(set(consts) - used)
for name in deads:
    errs.append(f"strings.py:{where[name]}: {name} 没有任何脚本引用（死名字）")

# ---------------------------------------------------------------- 报告

if errs:
    print(f"\n{len(errs)} 处不对：\n")
    for e in errs:
        print(" -", e)
    sys.exit(1)
print(
    f"strings.py: {len(consts)} 个常量 —— "
    f"节点 {sum(1 for s in section.values() if s == '一')} / "
    f"难度 {sum(1 for s in section.values() if s == '二')} / "
    f"词条 {sum(1 for s in section.values() if s == '三')}；"
    f"管线共 {len(nodes)} 个节点，全部核过。"
)
