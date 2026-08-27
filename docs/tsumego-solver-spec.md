# luciaGo · 死活题求解器 —— 设计 / 开发 / 验证 / 测试文档

> **交接说明**：本功能交给同事按现有接口与后端逻辑实现。本文档为唯一规范，包含：背景现状、接口契约（**不得变更**）、算法设计、开发步骤、验收标准与测试方法、边界与坑。

---

## 0. TL;DR（给实现者的 30 秒）

- **要做什么**：把当前 `backend/app/tsumego.py` 里**不可靠的启发式死活判定**，替换成一个**正确、可靠的 Python 死活求解器（df-pn 证明数搜索 + 准确的死活终局判定）**。
- **接口不变**：`Tsumego.solve(...)` 的方法签名与返回字典、以及 `/api/tsumego/solve`、`/api/tsumego/evaluate` 两个 HTTP 接口的输入输出契约**必须保持不变**（前端已依赖）。
- **KataGo 角色**：只用它做**候选点生成与排序（区域受限）**，**绝不用它做死活判定**（全局胜率对死活"盲"）。
- **验收金标准**：标准死活题库 + 本文第 8 节的具体用例，尤其是 `黑先杀白 / 正解 S6` 这道必须给出 `S6`。

---

## 1. 项目背景与目标

luciaGo 是一个 B/S 围棋应用，后端以 KataGo 为 AI 核心。产品要支持"**死活题**"：用户手工摆盘（或拍照）得到局面，应用给出**死活结论**（目标块活/死）+ **正解**（关键点）+ **解法主线**，并支持用户自行解题后的**验证**。

**本次目标**：实现可靠的死活题判定与求解，替换当前不可靠的启发式。

---

## 2. 当前架构与现状

```
浏览器 (Vue3 SPA)
  │  fetch /api/... (GTP坐标)
  ▼
FastAPI (backend/app/main.py)
  ├── /api/analyze        → KataGo 形势分析（胜率/目差/归属图）—— 已OK，不动
  ├── /api/tsumego/solve  → 死活题：给出正解+活/死+主线   ← 本次要改
  ├── /api/tsumego/evaluate → 死活题：验证用户某手是否达成 ← 本次要改
  └── katanago.py (KataGoEngine)  异步JSON行协议封装 —— 已OK，不动
```

**关键文件**
- `backend/app/main.py` —— FastAPI 应用，定义 `TsumegoRequest` 与两个端点。
- `backend/app/tsumego.py` —— **`Tsumego` 类（本次实现核心）**。当前是启发式：`classify`（两只封闭空区=活）、`_fight`（按目标得分贪心对杀）、`_resolve_after`（逐候选判定达成）。
- `backend/app/katago.py` —— `KataGoEngine`，提供 `await engine.analyze(initial_stones=..., initial_player=..., board_size=..., komi=..., rules=..., max_visits=..., include_ownership=..., extra={"allowMoves":[...]})`。
- 本地棋盘逻辑已用 **`sgfmill.boards.Board`**（自带提子/劫/自杀判定）。

**坐标约定（必须循用）**
- 内部坐标：`(row, col)`，**`row=0` 为顶行**（与 sgfmill、前端一致）。
- GTP 顶点：`LETTERS[col] + (size - row)`，`LETTERS = "ABCDEFGHJKLMNOPQRST"`（跳 I）。即：顶左 = `A<size>`，底左 = `A1`。
- `Tsumego.parse(vertex) -> (row,col)`、`Tsumego.gtp(row,col) -> vertex` 已实现，可复用。
- **注意**：sgfmill 的 `format_vertex` 行编号与 GTP **不一致**，不要用它；用上面的 `gtp/parse`。

---

## 3. 现状问题（为什么必须重写）

当前启发式**不可靠**，已实测失败。具体失败用例（**必须修复的目标**）：

**局面**（用户摆盘，SGF）：
```
(;GM[1]FF[4]SZ[19]AB[pnqnpopppqpr]AW[qoqpqqrr])
```
对应棋子（GTP）：黑 `Q6 R6 Q5 Q4 Q3 Q2`；白 `R5 R4 R3 S2`。
题目：**黑先杀白**（目标 = 白 `R3 R4 R5` 这一块，`S2` 是孤立白子）。

- **期望正确正解：`S6`**（白块最终被杀/死）。
- **当前实现给出：`S5`**（错误）。

