type ByteUnit = 'B' | 'KB' | 'MB' | 'GB' | 'TB' | 'PB' | 'EB' | 'ZB' | 'YB'

export function formatBytes(bytes: number, decimals?: number, size?: boolean, asArray?: false, forceUnit?: ByteUnit): string
export function formatBytes(bytes: number, decimals: number | undefined, size: boolean | undefined, asArray: true, forceUnit?: ByteUnit): [number, ByteUnit]
export function formatBytes(bytes: number, decimals = 2, size: boolean = true, asArray = false, forceUnit?: ByteUnit) {
  if (!+bytes) return size ? '0 B' : '0'

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes: ByteUnit[] = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

  if (forceUnit && sizes.includes(forceUnit)) {
    const i = sizes.indexOf(forceUnit)
    const value = parseFloat((bytes / Math.pow(k, i)).toFixed(dm))
    if (asArray) return [value, forceUnit]
    return size ? `${value} ${forceUnit}` : `${value}`
  }

  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = parseFloat((bytes / Math.pow(k, i)).toFixed(dm))

  if (asArray) return [value, sizes[i]]
  return size ? `${value} ${sizes[i]}` : `${value}`
}

export function formatGigabytes(gb: number, decimals = 2): string {
  return formatBytes(gb * 1024 * 1024 * 1024, decimals)
}

export const numberWithCommas = (x: number | undefined | null) => {
  if (x === undefined || x === null) return '0'
  return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export const toPersianNumerals = (num: number | string): string => {
  const persianDigits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
  return num.toString().replace(/\d/g, digit => persianDigits[parseInt(digit)])
}

/**
 * Converts GB to bytes
 * @param gb - The value in GB (can be string, number, null, or undefined)
 * @returns The value in bytes as a number, or undefined if input is invalid
 */
export function gbToBytes(gb: string | number | null | undefined): number | undefined {
  if (gb === undefined || gb === null || gb === '') return undefined
  return Math.round(Number(gb) * 1024 * 1024 * 1024)
}
