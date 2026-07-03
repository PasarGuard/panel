// sessionIDTable predefined aliases (from Xray-core) -> their character-set length.
export const PREDEFINED_TABLE_LENGTHS: Record<string, number> = {
  ALPHABET: 26,
  Alphabet: 52,
  BASE36: 36,
  Base62: 62,
  HEX: 16,
  alphabet: 26,
  base36: 36,
  hex: 16,
  number: 10,
}

// Xray requires at least ~2.1B possible session IDs (Go: 2<<30).
export const ROOM_SIZE_THRESHOLD = 2 * 2 ** 30

export function sessionIdTableLength(table: string): number {
  return PREDEFINED_TABLE_LENGTHS[table] ?? table.length
}

// Parse "from-to" (or a single "n") into [from, to].
export function parseLengthRange(value: string): [number, number] | null {
  const match = value.match(/^(\d+)(?:-(\d+))?$/)
  if (!match) return null
  const from = Number(match[1])
  const to = match[2] !== undefined ? Number(match[2]) : from
  return [from, to]
}

// room = sum of tableLen^k for k in [from, to]. Short-circuits once over the threshold.
export function sessionIdRoomSize(tableLen: number, from: number, to: number): number {
  let sum = 0
  for (let k = from; k <= to; k++) {
    sum += Math.pow(tableLen, k)
    if (sum >= ROOM_SIZE_THRESHOLD) return sum
  }
  return sum
}

export type SessionIdRoomSizeProblem = 'length-not-positive' | 'room-too-small'

/**
 * Mirrors Xray-core's Build()-time check on `sessionIDTable`/`sessionIDLength` (XHTTP transport).
 * Returns null when `length` doesn't parse (format is checked elsewhere) or the combination is safe.
 */
export function checkSessionIdRoomSize(table: string, length: string): SessionIdRoomSizeProblem | null {
  const range = parseLengthRange(length)
  if (!range) return null
  const [from, to] = range
  if (from <= 0) return 'length-not-positive'
  const room = sessionIdRoomSize(sessionIdTableLength(table), from, to)
  return room < ROOM_SIZE_THRESHOLD ? 'room-too-small' : null
}
