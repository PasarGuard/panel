export function formatBytes(bytes: number, decimals = 2, size: boolean = true, asArray = false) {
  if (!+bytes) return size ? '0 B' : '0'

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = parseFloat((bytes / Math.pow(k, i)).toFixed(dm))

  if (asArray) return [value, sizes[i]]
  return size ? `${value} ${sizes[i]}` : `${value}`
}

export const numberWithCommas = (x: number | undefined | null) => {
  if (x === undefined || x === null) return '0'
  return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export const toPersianNumerals = (num: number | string): string => {
  const persianDigits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
  return num.toString().replace(/\d/g, digit => persianDigits[parseInt(digit)])
}
