"""牌名这件事：**五张卡牌配置 + 判据** —— 所有屏共用这一份。

五张配置住在 `script/cards/`（严格 JSON，改完不用重启脚本）：

| 文件 | 管什么 | 今天的内容 |
|---|---|---|
| `保留.json` | 要保留、不许动手的卡名 | 无畏斧 · 莽撞头槌 · 隐痛 |
| `移除.json` | **优先移除**的卡名（压过 保留） | 空 |
| `升变.json` | 锻造屏上允许升变的卡名 | 无畏斧 |
| `升级.json` | 升级屏上允许升级的卡名（空 = 一张都不选） | 空 |
| `选择.json` | **往卡组里加牌**时想拿的卡名（复制屏 / 加入卡组屏） | 空 |

**三条独立的链，别并成一个决策函数**（用户 2026-10-13 定的前两条，2026-10-15 加的第三条）：

  · **保留 / 移除** —— 互补，**这两个怎么用有四个方式**（`均不使用` / `只使用移除` /
    `只使用保留` / `均使用`，换方式改模块级的 `MODE` 一个词；两张表见下面 `MODE` 那
    一段）。默认 `均使用`＝**移除优先**：一张牌要保留 ⟺ `base_name(名) ∉ 移除.json`
    **且** `名 ∈ 保留.json`（`is_kept` / `is_removed`）。
  · **升变 / 升级** —— 另一条，`升变.json` 只决定"哪几种牌能升"
    （"一次最多升几把"在 `nodes/forge.py` 的 `UPGRADES`，是另一个轴）。
  · **选择** —— 第三条，只管**加牌**那两屏（`ops/card_copy.py` 的复制屏、
    `ops/card_add.py` 的加入卡组屏）。用户 2026-10-15 的原话：「添加一个逻辑, 与升级,
    升变, 移除同等级, 叫做选择.json, 用于出现卡牌选择页面时, 进行选择」，随后把范围
    说定成「选择, 是用来管理向卡组添加卡牌的逻辑」。`is_wanted` 是它唯一的判据，
    **和上面两条没有交集**：移除 / 升级 / 销毁面板 / 升变各归各的名单，不并。

⚠️ **`选择.json` 出厂是空的**（`"卡牌": []`）⇒ `has_select` 恒假 ⇒ 那两屏走的
**还是加它之前那条路**（复制屏取左上角第一张、加入卡组屏一张都不拿）。

**四条规则一律按卡面筛**，所以本模块还管那张「卡名 ↦ 卡面模板节点」的对应表
（`FACES`）。**表按屏分**：模板是按屏裁的 —— 商店销毁面板（4 列）那四条
`卡面-*` 搬到事件选卡屏（5 列）上分数掉到 0.73~0.91（实测，见
`debug/_cardtpl_check.py` 抬头），所以**一屏一套**，不是把阈值压下去。

**为什么住在 `shared/`**：这份名单最早在 `nodes/cardpick.py`（2026-10-03 事件那条
路）。2026-10-04 商店那条路要的是**同一张单子**，而屏模块之间不许互相 import
（`tools/check_screens.py` 第 1 条钉着），名单就只能往公共层挪。2026-10-13 用户要求
"把四张配置与相关代码统一"，于是 `ops/card_destroy.py`（商店销毁面板）、
`ops/card_remove.py`（事件选卡屏的移除）、`nodes/forge.py`（锻造升变）、
`ops/card_upgrade.py`（升级）四处**都只看这一个模块**。

**加一张保留牌要动的地方**（缺一处就有个洞）：

  1. `script/strings.py`：加 `卡名_新牌`，以及**它那一屏**的 `卡面_新牌` 常量。
  2. `assets/resource/pipeline/卡牌族.json`：加 `卡面-新牌` 节点 ——
     **必须先有存档帧裁图、量准阈值**（照那个文件抬头那套实测流程）。
  3. **本模块的 `FACES`**：在对应屏那张表里加 `卡名_新牌: (卡面_新牌,)`。
  4. `script/cards/保留.json`：把 `"新牌"` 写进 `卡牌`。

删一张保留牌**只动第 4 步**就够（卡面那些是派生出来的）；但**第 3 步的卡面要一起删**，
否则那张牌会被当成"要留的"跳过。

本模块只 import `strings` 与标准库（外加 `shared/kit` 的日志口）—— 卡名是游戏里的
字，从 `strings` 取。
"""

