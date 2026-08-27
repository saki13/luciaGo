<script setup lang="ts">
import { computed } from 'vue'
import type { Sign } from '../types'

interface Marker {
  x: number
  y: number
  label: string
  kind: 'best' | 'move'
}

const props = defineProps<{
  size: number
  signMap: Sign[][]
  markers?: Marker[]
  ownership?: number[] | null
  regionRect?: { x0: number; y0: number; x1: number; y1: number } | null
  targetXY?: { x: number; y: number } | null
  targetGroup?: { x: number; y: number }[] | null
}>()

const emit = defineEmits<{
  (e: 'cell-click', v: { x: number; y: number }): void
}>()

const CELL = 30
const MARGIN = 24
const R = CELL * 0.46 // stone radius

const span = computed(() => (props.size - 1) * CELL)
const vb = computed(
  () => `0 0 ${span.value + 2 * MARGIN} ${span.value + 2 * MARGIN}`
)
const px = (x: number) => MARGIN + x * CELL
const py = (y: number) => MARGIN + y * CELL

// Column letters (GTP: skip 'I')
const LETTERS = 'ABCDEFGHJKLMNOPQRST'
const cols = computed(() =>
  props.size <= 19 ? LETTERS.slice(0, props.size) : LETTERS
)
const rows = computed(() => Array.from({ length: props.size }, (_, i) => props.size - i))

const hoshi = computed(() => {
  const s = props.size
  if (s < 9) return []
  const near = s >= 13 ? 3 : 2
  const far = s - 1 - near
  const mid = (s - 1) / 2
  const pts = new Set<number>()
  const add = (x: number, y: number) => pts.add(y * s + x)
  add(near, near); add(near, far); add(far, near); add(far, far)
  if (s % 2 === 1) add(mid, mid)
  if (s === 19) {
    add(near, mid); add(far, mid); add(mid, near); add(mid, far)
  }
  return [...pts].map((idx) => ({ x: idx % s, y: Math.floor(idx / s) }))
})

function ownershipTint(i: number): string | null {
  if (!props.ownership || props.ownership.length !== props.size * props.size) return null
  const v = props.ownership[i]
  if (Math.abs(v) < 0.2) return null
  const a = Math.min(0.5, Math.abs(v) * 0.45)
  return v > 0 ? `rgba(0, 90, 190, ${a.toFixed(2)})` : `rgba(230, 60, 60, ${a.toFixed(2)})`
}

function onClick(x: number, y: number) {
  emit('cell-click', { x, y })
}
</script>

