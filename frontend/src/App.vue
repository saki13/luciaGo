<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import GoBoard from './components/GoBoard.vue'
import SabakiBoard from '@sabaki/go-board'
import { analyze, health } from './api'
import type { AnalyzeResult, Color, Sign } from './types'

const LETTERS = 'ABCDEFGHJKLMNOPQRST'

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

// ---- board state (source of truth = SabakiBoard) ----
const mode = ref<'edit' | 'play'>('edit')
const size = ref(19)
const toPlay = ref<Sign>(1) // 1 = black, -1 = white
let board: SabakiBoard = SabakiBoard.fromDimensions(19, 19)

const grid = reactive<Sign[][]>(makeGrid(19))
const captures = reactive({ black: 0, white: 0 })
const history: { grid: Sign[][]; black: number; white: number }[] = []

const analysis = ref<AnalyzeResult | null>(null)
const loading = ref(false)
const error = ref('')
const showOwnership = ref(false)
const serverUp = ref<boolean | null>(null)

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
}

function pushHistory() {
  history.push({ grid: grid.map((r) => [...r]), black: captures.black, white: captures.white })
  if (history.length > 60) history.shift()
}

function undo() {
  const h = history.pop()
  if (!h) return
  board = new SabakiBoard(h.grid.map((r) => [...r]))
  for (let y = 0; y < size.value; y++) {
    for (let x = 0; x < size.value; x++) grid[y][x] = h.grid[y][x]
  }
  captures.black = h.black
  captures.white = h.white
  analysis.value = null
  error.value = ''
}

function toggleColor(c: Color) {
  toPlay.value = c === 'B' ? 1 : -1
}

function onCellClick({ x, y }: { x: number; y: number }) {
  error.value = ''
  if (mode.value === 'edit') {
    pushHistory()
    const cur = board.get([x, y]) || 0
    if (cur === 0) board.set([x, y], toPlay.value)
    else board.set([x, y], 0)
    syncGrid()
    analysis.value = null
    return
  }

  // play mode: apply Go rules (capture / ko / suicide)
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
    analysis.value = null
  } catch (e: any) {
    history.pop() // discard the pushed state on illegal move
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

async function runAnalyze() {
  error.value = ''
  loading.value = true
  try {
    const toPlayColor: Color = toPlay.value === 1 ? 'B' : 'W'
    analysis.value = await analyze({
      stones: stonesPayload(),
      toPlay: toPlayColor,
      boardSize: size.value,
      maxVisits: 300,
      includeOwnership: true,
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
  if (!analysis.value) return []
  const res: { x: number; y: number; label: string; kind: 'best' | 'move' }[] = []
  const top = analysis.value.moveInfos.slice(0, 5)
  top.forEach((m, i) => {
    const v = gtpToV(m.move, size.value)
    if (!isValidVertex(v, size.value)) return
    res.push({
      x: v[0],
      y: v[1],
      label: `${Math.round(m.winrate * 100)}%`,
      kind: i === 0 ? 'best' : 'move',
    })
  })
  return res
})

const rootInfo = computed(() => analysis.value?.rootInfo)
const winratePct = computed(() =>
  rootInfo.value ? `${(rootInfo.value.winrate * 100).toFixed(1)}%` : '—'
)
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
            <button :class="{ active: mode === 'play' }" @click="mode = 'play'">对局(含规则)</button>
          </div>
          <p class="tip">
            {{ mode === 'edit' ? '左键放子 / 再点删子（自由摆）' : '按黑白轮走，自动提子、禁自杀与劫' }}
          </p>
        </section>

        <section>
          <h2>棋盘</h2>
          <div class="btns">
            <button v-for="n in [9, 13, 19]" :key="n" :class="{ active: size === n }" @click="changeSize(n)">
              {{ n }}路
            </button>
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
          <div class="caps">
            <span>提子：黑 {{ captures.black }}</span>
            <span>白 {{ captures.white }}</span>
          </div>
        </section>

        <section>
          <h2>分析</h2>
          <button class="primary" @click="runAnalyze" :disabled="loading">
            {{ loading ? '分析中…' : '调用 KataGo 分析' }}
          </button>
          <label class="row">
            <input type="checkbox" v-model="showOwnership" /> 显示归属图
          </label>
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
          @cell-click="onCellClick"
        />
      </main>

      <aside class="side">
        <section>
          <h2>推荐着法</h2>
          <div v-if="!rootInfo" class="empty">摆盘后点击分析</div>
          <ul v-else class="moves">
            <li
              v-for="(m, i) in analysis!.moveInfos.slice(0, 5)"
              :key="i"
              :class="{ best: i === 0 }"
              @click="i === 0 && playBestMove()"
            >
              <span class="coord">{{ m.move }}</span>
              <span class="wr">{{ (m.winrate * 100).toFixed(1) }}%</span>
              <span class="sc">{{ m.scoreLead >= 0 ? '+' : '' }}{{ m.scoreLead.toFixed(1) }}</span>
              <span class="vis">{{ m.visits }}</span>
            </li>
          </ul>
          <p v-if="rootInfo" class="hint">点击第一条＝自动切到对局模式并落最佳着。</p>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #2b2b2b;
  color: #f4ead7;
}
.brand {
  font-weight: 700;
  font-size: 16px;
}
.health {
  font-size: 12px;
  opacity: 0.8;
}
.health.ok { color: #7ce38b; }
.health.bad { color: #ff8a8a; }
.body {
  display: flex;
  gap: 16px;
  padding: 16px;
  align-items: flex-start;
  flex: 1;
}
.side {
  width: 240px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.side section {
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.side h2 {
  margin: 0 0 10px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #777;
}
.btns,
.row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}
button {
  padding: 6px 12px;
  border: 1px solid #ccc;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
  font-size: 13px;
}
button.active {
  background: #e6f0d8;
  border-color: #8fbf5f;
  color: #2f5d1a;
}
button.primary {
  width: 100%;
  background: #4a7c3f;
  color: #fff;
  border: none;
  font-weight: 600;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.board-wrap {
  flex: 1;
  display: flex;
  justify-content: center;
}
.board-wrap > :deep(svg) {
  width: min(86vh, 100%);
}
.tip {
  font-size: 12px;
  color: #888;
  margin: 0;
}
.caps {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: #555;
}
.err {
  color: #c0392b;
  font-size: 12px;
}
.result {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
.kpi {
  flex: 1;
  text-align: center;
  background: #f4f4f4;
  border-radius: 8px;
  padding: 8px 4px;
}
.kpi span {
  display: block;
  font-size: 11px;
  color: #888;
}
.kpi b {
  font-size: 16px;
}
.moves {
  list-style: none;
  margin: 0;
  padding: 0;
}
.moves li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: default;
}
.moves li.best {
  background: #e6f0d8;
  cursor: pointer;
}
.moves li .coord {
  font-weight: 700;
  width: 40px;
}
.moves li .wr {
  flex: 1;
}
.moves li .sc {
  color: #555;
  width: 48px;
  text-align: right;
}
.moves li .vis {
  color: #999;
  font-size: 11px;
}
.empty {
  color: #999;
  font-size: 13px;
}
.hint {
  font-size: 11px;
  color: #888;
  margin-top: 8px;
}
</style>