import json
from pathlib import Path

from strings import (卡名_无畏斧, 卡名_莽撞头槌, 卡名_隐痛,
                     卡面_隐痛, 卡面_无畏斧, 卡面_无畏斧_熔岩, 卡面_莽撞头槌,
                     卡牌_无畏斧)
from shared.kit import log


CARDS_DIR = Path(__file__).parent.parent / "cards"

_FILES = {
    "keep": "保留.json",
    "remove": "移除.json",
    "ascend": "升变.json",
    "upgrade": "升级.json",
    "select": "选择.json",
}

# 配置里的那一格数组叫什么（其余非 `_` 开头的键都算写错了）
_NAMES_KEY = "卡牌"

# ---- `保留.json` / `移除.json` 这两份**怎么用**：用户 2026-10-13 定的四个方式 ----
#
# 用户原话：「同时, 移除与保留逻辑, 可以只使用一个」＋「两份配置均保留, 在代码中
# 有四个方式 —— 均不使用 / 只使用移除 / 只使用保留 / 均使用」。**两份配置一个字都
# 不删**，换方式只改下面这一行 `MODE`（`Rules` 的 `mode=` 可以逐次覆盖它，单测就
# 是那么走的）。
#
#   | 方式 | 一张牌算「保留」的条件 |
#   |---|---|
#   | `均使用`（今天） | `名 ∈ 保留` **且** `名 ∉ 移除` —— **移除优先** |
#   | `只使用保留` | `名 ∈ 保留`（`移除.json` 整个不参与） |
#   | `只使用移除` | `名 ∉ 移除`（`保留.json` 整个不参与） |
#   | `均不使用` | **全都算保留** —— 两份名单都不参与，「谁也不动」 |
#
# `均不使用` 取「谁也不动」这一侧（而不是"全都可移除"）：两份名单都不用时，屏上
# 没有任何依据说哪张该动，而动卡（销毁 / 移除）是**不可逆**的 —— 跟本工程
# 「读不出来就不猜」是同一个口径。
#
# ⚠️ 换方式之前先看看那两份里真写了什么：`移除.json` 空着时 `名 ∉ 移除` 恒真，
# `只使用移除` 就退化成「谁也不动」了；而 `保留.json` 空着时 `均使用` / `只使用保留`
# 都退化成「一张都不留」（= 全都能动）。四种方式只有在**两份都非空**时才彼此都不同。
MODE_NONE = "均不使用"
MODE_REMOVE = "只使用移除"
MODE_KEEP = "只使用保留"
MODE_BOTH = "均使用"

MODES = (MODE_NONE, MODE_REMOVE, MODE_KEEP, MODE_BOTH)

MODE = MODE_BOTH        # ← 换保留/移除的方式只改这一个字

# 屏名 —— **FACES 的键**。用常量而不用字面量：打错了 import 期就报，
# 不会静悄悄落进"这一屏没有卡面表"那条静默分支。
SCREEN_DECK = "销毁面板"      # 商店点「移除卡牌」弹出的那一屏（标题「你的卡组」），4 列
SCREEN_FORGE = "锻造屏"       # 锻造使的「卡牌升变」界面

