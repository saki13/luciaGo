<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import GoBoard from './components/GoBoard.vue'
import SabakiBoard from '@sabaki/go-board'
import { analyze, health, solveTsumego, evaluateTsumego } from './api'
import type { TsumegoResult } from './api'
import type { AnalyzeResult, Color, Sign } from './types'

const LETTERS = 'ABCDEFGHJKLMNOPQRST'
const REGION_MARGIN = 2

function vToGtp(x: number, y: number, size: number): string {
  return LETTERS[x] + (size - y)
}
function gtpToV(gtp: string, size: number): [number, number] {
  const m = /^([A-T])(\d+)$/i.exec(gtp)
  if (!m) return [-1, -1]
  const x = LETTERS.indexOf(m[1].toUpperCase())
  const y = size - parseInt(m[2], 10)
  return [x, y]
}
function isValidVertex(v: [number, number], size: number): boolean {
  return v[0] >= 0 && v[0] < size && v[1] >= 0 && v[1] < size
}
function makeGrid(n: number): Sign[][] {
  return Array.from({ length: n }, () => Array(n).fill(0))
}
interface Rect { x0: number; y0: number; x1: number; y1: number }

// ---- board state ----
const mode = ref<'edit' | 'play'>('edit')
const size = ref(19)
const toPlay = ref<Sign>(1)
let board: SabakiBoard = SabakiBoard.fromDimensions(19, 19)

const grid = reactive<Sign[][]>(makeGrid(19))
const captures = reactive({ black: 0, white: 0 })
const history: { grid: Sign[][]; black: number; white: number }[] = []

const analysis = ref<AnalyzeResult | null>(null)
const loading = ref(false)
const solving = ref(false)
const error = ref('')
const showOwnership = ref(false)
const serverUp = ref<boolean | null>(null)

// ---- tsumego state ----
const tsumego = ref(false)
const regionRect = ref<Rect | null>(null)

// ---- tsumego adjudication state ----
const selTarget = ref(false)
const targetVertex = ref<string | null>(null)
const tsumegoGoal = ref<'live' | 'kill'>('live')
const tsumegoSide = ref<Color>('B')
const tsumegoResult = ref<TsumegoResult | null>(null)
const lastUserMove = ref<string | null>(null)
const adjudicating = ref(false)
const originalGrid = ref<Sign[][] | null>(null)

function syncGrid() {
  const sm = board.signMap
  for (let y = 0; y < size.value; y++) {
    for (let x = 0; x < size.value; x++) grid[y][x] = sm[y]?.[x] ?? 0
  }
}
function syncCaptures() {
  captures.black = board.getCaptures(1)
  captures.white = board.getCaptures(-1)
}
function resetBoard() {
  board = SabakiBoard.fromDimensions(size.value, size.value)
  const g = makeGrid(size.value)
  for (let y = 0; y < size.value; y++) grid[y] = g[y]
  grid.length = size.value
  captures.black = 0
  captures.white = 0
  history.length = 0
  analysis.value = null
  error.value = ''
  regionRect.value = null
  tsumego.value = false
  targetVertex.value = null
  tsumegoResult.value = null
  selTarget.value = false
  lastUserMove.value = null
}
function changeSize(n: number) {
  size.value = n
  board = SabakiBoard.fromDimensions(n, n)
  grid.length = 0
  const g = makeGrid(n)
  for (let y = 0; y < n; y++) grid.push(g[y])
  captures.black = 0
  captures.white = 0
  history.length = 0
  analysis.value = null
  error.value = ''
  regionRect.value = null
  tsumego.value = false
  targetVertex.value = null
  tsumegoResult.value = null
  selTarget.value = false
  lastUserMove.value = null
}
function pushHistory() {
  history.push({ grid: grid.map((r) => [...r]), black: captures.black, white: captures.white })
  if (history.length > 60) history.shift()
}
function undo() {
  const h = history.pop()
  if (!h) return
  board = new SabakiBoard(h.grid.map((r) => [...r]))
  for (let y = 0; y < size.value; y++) for (let x = 0; x < size.value; x++) grid[y][x] = h.grid[y][x]
  captures.black = h.black
  captures.white = h.white
  analysis.value = null
  error.value = ''
}
function toggleColor(c: Color) {
  toPlay.value = c === 'B' ? 1 : -1
}

