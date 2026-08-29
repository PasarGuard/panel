import { AlertCircle, Ban, Clock, Wifi } from 'lucide-react'
import { ForwardRefExoticComponent, SVGProps } from 'react'

export const statusColors: {
  [key: string]: {
    statusColor: string
    bandWidthColor: string
    sliderColor: string
    icon: ForwardRefExoticComponent<SVGProps<SVGSVGElement>>
  }
} = {
  active: {
    statusColor: 'border-0 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    bandWidthColor: 'bg-primary-500',
    icon: Wifi,
    sliderColor: 'bg-emerald-600',
  },
  connected: {
    statusColor: 'border-0 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    bandWidthColor: 'bg-primary-500',
    icon: Wifi,
    sliderColor: 'bg-primary-500',
  },
  disabled: {
    statusColor: 'border-0 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
    bandWidthColor: 'bg-zinc-400',
    icon: Ban,
    sliderColor: 'bg-neutral-600',
  },
  expired: {
    statusColor: 'border-0 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    bandWidthColor: 'bg-amber-500',
    icon: Clock,
    sliderColor: 'bg-amber-600',
  },
  on_hold: {
    statusColor: 'border-0 bg-violet-500/10 text-violet-700 dark:text-violet-300',
    bandWidthColor: 'bg-violet-500',
    icon: Clock,
    sliderColor: 'bg-violet-800',
  },
  connecting: {
    statusColor: 'border-0 bg-orange-500/10 text-orange-700 dark:text-orange-300',
    bandWidthColor: 'bg-orange-500',
    icon: Clock,
    sliderColor: 'bg-primary-500',
  },
  limited: {
    statusColor: 'border-0 bg-red-500/10 text-red-700 dark:text-red-300',
    bandWidthColor: 'bg-red-500',
    icon: AlertCircle,
    sliderColor: 'bg-red-600',
  },
  error: {
    statusColor: 'border-0 bg-red-500/10 text-red-700 dark:text-red-300',
    bandWidthColor: 'bg-red-500',
    icon: AlertCircle,
    sliderColor: 'bg-red-900',
  },
}