# 「卡名 ↦ 卡面模板节点」对应表。**配置只写名字，名字对哪几张图在这儿。**
#
# **声明顺序 = keep_templates() 的输出顺序**，必须与 2026-10-13 之前的
# `KEEP_TEMPLATES`（= 卡面_隐痛, 卡面_无畏斧, 卡面_无畏斧_熔岩, 卡面_莽撞头槌）
# 逐项一致 —— `debug/test_deck.py` 的假 `boxes={节点名: [...]}` 是按名字索引的，
# 顺序一变那 19 个场景就对不上。`debug/test_cards.py` 把这条钉死。
FACES = {
    SCREEN_DECK: {
        卡名_隐痛: (卡面_隐痛,),
        卡名_无畏斧: (卡面_无畏斧, 卡面_无畏斧_熔岩),
        卡名_莽撞头槌: (卡面_莽撞头槌,),
    },
    SCREEN_FORGE: {
        卡名_无畏斧: (卡牌_无畏斧,),
    },
}


class CardsConfigError(Exception):
    """五张配置读不动 / 名单要的卡没配上卡面 —— 调用方据此停下等人（不猜）。"""


def _read_names(key):
    """读一份配置的 `卡牌` 数组。**每次都重读**（无缓存），改了不用重启脚本。"""
    path = CARDS_DIR / _FILES[key]
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
    except FileNotFoundError:
        raise CardsConfigError(f"找不到配置文件 {path}") from None
    except json.JSONDecodeError as exc:
        # 每一份都是严格 JSON —— `script/**` 不在 .vscode/settings.json 的 jsonc
        # 映射里，所以写 `//` 注释会当场炸在这儿。
        raise CardsConfigError(f"{path} 不是合法 JSON（写注释了吗？）：{exc}") from None

    if not isinstance(data, dict):
        raise CardsConfigError(f"{path} 的顶层应当是一个对象")

    # `_` 前缀的键是文档；除了它和 `卡牌` 之外还写了别的键 = 名字写错了
    # （比如 "卡片" / "卡牌 "），那会静悄悄读成空名单 —— 当场报出来。
    stray = [k for k in data if not k.startswith("_") and k != _NAMES_KEY]
    if stray:
        raise CardsConfigError(
            f"{path} 里有认不出的键 {'、'.join(repr(k) for k in stray)}"
            f"（本文件只认 `{_NAMES_KEY}`；`_` 开头的算说明）")

    names = data.get(_NAMES_KEY)
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise CardsConfigError(f'{path} 的 "{_NAMES_KEY}" 应当是一个字符串数组')

    return tuple(n.strip() for n in names if n.strip())


def base_name(name):
    """卡名去掉升级后缀 `+`：`无畏斧+` 和 `无畏斧` 是**同一种牌**。

    管线「卡牌名」那条的原话：「同名卡可能有 + 后缀（升级版），比对时按'去掉 +
    的前缀'来认」。实测这局读出来的是 `无畏斧+`、`莽撞头槌+`。
    比对名单之前一律先过这一道。
    """
    return (name or "").rstrip("+").strip()


def looks_like_name(text):
    """这段字像不像卡名（至少两个汉字）。

    没选中任何卡时，详情面板那块 roi 会读到别的屏上的零碎字（实测整片底色被
    读成 `一の`，score 0.161），加这道闸挡噪声 —— 跟事件屏的
    `_looks_like_title` 一个道理：读到的字不像名字 = **没读到**，
    调用方据此走"不猜"那条路，别把噪声当成一张牌的名字。
    """
    return sum(1 for ch in text if "一" <= ch <= "鿿") >= 2


_warned = set()     # 同一条"缺卡面"的警告只打一次（keep_templates 每轮都会调）
_logged_mode = None  # 保留/移除 的方式只在**变了**的时候打一行（load_rules 每屏都调）


def _log_mode(mode):
    """方式变了打一行日志（同一趟里一个方式只打一次）。"""
    global _logged_mode
    if mode == _logged_mode:
        return
    _logged_mode = mode
    log(f"  卡牌配置：保留/移除 方式 = {mode}")