// ---- region (problem area) ----
function stonesOnBoard(): { x: number; y: number }[] {
  const out: { x: number; y: number }[] = []
  for (let y = 0; y < size.value; y++)
    for (let x = 0; x < size.value; x++) if (grid[y][x] !== 0) out.push({ x, y })
  return out
}
function computeRegion(stones: { x: number; y: number }[]): Rect | null {
  if (stones.length === 0) return null
  let minX = size.value, minY = size.value, maxX = 0, maxY = 0
  for (const s of stones) {
    minX = Math.min(minX, s.x); minY = Math.min(minY, s.y)
    maxX = Math.max(maxX, s.x); maxY = Math.max(maxY, s.y)
  }
  return {
    x0: Math.max(0, minX - REGION_MARGIN),
    y0: Math.max(0, minY - REGION_MARGIN),
    x1: Math.min(size.value - 1, maxX + REGION_MARGIN),
    y1: Math.min(size.value - 1, maxY + REGION_MARGIN),
  }
}
function regionVertices(r: Rect | null): string[] {
  if (!r) return []
  const v: string[] = []
  for (let y = r.y0; y <= r.y1; y++) for (let x = r.x0; x <= r.x1; x++) v.push(vToGtp(x, y, size.value))
  return v
}
function currentRegion(): string[] {
  return tsumego.value ? regionVertices(regionRect.value) : []
}

function startTsumego() {
  const stones = stonesOnBoard()
  if (stones.length === 0) {
    error.value = '请先在棋盘摆好死活题局面'
    return
  }
  regionRect.value = computeRegion(stones)
  originalGrid.value = grid.map((r) => [...r])
  tsumego.value = true
  mode.value = 'play'
  // 先手方 default to the colour of the side with fewer stones (the attacker/problem) —
  // fall back to Black if tied. The user can change it.
  let b = 0, w = 0
  for (let y = 0; y < size.value; y++) for (let x = 0; x < size.value; x++) {
    if (grid[y][x] === 1) b++
    else if (grid[y][x] === -1) w++
  }
  tsumegoSide.value = b <= w ? 'B' : 'W'
  toPlay.value = tsumegoSide.value === 'B' ? 1 : -1
  error.value = ''
  tsumegoResult.value = null
  lastUserMove.value = null
}

// Set who moves first (先手方) for the tsumego.
function setSide(s: Color) {
  tsumegoSide.value = s
  toPlay.value = s === 'B' ? 1 : -1
}

function resetToOriginal() {
  if (!originalGrid.value) return
  const g = originalGrid.value
  for (let y = 0; y < size.value; y++) for (let x = 0; x < size.value; x++) grid[y][x] = g[y]?.[x] ?? 0
  board = new SabakiBoard(g.map((r) => [...r]))
  captures.black = 0
  captures.white = 0
  history.length = 0
  tsumegoResult.value = null
  lastUserMove.value = null
  targetVertex.value = null
  toPlay.value = tsumegoSide.value === 'B' ? 1 : -1
  analysis.value = null
  error.value = ''
}

// ---- tsumego adjudication ----
function activateTargetMode() {
  if (!tsumego.value) {
    error.value = '请先“开始死活题”'
    return
  }
  selTarget.value = true
  error.value = '点击目标棋块上的一块棋子'
}

function tsumegoPayload(attempt?: string) {
  return {
    stones: stonesPayload(),
    region: currentRegion(),
    targetVertex: targetVertex.value!,
    sideToMove: tsumegoSide.value,
    goal: tsumegoGoal.value,
    attemptVertex: attempt,
    boardSize: size.value,
    maxVisits: 300,
  }
}