**根因**（写进文档，避免同事重蹈）：
1. **全局胜率对死活"盲"**：高访问数分析显示黑棋整体胜率已 ~0.86（黑大优），黑走 `S5`/`S6` 甚至远处 `N9`，胜率都在 0.84~0.86，**局部白块死活不改变全局胜率** → 不能靠胜率判死活。
2. 现有"两只封闭空区=活"是**静态**判断，对"还没走完、尚有空间做眼"的棋块会**过早判死**。
3. 对杀用"KataGo 胜率最佳"或"简单目标得分贪心"，**不是真正最优死活着法** → 多手才见分晓的形会误判。

---

## 4. 接口契约（**不得变更**，前端已依赖）

### 4.1 HTTP 接口

**`POST /api/tsumego/solve`**

请求体（`TsumegoRequest`，见 `main.py`）：
```json
{
  "stones": [["B","Q6"],["B","R6"],["B","Q5"],["B","Q4"],["B","Q3"],["B","Q2"],
             ["W","R5"],["W","R4"],["W","R3"],["W","S2"]],
  "region": ["P4","P5","P6","...","T9"],      // GTP 顶点列表 = 题目区域
  "targetVertex": "R4",                        // 目标棋块上任意一子的 GTP 顶点
  "sideToMove": "B",                           // 先手方 "B"|"W"
  "goal": "kill",                              // "live"|"kill"
  "attemptVertex": null,
  "boardSize": 19,
  "maxVisits": 300
}
```

响应（`solve` 构造并原样返回，**字段不可少**）：
```json
{
  "target": "R4",
  "owner": "W",                // 目标棋块颜色
  "sideToMove": "B",
  "goal": "kill",
  "status": "dead",            // "alive"|"dead"|"unknown"
  "achieved": true,            // goal 是否达成：live→status=='alive'，kill→status=='dead'
  "bestMove": "S6",            // 正解点（达成目标的首手）
  "line": [{"color":"B","move":"S6"}, {"color":"W","move":"..."}],
  "winners": ["S6"]            // 可选：所有达成目标的着法
}
```
> `line` 为**正确变化线**（双方交替），前端会用它在棋盘上"演示解法"。

**`POST /api/tsumego/evaluate`**：请求体多一个 `attemptVertex`（用户落的点）。响应契约相同，但 `bestMove` = `attemptVertex`，`achieved` = "走这手是否能达成 goal"。`main.py` 会额外加 `res["attempt"] = attemptVertex`。

### 4.2 Python 内部接口（`main.py` 调用的）

```python
async def solve(
    self,
    stones: list[list[str]],     # [["B","Q6"],...]
    region: list[str],           # GTP 顶点
    target_vertex: str,          # GTP 顶点
    side_to_move: str,           # "B"|"W"
    goal: str = "live",          # "live"|"kill"
    *,
    first_move: Optional[str] = None,  # 非空=验证该手（evaluate 用）
    visits: int = 300,
    max_plies: int = 10,
    candidate_limit: int = 10,
) -> dict
```
返回字典字段：`target, owner, sideToMove, goal, status, achieved, bestMove, line`（可加 `winners`）。出错返回 `{"error": str}`（main.py 会转成 HTTP 400）。

**语义**：
- `status` 是**目标棋块**在"先手方先走、双方最优化"下的**死活结论**。
- `goal` 与 `status` 的关系决定 `achieved`（见上）。
- `first_move` 非空时：把它当作先手方第一手，判定这手之后目标块是否达成 goal（用于"验证我这手"）。

---

## 5. 技术选型结论（已调研，直接采纳，勿再纠结）

| 方案 | 结论 |
|---|---|
| 外部工具 Smargo / cameron-martin-tsumego-solver / TsumeGo(nongnu) | ✗ 或不适配任意局面求解 / CLI 只 generate / 0.1 版不完整 |
| XuanXuanGo | ⭐ 最准，但**纯 Windows GUI、无命令行**，无法接入 Web 后端 |
| study-LD-RZ（Relevance-Zone, IEEE ToG） | ⭐ 准确、无头 CGI，但 **CMake+Caffe2+Linux 容器**编译，Windows 不可行 |
| **自研 Python 死活求解器（df-pn + 准确终局）** | **✅ 唯一满足"可集成 + 免编译 + 可靠"** |

**KataGo 定位**（明确）：
- ✅ 用：**候选点生成 + 排序**（`allowMoves` 限定题目区域，见 `main.py` 中 `/api/analyze` 的 region 用法）；供"对弈 / 复盘 / 形势分析"。
- ❌ 不用：**做死活判定**（全局胜率对死活盲）。

---

## 6. 算法设计（核心）

### 6.1 总体

