const envPortRegex = /^env:[A-Za-z_][A-Za-z0-9_]*$/

function isValidPortNumber(value: number, min = 1): boolean {
  return Number.isInteger(value) && value >= min && value <= 65535
}

export function isValidXrayPortListSegment(segment: string, min = 1): boolean {
  const trimmed = segment.trim()
  if (trimmed === '') return false
  if (envPortRegex.test(trimmed)) return true
  if (/^\d+$/.test(trimmed)) return isValidPortNumber(Number(trimmed), min)

  const range = trimmed.match(/^(\d+)-(\d+)$/)
  if (!range) return false
  const from = Number(range[1])
  const to = Number(range[2])
  return isValidPortNumber(from, min) && isValidPortNumber(to, min) && from <= to
}

export function isValidXrayPortList(raw: string, min = 1): boolean {
  return raw.split(',').every(segment => isValidXrayPortListSegment(segment, min))
}