async function adjudicateNow() {
  if (!targetVertex.value) {
    error.value = '请先选择目标群'
    return
  }
  adjudicating.value = true
  error.value = ''
  try {
    tsumegoResult.value = await solveTsumego(tsumegoPayload())
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    adjudicating.value = false
  }
}

async function runVerify() {
  if (!targetVertex.value || !lastUserMove.value) {
    error.value = '请先选择目标群，再落一手'
    return
  }
  adjudicating.value = true
  error.value = ''
  try {
    tsumegoResult.value = await evaluateTsumego(tsumegoPayload(lastUserMove.value))
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    adjudicating.value = false
  }
}

// Play a solution line (the correct variation) onto the board, one move at a time.
async function playLine(line: { color: Color; move: string }[]) {
  loading.value = true
  solving.value = true
  error.value = ''
  try {
    for (const m of line) {
      const [x, y] = gtpToV(m.move, size.value)
      if (!isValidVertex([x, y], size.value)) break
      if ((grid[y]?.[x] ?? 0) !== 0) break
      const sign = m.color === 'B' ? 1 : -1
      try {
        board = board.makeMove(sign, [x, y], { preventSuicide: true, preventKo: true, preventOverwrite: true })
      } catch {
        break
      }
      syncGrid()
      syncCaptures()
      toPlay.value = m.color === 'B' ? -1 : 1
      await new Promise((r) => setTimeout(r, 420))
    }
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
    solving.value = false
  }
}

// AI demonstrates the correct solution: reset to the original position, then play the line.
async function aiPlay() {
  if (!tsumego.value) {
    error.value = '请先“开始死活题”'
    return
  }
  if (!tsumegoResult.value?.line?.length) {
    await adjudicateNow()
  }
  const line = tsumegoResult.value?.line
  if (!line?.length) {
    error.value = '未找到正解，无法演示'
    return
  }
  resetToOriginal()
  await playLine(line)
}

// ---- interaction ----
function onCellClick({ x, y }: { x: number; y: number }) {
  error.value = ''

  // Target-selection mode: clicking a stone picks the target group.
  if (selTarget.value) {
    if ((grid[y]?.[x] ?? 0) !== 0) {
      targetVertex.value = vToGtp(x, y, size.value)
      selTarget.value = false
      adjudicateNow()
    }
    return
  }

  if (mode.value === 'edit') {
    pushHistory()
    const cur = board.get([x, y]) || 0
    if (cur === 0) board.set([x, y], toPlay.value)
    else board.set([x, y], 0)
    syncGrid()
    analysis.value = null
    return
  }

  // play mode with rules (capture / ko / suicide) — 对局 or 死活题
  const sign = toPlay.value
  pushHistory()
  try {
    const next = board.makeMove(sign, [x, y], {
      preventSuicide: true,
      preventKo: true,
      preventOverwrite: true,
    })
    board = next
    syncGrid()
    syncCaptures()
    toPlay.value = sign === 1 ? -1 : 1
    lastUserMove.value = vToGtp(x, y, size.value)
    analysis.value = null
  } catch (e: any) {
    history.pop()
    error.value = e?.message || '禁着'
  }
}

function stonesPayload(): [Color, string][] {
  const out: [Color, string][] = []
  for (let y = 0; y < size.value; y++) {
    for (let x = 0; x < size.value; x++) {
      const s = grid[y][x]
      if (s !== 0) out.push([s === 1 ? 'B' : 'W', vToGtp(x, y, size.value)])
    }
  }
  return out
}

