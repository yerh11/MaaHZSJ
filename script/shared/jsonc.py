"""把 json 当 **JSONC** 读 —— 允许 `//` 行注释与 `/* */` 块注释。只依赖标准库。

来历（2026-10-15 用户定）：「以后, 均使用jsonc, 显示说明使用的是jsonc」。
在这之前只有 `assets/**/*.json` 在**编辑器**里按 jsonc 走（`.vscode/settings.json`
的 `files.associations`），而脚本**运行时**读 json 一律是裸 `json.load` ——
于是往 `script/cards/*.json` 里写一句 `//`，编辑器不报错、脚本一跑到那儿当场炸。
现在读取口统一走这里，两边口径一致。

⚠️ **本模块只做"读得动"，不做"写回去还留着注释"。** 所以：

  · **会被脚本回写的 json 不许写注释** —— 目前只有 `script/events.json`：
    `nodes/event.py` 的 `save_book()` 是整文件读-改-写（`json.dump` 重建整个文件），
    注释在那一步会被**静默抹掉**。那一份因此**继续用裸 `json.load` 严格读** ——
    写进去的注释当场报错，好过被悄悄删掉。它的说明继续用 `_说明` 这类**键**写
    （键会被 `save_book` 原样保住，见那段代码的注释）。
  · 其余 json（`script/cards/` 五份 · `assets/` 全部）**只读不回写**，随便写注释。

去注释那台机器与 `tools/validate_schema.py` 的 `strip_jsonc_comments`、
`tools/check_strings.py` 的同名函数**同一套规则**（`//` 到行尾、`/* */` 整段、
**字符串里的不算注释**）。三处各留一份实现是没办法的事 —— `tools/` 不许 import
`script/`，而 `script/` 也不该去 import `tools/`（那是开发期工具，不进运行时）。
改规则时**三处一起改**，`debug/test_jsonc.py` 钉着它们同解。
"""

import json

__all__ = ["strip", "loads", "load"]


def strip(text):
    """删掉注释，其余一个字符不动（含字符串里的 `//`、`/*`）。

    状态机：0=正常 1=字符串中 2=转义。与 `tools/` 那两个同款。
    """
    out = []
    state = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if state == 0:
            if ch == '"':
                out.append(ch)
                state = 1
                i += 1
            elif text[i:i + 2] == "//":
                while i < n and text[i] != "\n":
                    i += 1
                # 换行本身留着：注释删完这一行就空了，但行号不乱
            elif text[i:i + 2] == "/*":
                i += 2
                while i + 1 < n and text[i:i + 2] != "*/":
                    if text[i] == "\n":
                        out.append("\n")
                    i += 1
                i += 2
            else:
                out.append(ch)
                i += 1
        elif state == 1:
            out.append(ch)
            if ch == "\\":
                state = 2
            elif ch == '"':
                state = 0
            i += 1
        else:
            out.append(ch)
            state = 1
            i += 1
    return "".join(out)


def loads(text):
    """读一段 JSONC 文本。坏 JSON 照旧抛 `json.JSONDecodeError`（**不吞**）。"""
    return json.loads(strip(text))


def load(fp):
    """同 `json.load`，只是先去掉注释。"""
    return loads(fp.read())