把目标棋块的生命/死亡归结为一个小型**博弈树搜索**：攻击方想让目标块**死**，防守方想让其**活**。用 **df-pn（深度优先证明数搜索）** 高效地判定"先手方是否达成 goal"，并给出**关键着（正解）**。

**为什么 df-pn**：死活题的搜索空间是"证明一个结论"（活/死），证明数搜索（proof-number）天然适合"先找到一个证明/反证"，比 αβ/普通 MCTS 更高效且更有针对性。

### 6.2 死活终局判定（cornerstone：必须准确）

- 一个棋块的**死活**最终判据：是否能做出**两只"真眼"**。真眼 = 对方**无法填掉**的空区。
  - **两只独立真眼 → 活**。
  - **被吃（无气/被提）→ 死**。
  - **仅一眼/假眼 → 死**（对方可填掉最后的气并提掉）。
- 需要处理：**假眼**（看似眼但可被填/气不够）、**大眼**（如刀把五、板六、盘角曲四——需要按形状细分）、**劫**、**似活似死(seki)**、**双活**。
- 终局判定要**与搜索解耦**：搜索负责探索，终局函数负责"这盘到没到定式结论（活/死）"。

### 6.3 局部化 / 区域

- 只在**题目区域（`region`）**内搜索与走子；区域外的子视为"背景/外气"，避免把搜索扩散到整盘。
- 用 `sgfmill.Board` 维护局面（提子/劫/自杀），与 KataGo 无关。
- **目标棋块**由 `targetVertex` 所在连通块确定（`Tsumego._group` 已实现）。

### 6.4 KataGo 的角色（仅辅助）

- 用 `self.engine.analyze(initial_stones=..., initial_player=side, include_ownership=True, extra={"allowMoves":[{"player":side,"moves":region,"untilDepth":1000}]})` 拿到**区域内候选点**（top 若干）作为搜索的**候选集**，并可用其给出**候选排序**（作为搜索的启发/先验，不属于判定）。
- 参考现成的 `Tsumego._region_candidates` / `_engine_best`。

### 6.5 验证用户着法（evaluate）

- `solve(..., first_move=attempt)`：把 `attempt` 当作先手方第一手，其后进入搜索，判定目标块最终状态是否达成 `goal`。**返回与 solve 一致**。

---

## 7. 详细实现规划

### 7.1 建议的文件 / 结构（可在 `tsumego.py` 内扩展，或拆分）

建议保留 `Tsumego` 类与 `solve`/`parse`/`gtp`/`_group` 等对外契约，新增/替换内部实现：

```
backend/app/tsumego.py
  class Tsumego:
      # 对外（保留签名）
      async def solve(...)                       # 入口：调 adjudicate + 求正解
      # 工具（可复用/重写）
      gtp/parse/_apply_setup/_play/_group/_exists
      # 新实现
      _find_candidates(...)                      # KataGo 区域内候选点（可选）
      _solve_dpn(state, attacker, defender, goal, ...)   # df-pn 证明数搜索
      _terminal(state, group, colour) -> 'alive'|'dead'|None   # 死活终局
      _eyes(...) / _true_eye(...)                # 更准确的眼判定
```

### 7.2 数据结构

- 用 `sgfmill.boards.Board` 表示局面（`play`/`get`/`copy`/`apply_setup`）。
- 搜索节点：`(board, 轮到谁)`；用 **Zobrist/局面哈希** 做**置换表**去重（死活搜索分支多，必须去重）。可用 `board` 的一个规范化字符串或 KataGo 的 `symHash`/`thisHash`（`engine.analyze` 返回）做 key。

### 7.3 开发步骤（建议顺序，每步可跑）

1. **先写死活终局判定** `_terminal`，并单测：两眼活、一眼死、假眼、被吃、大眼（刀把五/板六）。这是最难的，先用大量标准题校准。
2. **写 df-pn 搜索** `_solve_dpn`，能对"直三/简单眼形"求出正解与活/死。
3. **接入候选点（KataGo 辅助）**，把搜索限制在区域、用 KataGo 排序候选。
4. **接通 `solve`/`evaluate` 对外契约**，跑通 HTTP 接口。
5. **用题库 + 失败用例（S6）验收**，逐项修正。

---

## 8. 验证与验收标准（**必须全部通过**）

### 8.1 标准死活题用例（每个给"期望正解 + 期望活/死"）