def _warn_missing(screen, names):
    key = (screen, tuple(names))
    if key in _warned:
        return
    _warned.add(key)
    log(f"  ! 卡牌配置：保留名单里的 {'、'.join(f'「{n}」' for n in names)}"
        f" 在「{screen}」上没有卡面模板 —— 这一屏保护不了它"
        "（后面那道「点开读卡名」还兜着，只是慢一点、也可能白白少认一张）")


class Rules:
    """一趟判据：五份配置读进来的结果 + 由它派生的卡面模板表。

    **不可变**（构造完就不再改），所以可以在一个入口里取一份、往下传着用。

    `mode` 决定 `保留.json` / `移除.json` **怎么用**（四个方式，见模块顶上那段）——
    本类把它摊成两个布尔（`use_keep` / `use_remove`），**所有下游只看
    `is_kept` / `is_removed`**，所以换方式一处调用点都不用改。

    `select`（2026-10-15 加的第五份）**连着上面那个 `mode` 都不沾** —— 它自己一条链、
    只看 `is_wanted`，所以按关键字传、带默认值：加它之前那些 `Rules(keep=…, remove=…,
    ascend=…, upgrade=…)` 一个字都不用改（`debug/test_cards.py` 里二十多处就是）。
    """

    def __init__(self, keep, remove, ascend, upgrade, select=(), mode=MODE):
        if mode not in MODES:
            raise CardsConfigError(
                f"保留/移除 的方式写成了 {mode!r} —— 只认 {'、'.join(MODES)}")
        self.mode = mode
        self.use_keep = mode in (MODE_KEEP, MODE_BOTH)
        self.use_remove = mode in (MODE_REMOVE, MODE_BOTH)
        self.keep_names = tuple(keep)          # 配置原文，原样留着（日志/报错要打）
        self.remove_names = tuple(remove)
        self.ascend_names = tuple(ascend)
        self.upgrade_names = tuple(upgrade)
        self.select_names = tuple(select)
        self._keep = frozenset(base_name(n) for n in self.keep_names)
        self._remove = frozenset(base_name(n) for n in self.remove_names)
        self._select = frozenset(base_name(n) for n in self.select_names)
        # 名单**空**= 这条链整个不启用（不是"一张都不想要"，两者在这两屏上恰好同效，
        # 但语义不同 —— 空名单走的是"加它之前那条老路"，见 is_wanted 的 docstring）。
        self.has_select = bool(self.select_names)

    # ---- 名字面：保留 ⇄ 移除（互补；"移除优先"是"两个都用"时的口径）----

    def is_kept(self, name):
        """这张牌要不要留 —— **看 `self.mode`**（四种方式见模块顶上那张表）：

          · `均不使用`     → 一律 True（谁也别动）
          · `只使用移除`   → `名 ∉ 移除`
          · `只使用保留`   → `名 ∈ 保留`
          · `均使用`（今天）→ `名 ∈ 保留` **且** `名 ∉ 移除`（**移除优先**）
        """
        if not self.use_keep and not self.use_remove:
            return True                        # 均不使用：两份名单都不参与
        base = base_name(name)
        if self.use_remove and base in self._remove:
            return False                       # 移除优先 —— 两个都用时压过保留
        if self.use_keep:
            return base in self._keep
        return True                            # 只使用移除：不在移除名单里的都留

    def is_removed(self, name):
        """这张牌要不要移除 —— 就是 `not is_kept`，**严格互补**。

        互补是这条判据唯一的形状：屏上每一格只有"动它"和"留着"两种去向，
        分开写两个公式迟早会写出"既不保留也不移除"或"既保留又移除"的格子。
        移除.json 空着、方式又是 `均使用`（今天）时，它退化成
        "不在保留名单里的都要移除"，与 2026-10-03 起的现状一字不差。

        ⚠️ 名字**读不出来**（`""` / `None`）在 `均使用` / `只使用保留` 下落进
        "要移除"那一侧 —— 调用方必须自己先挡住（现状是 `c["name"] and ...`），
        别拿它替"读不出"做决定。（`只使用移除` / `均不使用` 下反过来落在"留着"那侧。）
        """
        return not self.is_kept(name)

    # ---- 名字面：选择（第三条链，只管"往卡组里加牌"那两屏）----

    def is_wanted(self, name):
        """这张牌**想不想要** —— 是不是 `选择.json` 名单里的那一张。

        和 `is_kept` / `is_removed` **没有关系**（用户 2026-10-15 定的："与升级、
        升变、移除同等级" = 一条独立的链，不是那两条的补充）。升级后缀照旧先去掉：
        `无畏斧+` 和 `无畏斧` 是同一种牌（`base_name`）。

        ⚠️ **名单空着的时候它一律 False**，但调用方**不该靠它分辨"名单空"和"一张都
        没挑中"** —— 这两件事去向不同（名单空 = 这屏走老路；名单非空却没挑中 = 走用户
        定的"能跳过就跳过、不能就第一张"）。分辨用 `has_select`。
        """
        return base_name(name) in self._select

    # ---- 卡面面：由名字派生（先过 is_kept / 名单本身）----

    def keep_templates(self, screen):
        """这一屏上"要保护的卡"的卡面模板节点，**按 FACES 声明序**。

        派生自**生效的保留名单**（= `is_kept` 为真的那些，随 `mode` 变：
        `均使用` 时是 `保留 ∖ 移除`），所以把一张牌写进 移除.json 会让它在这一屏上
        也不再被保护。该屏上没有卡面模板的名字只**警告**，不抛错 ——
        终点还有"点开读一眼卡名"那道闸兜着。
        """
        return self._faces(screen, (n for n in self.keep_names if self.is_kept(n)),
                           strict=False)

    def ascend_templates(self, screen):
        """这一屏上"允许升变"的卡面模板节点，**按 FACES 声明序**。

        锻造屏**没有读名字的兜底**（那屏只能对图），所以名单里的卡在该屏上
        没有卡面模板时**抛 `CardsConfigError`** —— 停车等人，不猜。
        """
        if not self.ascend_names:
            return ()
        return self._faces(screen, self.ascend_names, strict=True)

    def _faces(self, screen, names, strict):
        names = tuple(names)
        want = {base_name(n) for n in names}
        table = FACES.get(screen, {})
        idx = {base_name(key): faces for key, faces in table.items()}
        out = []
        for base, faces in idx.items():          # 声明序
            if base in want:
                out.extend(faces)
        missing = [n for n in names if base_name(n) not in idx]
        if missing:
            if strict:
                raise CardsConfigError(
                    f"名单里的 {'、'.join(f'「{n}」' for n in missing)}"
                    f" 在「{screen}」上没有卡面模板 —— 这一屏只能对图，不猜，停车等人")
            _warn_missing(screen, missing)
        return tuple(out)


def load_rules():
    """把五份配置读成一份 `Rules`。**每个入口调一次**，往下传着用。

    无缓存 —— 每次调用都重读那五个文件（对齐 `events.json`「改完不用重启脚本」的
    哲学）。`ops/card_destroy.py` 的**逐卡循环里不重载**：那会 N 次读盘，
    还会让"循环走到一半改了配置"变成半程换判据。

    `保留/移除 怎么用`取模块级的 `MODE`（换方式改那一行）；`保留.json` /
    `移除.json` 两份文件**都照读不误** —— 方式只决定"用不用它"，不改那份配置。

    第五份 `选择.json` 只是"多读一个文件"：它的异常面（缺文件 / 坏 JSON / 多写键 /
    `卡牌` 不是字符串数组）和另外四份**共用 `_read_names`**，所以**自动**是同一套
    停车理由（`WAIT_CARDS_CONFIG`）—— 不用再写一遍。
    """
    _log_mode(MODE)
    return Rules(keep=_read_names("keep"),
                 remove=_read_names("remove"),
                 ascend=_read_names("ascend"),
                 upgrade=_read_names("upgrade"),
                 select=_read_names("select"),
                 mode=MODE)
