# luciaGo 设计文档

## 1. 目标

一个 B/S 架构的围棋应用，后端以 **KataGo** 为 AI 核心。目标功能：

1. 摆盘 + AI 分析（最佳着手、胜率、目差、归属图）—— **MVP 已完成**
2. 死活题解题 + AI 提示
3. 死活题生成（手工摆盘 / 自对弈挖掘）
4. 拍照识别棋盘（下个迭代）
5. 研究模式（分支树 + 时间回退 + 逐节点 AI 建议）

## 2. 架构

```
┌──────────────┐   REST + (后续 WebSocket)   ┌──────────────────┐   逐行 JSON    ┌──────────────┐
│   Vue3 前端   │ ──────────────────────────▶ │  FastAPI 后端     │ ─────────────▶ │  KataGo 引擎  │
│  (SPA + SVG)  │ ◀────────────────────────── │  /api/analyze     │ ◀───────────── │ (analysis模式)│
└──────────────┘                             │  /api/health      │               └──────────────┘
                                            │  进程管理/调度      │
                                            └──────────────────┘
      拍照识别（Moku/RT-DETR ONNX）——可放前端浏览器(WASM)或后端
```

- **前端薄客户端**：只管界面与交互，真算力在服务端。
- **后端（FastAPI/Python）**：唯一接触 KataGo 的地方；管理 KataGo 进程、做分析、校验。
- **KataGo**：analysis 引擎，JSON 行协议，输出最佳着手/胜率/目差/PV/归属图。

> 技术取舍：选 Python 而非 Node/Go，因为 KataGo 上层生态最强是 Python（katrain、训练/自对弈工具链），
> 且本项目真正吃力的算法活（死活题校验/生成、进程调度）用 Python 更高效；后续拍照/OCR 用 OpenCV/ultralytics 也顺手。

## 3. 技术选型

| 层 | 选择 | 理由 |
|---|---|---|
| 前端 | Vue 3 + Vite + TypeScript | SPA，轻快；棋盘场景合适 |
| 棋盘逻辑 | `@sabaki/go-board` | 提供规则/提子/劫；`stringifyVertex`/`parseVertex` 用 GTP 格式，与 KataGo 互通 |
| 棋盘渲染 | 自绘 SVG | 需叠加箭头/标记/归属热力 |
| 后端 | Python FastAPI | async + WebSocket，能流式返回分析 |
| AI | KataGo v1.18.1，OpenCL | 4070 Ti Super；后续可切 CUDA |
| SGF | `sgfmill`（Python） | 用于后续题目/对局导入导出 |

## 4. KataGo 分析引擎要点（来自调研）

- 通讯：`katago.exe analysis -model <m> -config <cfg>`，stdin/stdout **逐行 JSON**。
- 请求字段：`id`、`moves`（`[["B","Q16"], ...]`，**必须存在**，可为 `[]`）、`initialStones`（摆盘）、
  `initialPlayer`、`boardXSize/YSize`、`komi`、`rules`、`maxVisits`、`includeOwnership`、`analysisPVLen`、`reportDuringSearchEvery`（流式）等。
- 响应：`moveInfos[]`（`move`、`winrate`、`scoreLead`、`visits`、`order`、`pv`）、`rootInfo`（胜率/目差/`currentPlayer`）、`ownership`（`size*size`，`-1`~`1`）。
- **v1.18 变更**：`moves`/`initialStones` 是 `[color, vertex]` 对；`moves` 字段必须存在。
- 模型文本格式 `.txt.gz` 与二进制 `.bin.gz`：KataGo **按扩展名**选择解析方式。

## 5. 关键技术挑战与对策

1. **KataGo 死活题会"脱先"**（觉得救小群不值而下外面）。
   → 用限定区域 / `avoidMoves` / `allowMoves`，或在题外填确定的死子/实地逼它解本地。（下个迭代）
2. **判定活/死/劫**：用高访问（数千 visits）分析 `ownership` 与胜率突变确认；剔除有第二正解的歧义题。
3. **性能/并发**：KataGo 单进程一次算一个局面，用进程池 + 队列 + 流式返回；GPU 加速。（当前单进程 MVP 够用）

## 6. 里程碑

- [x] **M0 骨架 + `/api/analyze`**：后端起 KataGo，前端摆盘 → 出最佳手 + 胜率；支持 9/13/19 路。
- [ ] **M1 死活题解题 + 提示**：`/hint`、`/verify`、区域限定防脱先、AI 引导。
- [ ] **M2 死活题生成**：摆盘 → 裁剪 + 唯一性校验 + 难度分级；自对弈挖掘。
- [ ] **M3 拍照识别**：Moku ONNX → SGF → 出题。
- [ ] **M4 研究模式**：分支树 + 时间回退 + 逐节点 AI 建议。
- [ ] **M5 产品化**：存储、进度跟踪、账号。

## 7. 坐标与符号约定

- `@sabaki/go-board` 的 `sign`：`1`=黑，`-1`=白，`0`=空；`signMap[y][x]`（y=0 为顶行）。
- `stringifyVertex([x,y])` = 列字母(跳 I) + (height - y)，即 **GTP** 坐标，与 KataGo 一致，故前后端坐标直接互通。