<template>
  <svg
    :viewBox="vb"
    class="goboard"
    xmlns="http://www.w3.org/2000/svg"
    :style="{ maxWidth: '100%', height: 'auto' }"
  >
    <rect
      :x="MARGIN - CELL * 0.5"
      :y="MARGIN - CELL * 0.5"
      :width="span + CELL"
      :height="span + CELL"
      rx="6"
      fill="#d9ab63"
      stroke="#b5853b"
      stroke-width="1"
    />

    <!-- grid lines -->
    <g stroke="#3a2a15" stroke-width="1.4">
      <line v-for="i in size" :key="'hl' + i" :x1="px(0)" :y1="py(i - 1)" :x2="px(size - 1)" :y2="py(i - 1)" />
      <line v-for="i in size" :key="'vl' + i" :x1="px(i - 1)" :y1="py(0)" :x2="px(i - 1)" :y2="py(size - 1)" />
    </g>

    <!-- star points -->
    <circle v-for="(h, i) in hoshi" :key="'h' + i" :cx="px(h.x)" :cy="py(h.y)" r="4" fill="#3a2a15" />

    <!-- ownership tint -->
    <g v-if="ownership && ownership.length === size * size" pointer-events="none">
      <rect
        v-for="i in size * size"
        :key="'o' + i"
        :x="px(i % size) - CELL * 0.42"
        :y="py(Math.floor(i / size)) - CELL * 0.42"
        :width="CELL * 0.84"
        :height="CELL * 0.84"
        rx="4"
        :fill="ownershipTint(i - 1) || 'transparent'"
      />
    </g>

    <!-- stones -->
    <g v-for="y in size">
      <g v-for="x in size">
        <circle
          v-if="signMap[y - 1] && signMap[y - 1][x - 1] !== 0"
          :cx="px(x - 1)"
          :cy="py(y - 1)"
          :r="R"
          :fill="signMap[y - 1][x - 1] === 1 ? '#1c1c1c' : '#f5f5f5'"
          :stroke="signMap[y - 1][x - 1] === 1 ? '#000' : '#999'"
          stroke-width="1"
        />
        <!-- clickable intersection -->
        <circle
          :cx="px(x - 1)"
          :cy="py(y - 1)"
          :r="CELL * 0.5"
          fill="transparent"
          style="cursor: pointer"
          @click="onClick(x - 1, y - 1)"
        />
      </g>
    </g>

    <!-- markers -->
    <g v-for="m in markers || []" :key="m.x + '-' + m.y +
      m.label" pointer-events="none">
      <circle
        :cx="px(m.x)"
        :cy="py(m.y)"
        :r="m.kind === 'best' ? CELL * 0.4 : CELL * 0.26"
        :fill="m.kind === 'best' ? 'rgba(46,204,113,0.9)' : 'rgba(241,196,15,0.85)'"
        fill-opacity="0.45"
        :stroke="m.kind === 'best' ? '#1a8f4f' : '#b8860b'"
        stroke-width="2"
      />
      <text
        :x="px(m.x)"
        :y="py(m.y) + (m.kind === 'best' ? -CELL * 0.9 : CELL * 0.55)"
        text-anchor="middle"
        font-size="11"
        font-weight="700"
        :fill="m.kind === 'best' ? '#0b5c31' : '#7a5704'"
      >
        {{ m.label }}
      </text>
    </g>

    <!-- problem region (tsumego) -->
    <rect
      v-if="regionRect"
      pointer-events="none"
      :x="px(regionRect.x0) - CELL * 0.6"
      :y="py(regionRect.y0) - CELL * 0.6"
      :width="(regionRect.x1 - regionRect.x0) * CELL + CELL * 1.2"
      :height="(regionRect.y1 - regionRect.y0) * CELL + CELL * 1.2"
      fill="rgba(255, 80, 120, 0.10)"
      stroke="rgba(220, 40, 90, 0.55)"
      stroke-width="2"
      stroke-dasharray="6 4"
    />

    <!-- target group highlight (whole group) -->
    <g v-if="targetGroup && targetGroup.length" pointer-events="none">
      <circle
        v-for="(p, i) in targetGroup"
        :key="'tg' + i"
        :cx="px(p.x)"
        :cy="py(p.y)"
        :r="R + 3"
        fill="none"
        stroke="#e74c3c"
        stroke-width="3"
        stroke-opacity="0.95"
      />
    </g>
    <circle
      v-else-if="targetXY"
      pointer-events="none"
      :cx="px(targetXY.x)"
      :cy="py(targetXY.y)"
      :r="R + 3"
      fill="none"
      stroke="#e74c3c"
      stroke-width="3"
      stroke-opacity="0.9"
    />

    <!-- coordinate labels -->
    <g font-size="10" fill="#6b4d1c">
      <text v-for="(c, i) in cols" :key="'ct' + i" :x="px(i)" :y="MARGIN - CELL * 0.6" text-anchor="middle">{{ c }}</text>
      <text v-for="(r, i) in rows" :key="'rt' + i" :x="MARGIN - CELL * 0.6" :y="py(i) + 3" text-anchor="end">{{ r }}</text>
    </g>
  </svg>
</template>

<style scoped>
.goboard {
  -webkit-user-select: none;
  user-select: none;
  touch-action: manipulation;
}
</style>
