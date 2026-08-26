# luciaGo · 围棋研究 / 死活题应用

一个面向围棋爱好者的 B/S 应用：用 **KataGo** 作为后端 AI 核心，提供**摆盘 + AI 分析**、**死活题解题与提示**、以及**研究模式**。目标是让用户能够：

- 手工摆盘（或拍照识别）生成局面
- 用 KataGo 实时给出**最佳着手、胜率、目差、归属图**
- 做死活题，AI 引导解题与提示

> **当前状态：MVP（0→1）已跑通。** 已实现「摆盘 + KaiGo 分析」全链路：前端摆盘 → 后端 FastAPI → KataGo 引擎 → 返回胜率/目差/最佳着/归属图。支持 9 / 13 / 19 路。
>
> 下一迭代：死活题生成、拍照识别、研究模式、死活题解题+提示。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | **Vue 3 + Vite + TypeScript**（棋盘逻辑用 `@sabaki/go-board`，自绘 SVG） |
| 后端 | **Python + FastAPI**（`/api/analyze`，CORS，WebSocket 可后续扩展） |
| AI 引擎 | **KataGo v1.18.1**（OpenCL 后端，后续可换 CUDA） |
| 模型 | b6c96（快），可换更强模型 |
| 存储 | 暂无（MVP 无持久化） |

---

## 目录结构

```
luciaGo/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI 应用 + /api/analyze + /api/health
│   │   └── katago.py      # KataGo 分析引擎异步封装（JSON 行协议）
│   ├── engine/
│   │   ├── analysis.cfg   # KataGo analysis 配置（已提交）
│   │   ├── kataGo/        # katago.exe + DLL（gitignore，需下载）
│   │   └── models/        # 神经网络模型（gitignore，需下载）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue        # 主界面：摆盘 + 分析面板
│   │   ├── api.ts         # 后端 API 客户端
│   │   ├── types.ts
│   │   └── components/GoBoard.vue   # SVG 棋盘（棋子/星位/归属/标记）
│   ├── package.json
│   └── vite.config.ts     # 开发服务器代理 /api → :8000
└── docs/DESIGN.md         # 设计文档
```

---

## 环境要求

- **conda**（Anaconda / Miniconda），已创建环境 `lucia-go`（Python 3.12）
- **Node.js**（v23 已验证）+ npm
- **KataGo 引擎** + 一个神经网络模型（见下方）

## 运行

### 1. 启动后端（FastAPI + KataGo）

```bash
# 激活 conda 环境
conda activate lucia-go

# 启动 API（默认 http://127.0.0.1:8000）
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

验证：浏览器打开 `http://127.0.0.1:8000/api/health`，应返回 `"running": true`。

### 2. 启动前端（Vue 3 + Vite）

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。开发服务器会把 `/api` 代理到后端 `:8000`。

> 若要在局域网（如手机 H5 调试）访问，已配置 Vite 监听 `0.0.0.0`，用 `http://<你的局域网IP>:5173` 打开。

---

## KataGo 引擎与模型（已 gitignore，需手动准备）

引擎二进制与模型体积较大，未提交进 git，但**已解压到本地**，直接可用：

- 引擎：`backend/engine/kataGo/katago.exe`
- 模型：`backend/engine/models/b6c96.txt.gz`
- 配置：`backend/engine/analysis.cfg`

需要重新下载时（来源）：

- **KataGo**（v1.18.1 OpenCL）:
  `https://github.com/lightvector/KataGo/releases/download/v1.18.1/katago-v1.18.1-opencl-windows-x64.zip`
- **模型**（b6c96）:
  从 `https://katagotraining.org/networks/` 找一个 `kata1-b6c96-s...-d....txt.gz` 下载到 `backend/engine/models/`。

> 说明：b6c96 是**文本格式**模型，需保留 `.txt.gz` 扩展名（KataGo 按扩展名选择解析方式）。想换更强模型（b15c192 / b18c384nbt）只需替换该文件并在 `main.py` 的 `KATAGO_MODEL` 指向它。

---

## 环境变量（可选）

后端支持以下环境变量覆盖默认值：

| 变量 | 默认 |
|---|---|
| `KATAGO_BIN` | `backend/engine/kataGo/katago.exe` |
| `KATAGO_MODEL` | `backend/engine/models/b6c96.txt.gz` |
| `KATAGO_CONFIG` | `backend/engine/analysis.cfg` |
| `BOARD_SIZE` | `19` |
| `KOMI` | `7.5` |
| `RULES` | `chinese` |
| `MAX_VISITS` | `300` |

---

## API

### `POST /api/analyze`

请求（坐标为 GTP 格式，如 `D4`、`Q16`）：

```json
{
  "stones": [["B", "Q16"], ["W", "D4"], ["B", "R4"]],
  "toPlay": "W",
  "boardSize": 19,
  "maxVisits": 300,
  "includeOwnership": true
}
```

响应：

```json
{
  "boardSize": 19,
  "toPlay": "W",
  "rootInfo": { "winrate": 0.5, "scoreLead": 0.1, "currentPlayer": "W", "visits": 300 },
  "moveInfos": [
    { "move": "D16", "winrate": 0.51, "scoreLead": 0.3, "visits": 42, "order": 0, "pv": ["D16", ...] }
  ],
  "ownership": [0.0, 0.9, ...]
}
```

`moveInfos` 已按 KataGo 排序，`[0]` 为最佳着。`ownership` 为 `size*size` 的一维数组（行主序，`-1`=白领地 ~ `1`=黑领地）。

### `GET /api/health`

返回引擎是否运行及配置信息。

---

## 下一步（planned）

- 死活题：`/api/hint`、`/api/verify`、题目区域限定（`kata-problem_analyze` / `avoidMoves` 防脱先）
- 死活题生成（手工摆盘 → 裁剪 + 唯一性校验；自对弈挖掘）
- 拍照识别（Moku / RT-DETR ONNX）
- 研究模式（分支树 + 时间回退 + 逐节点 AI 建议）
- 存储（SQLite）、进度跟踪
