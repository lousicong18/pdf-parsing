import type { TableData } from '@/types'

export interface CellInfo {
  row: number
  col: number
  text: string
  colspan: number
  rowspan: number
  merged: boolean
}

export function buildCellMatrix(table: TableData): CellInfo[][] {
  const occupied = new Set<string>()
  const mergedMap = new Map<string, { colspan: number; rowspan: number }>()

  for (const m of table.merged) {
    const rowspan = Math.max(1, m.rowspan ?? 1)
    const colspan = Math.max(1, m.colspan ?? 1)
    mergedMap.set(`${m.row},${m.col}`, { colspan, rowspan })
    for (let r = 0; r < rowspan; r++) {
      for (let c = 0; c < colspan; c++) {
        if (r === 0 && c === 0) continue
        occupied.add(`${m.row + r},${m.col + c}`)
      }
    }
  }

  const matrix: CellInfo[][] = []
  for (let r = 0; r < table.rows.length; r++) {
    const row: CellInfo[] = []
    for (let c = 0; c < table.rows[r].length; c++) {
      const key = `${r},${c}`
      if (occupied.has(key)) continue
      const m = mergedMap.get(key)
      row.push({
        row: r,
        col: c,
        text: table.rows[r][c] ?? '',
        colspan: m?.colspan ?? 1,
        rowspan: m?.rowspan ?? 1,
        merged: !!m
      })
    }
    matrix.push(row)
  }
  return matrix
}
