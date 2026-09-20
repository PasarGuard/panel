import { useTranslation } from 'react-i18next'
import { Check, Eye, ShieldCheck, Unlock, SlidersHorizontal, LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { MCPToolInfo } from '@/service/api'

export type McpAccessPreset = 'read_only' | 'recommended' | 'full' | 'custom'

export interface McpAccessValue {
  read_only: boolean
  disabled_tools: string[]
}

interface McpAccessPresetsProps {
  value: McpAccessValue
  defaultDisabledTools: string[]
  tools: MCPToolInfo[]
  disabled?: boolean
  onChange: (next: McpAccessValue) => void
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(item => b.includes(item))

const detectPreset = (value: McpAccessValue, defaults: string[]): McpAccessPreset => {
  if (value.read_only && value.disabled_tools.length === 0) return 'read_only'
  if (!value.read_only && sameSet(value.disabled_tools, defaults)) return 'recommended'
  if (!value.read_only && value.disabled_tools.length === 0) return 'full'
  return 'custom'
}

export function McpAccessPresets({ value, defaultDisabledTools, tools, disabled = false, onChange }: McpAccessPresetsProps) {
  const { t } = useTranslation()
  const active = detectPreset(value, defaultDisabledTools)
  const writeCount = tools.filter(tool => !tool.read_only).length
  const readCount = tools.length - writeCount

  const presets: { id: McpAccessPreset; icon: LucideIcon; count: number; apply: () => McpAccessValue }[] = [
    { id: 'read_only', icon: Eye, count: readCount, apply: () => ({ read_only: true, disabled_tools: [] }) },
    {
      id: 'recommended',
      icon: ShieldCheck,
      count: tools.filter(tool => !defaultDisabledTools.includes(tool.name)).length,
      apply: () => ({ read_only: false, disabled_tools: [...defaultDisabledTools] }),
    },
    { id: 'full', icon: Unlock, count: tools.length, apply: () => ({ read_only: false, disabled_tools: [] }) },
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {presets.map(preset => {
        const selected = active === preset.id
        const Icon = preset.icon
        return (
          <button
            key={preset.id}
            type="button"
            disabled={disabled}
            onClick={() => onChange(preset.apply())}
            className={cn(
              'bg-card hover:bg-accent/50 flex flex-col gap-2 rounded-lg border p-3 text-start transition-colors sm:p-4',
              selected && 'border-primary ring-primary/30 ring-1',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <Icon className="h-4 w-4" />
                {t(`mcp.presets.${preset.id}.title`)}
              </span>
              {selected && <Check className="text-primary h-4 w-4" />}
            </div>
            <span className="text-muted-foreground text-xs">{t(`mcp.presets.${preset.id}.description`)}</span>
            <span className="text-muted-foreground text-[11px]">{t('mcp.presets.toolCount', { count: preset.count, total: tools.length })}</span>
          </button>
        )
      })}
      {active === 'custom' && (
        <div className="text-muted-foreground flex items-center gap-2 text-xs sm:col-span-3">
          <SlidersHorizontal className="h-3.5 w-3.5" />
          {t('mcp.presets.custom')}
        </div>
      )}
    </div>
  )
}
