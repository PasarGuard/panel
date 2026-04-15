import { memo } from 'react'
import { createPortal } from 'react-dom'
import type { LucideIcon } from 'lucide-react'
import { Link2Off, MoreHorizontal, RefreshCcw, Settings, Trash2, UserCog, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

export interface BulkActionItem {
  key: string
  label: string
  icon: LucideIcon
  onClick: () => void
  destructive?: boolean
  direct?: boolean
  disabled?: boolean
}

interface BulkActionsBarProps {
  selectedCount: number
  onClear: () => void
  actions?: BulkActionItem[]
  onDelete?: () => void
  onResetUsage?: () => void
  onRevokeSub?: () => void
  onChangeOwner?: () => void
  onApplyTemplate?: () => void
}

export const BulkActionsBar = memo(({ selectedCount, onClear, actions, onDelete, onResetUsage, onRevokeSub, onChangeOwner, onApplyTemplate }: BulkActionsBarProps) => {
  const { t } = useTranslation()
  const defaultActions: Array<BulkActionItem | null> = [
    onDelete
      ? {
          key: 'delete',
          label: t('usersTable.delete'),
          icon: Trash2,
          onClick: onDelete,
          direct: true,
          destructive: true,
        }
      : null,
    onResetUsage
      ? {
          key: 'reset',
          label: t('userDialog.resetUsage'),
          icon: RefreshCcw,
          onClick: onResetUsage,
        }
      : null,
    onRevokeSub
      ? {
          key: 'revoke',
          label: t('userDialog.revokeSubscription'),
          icon: Link2Off,
          onClick: onRevokeSub,
        }
      : null,
    onChangeOwner
      ? {
          key: 'owner',
          label: t('setOwnerModal.title'),
          icon: UserCog,
          onClick: onChangeOwner,
        }
      : null,
    onApplyTemplate
      ? {
          key: 'apply_template',
          label: t('bulk.applyTemplate'),
          icon: Settings,
          onClick: onApplyTemplate,
        }
      : null,
  ]
  const resolvedActions =
    actions ??
    defaultActions.filter((action): action is BulkActionItem => action !== null)
  const directActions = resolvedActions.filter(action => action.direct)
  const menuActions = resolvedActions.filter(action => !action.direct)

  if (typeof document === 'undefined') {
    return null
  }

  return createPortal(
    <div className={cn('fixed top-4 left-1/2 z-50', 'pointer-events-none')}>
      <div
        className={cn(
          'flex -translate-x-1/2 items-center gap-1.5 sm:gap-2',
          'rounded-full border bg-background/95 px-2.5 py-1.5 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:px-4 sm:py-2',
          'pointer-events-auto transition-all duration-200 ease-out',
          selectedCount > 0
            ? 'translate-y-0 scale-100 opacity-100'
            : 'pointer-events-none -translate-y-2 scale-95 opacity-0',
        )}
      >
        <span className="whitespace-nowrap text-xs font-medium sm:text-sm">
          {selectedCount} {t('bulk.targets')}
        </span>
        {directActions.map(action => (
          <div key={action.key} className="contents">
            <div className="h-3 w-px bg-border sm:h-4" />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={action.onClick}
              disabled={action.disabled}
              className={cn(
                'h-7 w-7 sm:h-8 sm:w-8',
                action.destructive && 'text-destructive hover:bg-destructive/10 hover:text-destructive',
              )}
              aria-label={action.label}
            >
              <action.icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </div>
        ))}
        {menuActions.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8" aria-label={t('more')}>
                <MoreHorizontal className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="bottom" className="z-[60]">
              {menuActions.map(action => (
                <DropdownMenuItem
                  key={action.key}
                  onClick={action.onClick}
                  disabled={action.disabled}
                  className={cn('gap-2 text-sm', action.destructive && 'text-destructive focus:text-destructive')}
                >
                  <action.icon className="h-4 w-4" />
                  {action.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <div className="h-3 w-px bg-border sm:h-4" />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onClear}
          className="h-7 w-7 sm:h-8 sm:w-8"
          aria-label={t('clear')}
        >
          <X className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        </Button>
      </div>
    </div>,
    document.body,
  )
})

BulkActionsBar.displayName = 'BulkActionsBar'
