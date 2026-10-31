import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import type { MyHost, MyHostsPolicy } from '@/service/api'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ArrowDown, ArrowUp, GripVertical, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  host: MyHost
  index: number
  total: number
  policy: MyHostsPolicy
  disabled: boolean
  onRename: (value: string) => void
  onToggle: (enabled: boolean) => void
  onMove: (offset: number) => void
  onReset: () => void
}

export function PersonalHostRow({ host, index, total, policy, disabled, onRename, onToggle, onMove, onReset }: Props) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: host.id, disabled: disabled || !policy.allow_reorder })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`bg-card relative grid items-center gap-3 rounded-lg border p-4 sm:grid-cols-[auto_1fr_auto] ${isDragging ? 'z-10 shadow-lg' : ''}`}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          {...attributes}
          {...listeners}
          disabled={disabled || !policy.allow_reorder}
          className="text-muted-foreground focus-visible:ring-ring cursor-grab touch-none rounded p-1 focus-visible:ring-2 disabled:cursor-default disabled:opacity-30"
          aria-label={t('myHosts.drag', { name: host.remark })}
        >
          <GripVertical className="h-4 w-4" />
        </button>
        <span className="text-muted-foreground w-6 text-center font-mono text-sm">{index + 1}</span>
        <div className="flex sm:flex-col">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={disabled || !policy.allow_reorder || index === 0}
            onClick={() => onMove(-1)}
            aria-label={t('myHosts.moveUp', { name: host.remark })}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={disabled || !policy.allow_reorder || index === total - 1}
            onClick={() => onMove(1)}
            aria-label={t('myHosts.moveDown', { name: host.remark })}
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="min-w-0 space-y-2">
        <label className="sr-only" htmlFor={`personal-host-${host.id}`}>
          {t('myHosts.name', { name: host.original_remark })}
        </label>
        <Input id={`personal-host-${host.id}`} value={host.remark} maxLength={256} disabled={disabled || !policy.allow_rename} onChange={event => onRename(event.target.value)} />
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span className="break-all">
            {t('myHosts.original')}: {host.original_remark}
          </span>
          <span className="font-mono" dir="ltr">
            {host.inbound_tag}
          </span>
          {host.globally_disabled && <Badge variant="secondary">{t('myHosts.globallyDisabled')}</Badge>}
        </div>
      </div>
      <div className="flex items-center justify-end gap-4">
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={!host.is_disabled}
            disabled={disabled || !policy.allow_disable || host.globally_disabled}
            onCheckedChange={onToggle}
            aria-label={t('myHosts.visibility', { name: host.remark })}
          />
          <span>{t(host.is_disabled ? 'myHosts.hidden' : 'myHosts.visible')}</span>
        </label>
        <Button
          size="icon"
          variant="ghost"
          disabled={disabled || (!policy.allow_rename && !policy.allow_disable)}
          onClick={onReset}
          aria-label={t('myHosts.resetHost', { name: host.original_remark })}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
