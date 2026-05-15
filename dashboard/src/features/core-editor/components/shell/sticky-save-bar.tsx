import { LoaderButton } from '@/components/ui/loader-button'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

interface StickySaveBarProps {
  dirty: boolean
  onSave: () => void
  onDiscard: () => void
  saving: boolean
  showRestart?: boolean
  restartNodes: boolean
  onRestartChange: (v: boolean) => void
  className?: string
}

export function StickySaveBar({
  dirty,
  onSave,
  onDiscard,
  saving,
  showRestart,
  restartNodes,
  onRestartChange,
  className,
}: StickySaveBarProps) {
  const { t } = useTranslation()
  const statusLabel = dirty
    ? t('coreEditor.unsaved', { defaultValue: 'Unsaved changes' })
    : t('coreEditor.saved', { defaultValue: 'All changes saved' })

  return (
    <div
      className={cn(
        'sticky bottom-0 z-20 flex flex-col gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:flex-row sm:items-center sm:justify-end mb-4',
        className,
      )}
    >
      <TooltipProvider delayDuration={200}>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {showRestart && (
            <div className="flex items-center gap-2 pr-2">
              <Checkbox id="restart-nodes" checked={restartNodes} onCheckedChange={v => onRestartChange(v === true)} />
              <Label htmlFor="restart-nodes" className="text-sm font-normal">
                {t('coreConfigModal.restartNodes', { defaultValue: 'Restart nodes' })}
              </Label>
            </div>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="relative inline-flex rounded-md">
                {dirty ? (
                  <span
                    className="absolute -right-1 -top-1 z-10 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-background"
                    aria-hidden
                  />
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!dirty || saving}
                  onClick={onDiscard}
                >
                  {t('coreEditor.discard', { defaultValue: 'Discard' })}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              {statusLabel}
            </TooltipContent>
          </Tooltip>
          <LoaderButton type="button" size="sm" disabled={!dirty || saving} isLoading={saving} onClick={onSave}>
            {t('save', { defaultValue: 'Save' })}
          </LoaderButton>
        </div>
      </TooltipProvider>
    </div>
  )
}