async function runAnalyze(visits = 300) {
  error.value = ''
  loading.value = true
  try {
    const toPlayColor: Color = toPlay.value === 1 ? 'B' : 'W'
    analysis.value = await analyze({
      stones: stonesPayload(),
      toPlay: toPlayColor,
      boardSize: size.value,
      maxVisits: visits,
      includeOwnership: true,
      region: currentRegion(),
    })
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function checkHealth() {
  try {
    const h = await health()
    serverUp.value = !!h.running
  } catch {
    serverUp.value = false
  }
}
checkHealth()

function playBestMove() {
  const mi = analysis.value?.moveInfos?.[0]
  if (!mi) return
  const [x, y] = gtpToV(mi.move, size.value)
  if (!isValidVertex([x, y], size.value)) return
  mode.value = 'play'
  onCellClick({ x, y })
}
const markers = computed(() => {
  // In tsumego mode, markers come from the adjudication solution, not global winrate.
  if (tsumego.value && tsumegoResult.value?.line?.length) {
    const res: { x: number; y: number; label: string; kind: 'best' | 'move' }[] = []
    tsumegoResult.value.line.forEach((m, i) => {
      const v = gtpToV(m.move, size.value)
      if (!isValidVertex(v, size.value)) return
      res.push({ x: v[0], y: v[1], label: i === 0 ? '正解' : String(i), kind: i === 0 ? 'best' : 'move' })
    })
    return res
  }
  if (!analysis.value) return []
  const res: { x: number; y: number; label: string; kind: 'best' | 'move' }[] = []
  const top = analysis.value.moveInfos.slice(0, 5)
  top.forEach((m, i) => {
    const v = gtpToV(m.move, size.value)
    if (!isValidVertex(v, size.value)) return
    res.push({ x: v[0], y: v[1], label: `${Math.round(m.winrate * 100)}%`, kind: i === 0 ? 'best' : 'move' })
  })
  return res
})

const rootInfo = computed(() => analysis.value?.rootInfo)
const winratePct = computed(() => (rootInfo.value ? `${(rootInfo.value.winrate * 100).toFixed(1)}%` : '—'))

const targetXY = computed(() => {
  if (!targetVertex.value || !tsumego.value) return null
  const v = gtpToV(targetVertex.value, size.value)
  return isValidVertex(v, size.value) ? { x: v[0], y: v[1] } : null
})

// Flood-fill the whole target group (connected same-colour stones) for highlighting.
const targetGroup = computed<{ x: number; y: number }[] | null>(() => {
  if (!targetVertex.value || !tsumego.value) return null
  const start = gtpToV(targetVertex.value, size.value)
  if (!isValidVertex(start, size.value)) return null
  const colour = (grid[start[1]]?.[start[0]] ?? 0) as Sign
  if (colour === 0) return null
  const n = size.value
  const seen = new Set<number>()
  const stack: [number, number][] = [start]
  const out: { x: number; y: number }[] = []
  while (stack.length) {
    const [x, y] = stack.pop()!
    const k = y * n + x
    if (seen.has(k)) continue
    seen.add(k)
    out.push({ x, y })
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
      const nx = x + dx, ny = y + dy
      if (nx >= 0 && nx < n && ny >= 0 && ny < n && (grid[ny]?.[nx] ?? 0) === colour && !seen.has(ny * n + nx)) {
        stack.push([nx, ny])
      }
    }
  }
  return out
})
</script>

<template>
  <div class="layout">
    <header class="bar">
      <div class="brand">luciaGo · 围棋研究</div>
      <div class="health" :class="{ ok: serverUp, bad: serverUp === false }">
        {{ serverUp === null ? '检测引擎...' : serverUp ? 'KataGo 就绪' : 'KataGo 未连接' }}
      </div>
    </header>

    <div class="body">
      <aside class="side">
        <section>
          <h2>模式</h2>
          <div class="btns">
            <button :class="{ active: mode === 'edit' }" @click="mode = 'edit'">摆盘</button>
            <button :class="{ active: mode === 'play' }" @click="mode = 'play'">对局</button>
          </div>
        </section>

        <section :class="{ ts: tsumego }">
          <h2>死活题</h2>
          <button class="primary" @click="startTsumego">开始死活题</button>
          <div v-if="tsumego" class="row">
            <button @click="aiPlay()" :disabled="loading || solving">演示解法</button>
            <button @click="resetToOriginal" :disabled="!originalGrid">重置到原题</button>
          </div>
          <p class="tip" v-if="tsumego">
            红框 = 题目区域。先选目标群→判定看正解；「演示解法」从原题走出正确变化；「重置到原题」回到开始。
          </p>
        </section>

        <section :class="{ ts: tsumego }" v-if="tsumego">
          <h2>死活判定</h2>
          <div class="row">
            <span>先手：</span>
            <button :class="{ active: tsumegoSide === 'B' }" @click="setSide('B')">黑先</button>
            <button :class="{ active: tsumegoSide === 'W' }" @click="setSide('W')">白先</button>
            <span>目标：</span>
            <button :class="{ active: tsumegoGoal === 'live' }" @click="tsumegoGoal = 'live'">活</button>
            <button :class="{ active: tsumegoGoal === 'kill' }" @click="tsumegoGoal = 'kill'">杀</button>
          </div>
          <div class="row">
            <button :class="{ active: selTarget }" @click="activateTargetMode">
              {{ targetVertex ? '目标已选' : '选目标群' }}
            </button>
            <button class="primary" @click="adjudicateNow" :disabled="adjudicating">
              {{ adjudicating ? '判定中…' : '判定' }}
            </button>
            <button @click="runVerify" :disabled="adjudicating">验证</button>
          </div>
          <div v-if="tsumegoResult" class="adjud">
            <div class="badge" :class="tsumegoResult.status">
              目标群：{{ tsumegoResult.status === 'alive' ? '活' : '死' }}
            </div>
            <div class="adjud-line" v-if="tsumegoResult.bestMove">
              正解：<b>{{ tsumegoResult.bestMove }}</b>
              <span :class="tsumegoResult.achieved ? 'ok' : 'no'">
                {{ tsumegoResult.achieved ? '达成' : '未达成' }}
              </span>
            </div>
          </div>
        </section>

        <section>
          <h2>棋盘</h2>
          <div class="btns">
            <button v-for="n in [9, 13, 19]" :key="n" :class="{ active: size === n }" @click="changeSize(n)">{{ n }}路</button>
          </div>
          <div class="row">
            <span>执子：</span>
            <button :class="{ active: toPlay === 1 }" @click="toggleColor('B')">黑</button>
            <button :class="{ active: toPlay === -1 }" @click="toggleColor('W')">白</button>
          </div>
          <div class="row">
            <button @click="undo" :disabled="history.length === 0">撤销</button>
            <button @click="resetBoard">清空</button>
          </div>
          <div class="caps"><span>提子：黑 {{ captures.black }}</span><span>白 {{ captures.white }}</span></div>
        </section>

        <section>
          <h2>分析</h2>
          <button class="primary" @click="runAnalyze(300)" :disabled="loading">
            {{ loading && !solving ? '分析中…' : '调用 KataGo 分析' }}
          </button>
          <label class="row"><input type="checkbox" v-model="showOwnership" /> 显示归属图</label>
          <p v-if="error" class="err">{{ error }}</p>
          <div v-if="rootInfo" class="result">
            <div class="kpi"><span>胜率</span><b>{{ winratePct }}</b></div>
            <div class="kpi"><span>目差</span><b>{{ rootInfo.scoreLead.toFixed(1) }}</b></div>
            <div class="kpi"><span>轮走</span><b>{{ rootInfo.currentPlayer === 'B' ? '黑' : '白' }}</b></div>
          </div>
        </section>
      </aside>

      <main class="board-wrap">
        <GoBoard
          :size="size"
          :signMap="grid"
          :markers="markers"
          :ownership="showOwnership ? analysis?.ownership ?? null : null"
          :region-rect="tsumego ? regionRect : null"
          :target-xy="targetXY"
          :target-group="targetGroup"
          @cell-click="onCellClick"
        />
      </main>

      <aside class="side">
        <section v-if="tsumego">
          <h2>解法主线</h2>
          <div v-if="tsumegoResult?.line?.length" class="pv">
            <div class="pv-best">
              正解：<b>{{ tsumegoResult.bestMove }}</b>
              <span class="wr">{{ tsumegoResult.status === 'alive' ? '活' : '死' }}</span>
            </div>
            <div class="pv-line">{{ tsumegoResult.line.map(m => (m.color === 'B' ? '黑' : '白') + '·' + m.move).join('  ') }}</div>
          </div>
          <div v-else class="empty">先选目标群 → 判定</div>
        </section>

        <section v-if="!tsumego">
          <h2>推荐着法</h2>
          <div v-if="!rootInfo" class="empty">摆盘后点击分析</div>
          <ul v-else class="moves">
            <li v-for="(m, i) in analysis!.moveInfos.slice(0, 5)" :key="i" :class="{ best: i === 0 }" @click="i === 0 && playBestMove()">
              <span class="coord">{{ m.move }}</span>
              <span class="wr">{{ (m.winrate * 100).toFixed(1) }}%</span>
              <span class="sc">{{ m.scoreLead >= 0 ? '+' : '' }}{{ m.scoreLead.toFixed(1) }}</span>
              <span class="vis">{{ m.visits }}</span>
            </li>
          </ul>
          <p v-if="rootInfo" class="hint">点击第一条＝落最佳着。</p>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.layout { display: flex; flex-direction: column; height: 100%; }
.bar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #2b2b2b; color: #f4ead7; }
.brand { font-weight: 700; font-size: 16px; }
.health { font-size: 12px; opacity: 0.8; }
.health.ok { color: #7ce38b; }
.health.bad { color: #ff8a8a; }
.body { display: flex; gap: 16px; padding: 16px; align-items: flex-start; flex: 1; }
.side { width: 250px; display: flex; flex-direction: column; gap: 16px; }
.side section { background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.side section.ts { border: 1px solid rgba(220,40,90,0.4); }
.side h2 { margin: 0 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #777; }
.btns, .row { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; }
button { padding: 6px 12px; border: 1px solid #ccc; border-radius: 6px; background: #fafafa; cursor: pointer; font-size: 13px; }
button.active { background: #e6f0d8; border-color: #8fbf5f; color: #2f5d1a; }
button.primary { width: 100%; background: #4a7c3f; color: #fff; border: none; font-weight: 600; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.board-wrap { flex: 1; display: flex; justify-content: center; }
.board-wrap > :deep(svg) { width: min(86vh, 100%); }
.tip { font-size: 12px; color: #888; margin: 0; }
.caps { display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: #555; }
.err { color: #c0392b; font-size: 12px; }
.result { display: flex; gap: 10px; margin-top: 12px; }
.kpi { flex: 1; text-align: center; background: #f4f4f4; border-radius: 8px; padding: 8px 4px; }
.kpi span { display: block; font-size: 11px; color: #888; }
.kpi b { font-size: 16px; }
.moves { list-style: none; margin: 0; padding: 0; }
.moves li { display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 6px; cursor: default; }
.moves li.best { background: #e6f0d8; cursor: pointer; }
.moves li .coord { font-weight: 700; width: 40px; }
.moves li .wr { flex: 1; }
.moves li .sc { color: #555; width: 48px; text-align: right; }
.moves li .vis { color: #999; font-size: 11px; }
.empty { color: #999; font-size: 13px; }
.hint { font-size: 11px; color: #888; margin-top: 8px; }
.pv { font-size: 13px; }
.pv-best { font-weight: 700; display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.pv-best .wr { font-weight: 600; color: #2f5d1a; }
.pv-line { color: #555; line-height: 1.5; word-break: break-all; }
.adjud { margin-top: 10px; }
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 13px;
  color: #fff;
}
.badge.alive { background: #2e9e4f; }
.badge.dead { background: #c0392b; }
.adjud-line { margin-top: 8px; font-size: 14px; }
.adjud-line .ok { color: #2e9e4f; font-weight: 700; margin-left: 6px; }
.adjud-line .no { color: #c0392b; font-weight: 700; margin-left: 6px; }
.adjud-variation { margin-top: 6px; color: #555; font-size: 12px; line-height: 1.5; }
</style>
