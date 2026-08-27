import type { AnalyzeResult, Color } from './types'

export interface AnalyzePayload {
  stones: [Color, string][]
  toPlay: Color
  boardSize: number
  maxVisits?: number
  komi?: number
  includeOwnership?: boolean
  region?: string[]
}

export async function analyze(payload: AnalyzePayload): Promise<AnalyzeResult> {
  const res = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function health(): Promise<any> {
  const res = await fetch('/api/health')
  return res.json()
}

export interface TsumegoPayload {
  stones: [Color, string][]
  region: string[]
  targetVertex: string
  sideToMove: Color
  goal: 'live' | 'kill'
  attemptVertex?: string
  boardSize?: number
  maxVisits?: number
}

export interface TsumegoResult {
  target: string
  owner: Color
  sideToMove: Color
  goal: 'live' | 'kill'
  status: 'alive' | 'dead'
  achieved: boolean
  bestMove: string | null
  line: { color: Color; move: string }[]
}

export async function solveTsumego(payload: TsumegoPayload): Promise<TsumegoResult> {
  const res = await fetch('/api/tsumego/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const b = await res.json()
      detail = b.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function evaluateTsumego(payload: TsumegoPayload): Promise<TsumegoResult> {
  const res = await fetch('/api/tsumego/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const b = await res.json()
      detail = b.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}
