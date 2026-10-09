# 模板图怎么放

pipeline 里 `"template"` 字段写的是**相对本目录的路径**（引擎把 `<resource>/image` 当根，
见 MaaFramework `source/MaaFramework/Resource/TemplateResMgr.cpp`），所以可以带子目录：

```jsonc
{ "recognition": "TemplateMatch", "template": "地图/map_marker.png", ... }
```

**这里的文件夹是按界面分的**，一个文件夹对齐一个 pipeline 文件，改某个界面只翻一个目录。
中文路径实测没问题（`地点/生命魔药.png` 跑过回归，score 与挪动前一字不差）。

## 目录对照

| 文件夹 | 对应 pipeline | 图 |
|---|---|---|
| `通用/` | `通用.json` | `btn_gear.png`（右上角齿轮）`btn_menu.png`（人形十字） |
| `启动/` | `启动.json` | `popup_close.png`（评价弹窗的红 X） |
| `暂停/` | `暂停.json` | `btn_pause_close.png`（蓝 X） |
| `地图/` | `地图.json` | `map_marker.png`（可前往箭头） |
| `地点/` | `地点.json` | `btn_amulet_close.png` + 5 张护符 |
| `锻造/` | `锻造.json` | `btn_forge_back.png`（返回箭头）`无畏斧.png`（升变图鉴里的斧头卡） |
| `仪式/` | `仪式.json` | `btn_amulet.png`（护符配置页签） |
| `empty.png` | — | 模板自带的占位图，**唯一进了 git 的一张，别动** |

## `地点/` 那 5 张护符：文件名是游戏里的真名

| 文件 | 节点名 | 印的号 / 槽位中心 | 判据帧 |
|---|---|---|---|
| `冲锋纹印.png` | `护符-冲锋纹印` | 1 / (777,301) | `op/06_10_amulet1.png` |
| `源力宝石.png` | `护符-源力宝石` | 2 / (829,417) | `_probe_白水晶.png` |
| `生命魔药.png` | `护符-生命魔药` | 3 / (948,505) | `_amulet_toggle.png` |
| `切结臂环.png` | `护符-切结臂环` | 4 / (1035,432) | `_amulet_4红心.png` |
| `仪式钉.png` | `护符-仪式钉` | 5 / (1079,299) | `_amulet_pick.png` |

判据是**详情面板的大图标**：那五张存档帧里，面板上放大的图案就是被点中的那个候选，
同一个图案在它的槽位上带着金色高亮圈。逐张亲眼看过，不是靠文件名推的
（文件名会骗人 —— `_amulet_2blades` 那类名字是 2026-10-01 之前的临时叫法）。

**这 5 个节点是停用的**，只当坐标参考和来历记录，流程走
`script/nodes/amulet.py` 的写死坐标。原因见 `地点.json` 里那段注释。

`锻造/无畏斧.png` 同理：卡名核自 `op/14.png`（那帧是「卡牌升变」的两段式对比屏，
土黄斧头的名字栏写着「无畏斧+」，`+` 是等级标记不是名字的一部分）。

## 2026-10-01 删掉的那一批（`_未接线/` 32 张）

原来有个 `_未接线/` 文件夹收着 32 张零引用的图。**已经连文件夹一起删了**——留着会误导：
看着像"模板素材"，其实它们对应的按钮/图早就改走 OCR 了。

- **4 张按钮**：`btn_leave`（离开地点）`btn_accept`（接受）`btn_descend`（坠入深境）
  `btn_abandon`（放弃此轮游戏）。这四个按钮**每局都在点**，但认它们的是
  `祭坛.json` / `仪式.json` / `暂停.json` 里那几条 OCR 节点，模板是多余的。
- **28 张难度轮盘**：`diff_*.png` / `difflab_*.png`。轮盘走 OCR
  （`script/core/auto.py` 的 `current_difficulty()` 只对轮盘正中那一小块 OCR）；
  这些图本来就分不出「噩梦3层」和「噩梦9层」——图标字形相同，模板互相 0.93+。

原始整屏帧都还在 `debug/screenshots/`（当时的裁图脚本是 `debug/record_diff*.py`），
真要恢复就照帧重裁。**别把它们放回 `image/`，除非真的接线。**

## 加新图放哪

按**它出现在哪个界面**放，跟已经在那儿的图放一起。
**别给"已经在用 OCR 认"的按钮补模板图**（判据见上节）——那只会多出一张没人引用的图。
放完记得在对应 pipeline 的 `template` 里带上文件夹名。

> 本文件在 `image/` 里，但引擎只在有人把 `template` 指向**整个文件夹**时才会递归加载它、
> 对 `.md` 报一条 `Failed to load image`（不致命，会 `continue`）。现在没有任何节点这么写。
