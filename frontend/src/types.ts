export type Sign = 0 | -1 | 1
export type Color = 'B' | 'W'

export interface MoveInfo {
  move: string // GTP vertex, e.g. "D4"
  winrate: number
  scoreLead: number
  visits: number
  order: number
  prior?: number
  pv?: string[]
  lcb?: number
}

export interface RootInfo {
  winrate: number
  scoreLead: number
  currentPlayer: Color
  visits: number
}

export interface AnalyzeResult {
  boardSize: number
  toPlay: Color
  rootInfo?: RootInfo
  moveInfos: MoveInfo[]
  ownership?: number[]
  ownershipStdev?: number[]
  turnNumber?: number
}