| # | 题型 | 期望 |
|---|---|---|
| 1 | 直三 黑先活 | 活；正解=中点（如 `F5`） |
| 2 | 直三 白先杀 | 死；正解=中点或端点（视约定） |
| 3 | 刀把五（bulky five）| 死（无论谁先） |
| 4 | 板六（rectangular six）| 活（无外气断开时）；需按形状测 |
| 5 | 两只独立真眼 | 活 |
| 6 | 一眼被包围 | 死 |
| 7 | **本题目：黑先杀白（SGF 见第 3 节）** | **死；正解=`S6`** |
| 8 | 盘角曲四 / 劫 | 需标注"劫"或按规则处理（至少不给出错误确定结论） |
| 9 | 似活似死(seki) | 需识别并标注（不误判为活/死） |

> 题库来源：可选用公开 SGF 死活题（如 tsumego hero / goproblems 子集，注意版权），每道标注答案做回归。

### 8.2 回归：现有简单题不能回退

- 直三黑先活必须仍判 `alive` / 正确正解（当前启发式已能过，别改坏了）。

### 8.3 失败用例必须红→绿

- 用第 3 节 SGF 复现：**旧实现给 `S5`（错）→ 新实现给 `S6`（对）**。

---

## 9. 测试方法

### 9.1 运行环境（Windows，conda）

- 后端：`conda activate lucia-go`，`cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`。
- 前端（可选联调）：`cd frontend && npm run dev`，`http://localhost:5173`（代理 `/api` → `:8000`）。
- 引擎/模型已就位：`backend/engine/kataGo/katago.exe`（OpenCL）+ `models/b6c96.txt.gz`；配置 `analysis.cfg`。

### 9.2 单元测试（纯 Python，不依赖引擎）

- 针对 `_terminal` / 眼判定 / df-pn 搜索，构造小棋盘直接断言。建议用 `pytest`（若环境没有，装一下）。
- 用例：两眼活 / 一眼死 / 假眼 / 刀把五 / 板六。

### 9.3 集成测试（调用 solve HTTP）

- 用 Python `requests`/`urllib` 直接 `POST /api/tsumego/solve`，断言返回的 `status`/`bestMove`。
- 把第 3 节 SGF 转成 `stones`/`region`/`targetVertex`/`sideToMove="B"`/`goal="kill"`，断言 `bestMove == "S6"` 且 `status=="dead"`、`achieved==true`。
- 参考现有测试脚本模式（`_test.py` / `_case.py`，见 git 历史 / `docs`）。

### 9.4 端到端（UI）

- 前端摆盘 → 开始死活题 → 选目标群 → 判定（按钮「判定」）→ 应显示正解与活/死；「演示解法」应走出正确变化线；「验证我这手」对。

---

## 10. 边界与坑（务必注意）

- **性能**：死活搜索可能爆炸。必须用**置换表去重**、限制**搜索深度/区域**、用 KataGo 候选排序剪枝。设置合理 `maxVisits`（搜索辅助用）与超时。
- **劫/循环**：搜索结果若依赖劫材或出现循环，应标注"劫"或"无法确定"，**不要硬给确定结论**。
- **似活似死(seki)/双活**：需要识别；至少不应误判为"活/死"。
- **大眼形状**：刀把五、板六、盘角曲四等，需按眼形规则细分（不是"两个空区=活"这么简单）。
- **坐标**：统一用 `(row, col), row=0 顶` 与 `gtp/parse`；**别用 sgfmill 的 `format_vertex`**。
- **整数/浮点**：`sgfmill` 颜色是 `'b'/'w'`；KataGo 是 `'B'/'W'`，转换别错。
- **空局面 / 无目标 / 区域过小**：`solve` 返回 `{"error": ...}`，由 main.py 转 400，别崩。
- **不可用全局胜率判死活**：这是本需求的核心认知，写注释提醒后人。

---

## 11. 交付物清单

- [ ] `backend/app/tsumego.py` 替换为 df-pn + 准确终局实现，**保持接口契约**。
- [ ] `/api/tsumego/solve`、`/api/tsumego/evaluate` 通过第 8 节全部验收用例。
- [ ] 单元测试 + 集成测试脚本纳入 `backend/tests/`（或 `scripts/`）。
- [ ] 失败用例（黑先杀白/S6）绿。
- [ ] README / 本文档如需更新，声明"死活已接入 df-pn 求解器"。
- [ ] 提交 git，说明变更。

---

## 12. 参考（重要依据）

- 当前实现：`backend/app/tsumego.py`、`backend/app/main.py`。
- KataGo 分析引擎：`backend/engine/analysis.cfg` + `katago.py`（`allowMoves` 用法参考 `/api/analyze`）。
- 标准死活理论：两眼活 / 刀把五 / 板六 / 盘角曲四 / 劫 / seki。
- 证明数搜索：df-pn（可参考公开教材/论文实现要点，不引入重依赖）。
