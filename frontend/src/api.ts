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
