type Translate = (key: string, options?: { defaultValue?: string }) => string

const formatUnit = (value: number, singular: string, plural: string, t: Translate) => {
  const key = value === 1 ? singular : plural
  return `${value} ${t(`time.${key}`, { defaultValue: key })}`
}

export const formatDuration = (seconds: number | null | undefined, t: Translate) => {
  const totalSeconds = Math.max(0, Math.floor(Number(seconds) || 0))
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const remainingSeconds = totalSeconds % 60

  const parts: string[] = []
  if (days > 0) parts.push(formatUnit(days, 'day', 'days', t))
  if (hours > 0) parts.push(formatUnit(hours, 'hour', 'hours', t))
  if (minutes > 0 && parts.length < 2) parts.push(formatUnit(minutes, 'min', 'mins', t))
  if (parts.length === 0) parts.push(formatUnit(remainingSeconds, 'second', 'seconds', t))

  return parts.slice(0, 2).join(', ')
}
