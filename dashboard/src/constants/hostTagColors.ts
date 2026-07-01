import { HostTagColor } from '@/service/api'

export interface TagColorStyle {
  chip: string
  bar: string
  tint: string
}

export const HOST_TAG_COLORS: Record<HostTagColor, TagColorStyle> = {
  slate: { chip: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30', bar: 'bg-slate-500', tint: 'bg-slate-500/[0.06] dark:bg-slate-500/10 backdrop-blur-sm backdrop-saturate-150' },
  red: { chip: 'bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30', bar: 'bg-red-500', tint: 'bg-red-500/[0.06] dark:bg-red-500/10 backdrop-blur-sm backdrop-saturate-150' },
  orange: { chip: 'bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30', bar: 'bg-orange-500', tint: 'bg-orange-500/[0.06] dark:bg-orange-500/10 backdrop-blur-sm backdrop-saturate-150' },
  amber: { chip: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30', bar: 'bg-amber-500', tint: 'bg-amber-500/[0.06] dark:bg-amber-500/10 backdrop-blur-sm backdrop-saturate-150' },
  green: { chip: 'bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30', bar: 'bg-green-500', tint: 'bg-green-500/[0.06] dark:bg-green-500/10 backdrop-blur-sm backdrop-saturate-150' },
  teal: { chip: 'bg-teal-500/15 text-teal-700 dark:text-teal-300 border-teal-500/30', bar: 'bg-teal-500', tint: 'bg-teal-500/[0.06] dark:bg-teal-500/10 backdrop-blur-sm backdrop-saturate-150' },
  sky: { chip: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30', bar: 'bg-sky-500', tint: 'bg-sky-500/[0.06] dark:bg-sky-500/10 backdrop-blur-sm backdrop-saturate-150' },
  blue: { chip: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30', bar: 'bg-blue-500', tint: 'bg-blue-500/[0.06] dark:bg-blue-500/10 backdrop-blur-sm backdrop-saturate-150' },
  violet: { chip: 'bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30', bar: 'bg-violet-500', tint: 'bg-violet-500/[0.06] dark:bg-violet-500/10 backdrop-blur-sm backdrop-saturate-150' },
  pink: { chip: 'bg-pink-500/15 text-pink-700 dark:text-pink-300 border-pink-500/30', bar: 'bg-pink-500', tint: 'bg-pink-500/[0.06] dark:bg-pink-500/10 backdrop-blur-sm backdrop-saturate-150' },
}

export const HOST_TAG_COLOR_KEYS = Object.keys(HOST_TAG_COLORS) as HostTagColor[]

export const getTagColorStyle = (color?: string | null): TagColorStyle =>
  (color && HOST_TAG_COLORS[color as HostTagColor]) || HOST_TAG_COLORS.slate
