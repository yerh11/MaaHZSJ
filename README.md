<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://cdn.jsdelivr.net/gh/MaaAssistantArknights/design@main/v1/icons/maa-logo_512x512.png" width="256" height="256" />
</p>

<div align="center">

# MaaHZSJ

《魂坠深境》自动跑局脚本 —— 由 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 强力驱动

</div>

让**脚本**自己跑完《魂坠深境》的整局循环：

> 主界面开局 → 走地图 → 处理沿途每个地点 / 事件 / 战斗 → 走到结局（通关或失败）
> → 收尾回主界面 → 再开下一局

全程不需要人点，也不需要人盯着。**没定过策略的分支会主动停车**并说清停在哪 ——
停车不是故障，是"这儿还没教过脚本"。

> 本项目由 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate) 模板创建，
> 已按《魂坠深境》重做：识别定义留在 `assets/resource/pipeline/*.json`，
> 循环 / 状态机写在 `script/` 下的四层结构里。

## 怎么跑

前置：MuMu 12 模拟器 + 已登录的《魂坠深境》（**登录仍是手动的**），游戏内
「自动出牌按钮」打开且**自动结束回合**，截图分辨率 **1280x720**。

```bash
cd MaaHZSJ
export PYTHONIOENCODING=utf-8        # Windows 下必须，否则中文日志会炸
python script/battle.py 噩梦9层       # 缺省难度「噩梦9层」；Ctrl-C 停
```

- 启动时游戏停在哪都行：停在**局内**就接着这一局走完；停在**局外**就回主界面开新局。
- 一局正常收尾会**自动开下一局**，一直跑。
- 想挂后台跑（推荐，日志落盘）：

  ```bash
  python -u script/battle.py 噩梦9层 > debug/run_$(date +%m%d_%H%M).log 2>&1 &
  ```

- 只想跑一局 / 接着当前这一局跑（不重启、不开新局）：

  ```bash
  python debug/play.py          # 接着跑（默认最多 400 步）
  python debug/play.py 40       # 最多 40 步
  ```

## 文档

| 想了解 | 看哪 |
|---|---|
| 怎么起、它自己会做哪些决定、什么时候会停、停了怎么办、想改哪条规则 | [`docs/zh_cn/使用文档.md`](docs/zh_cn/使用文档.md) |
| 脚本内部怎么搭的（认屏表 / 四层结构 / 每层能依赖谁 / `handle()` 要守哪四条） | [`docs/zh_cn/架构与流程图.md`](docs/zh_cn/架构与流程图.md) |
| 工作区总览、已确认的运行环境、开发约定与已知的洞 | 工作区根目录 `CLAUDE.md` |
| 版本变更记录 | [`CHANGELOG.md`](CHANGELOG.md) |
| 模板自带的开发 / FAQ / PR 规范 | [`docs/zh_cn/develop/`](docs/zh_cn/develop/) |

**改完代码请跑一遍自检**（`使用文档.md` 第八节有完整清单）：

```bash
export PYTHONIOENCODING=utf-8
python -m py_compile script/*.py script/*/*.py tools/*.py
python tools/check_strings.py      # 脚本里没写裸游戏字 / 没死名字 / 节点名都对得上
python tools/check_screens.py      # 认屏表顺序没被改坏 / handle 契约没破
python tools/validate_schema.py --schema-dir deps/tools \
    --resource-dirs assets/resource --interface-files assets/interface.json
```

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动，
由 **[MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate)** 模板创建。
