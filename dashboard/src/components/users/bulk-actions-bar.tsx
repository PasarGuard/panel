import { memo } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Trash2, UserCog, X, MoreHorizontal, Link2Off, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

interface BulkActionsBarProps {
  selectedCount: number
  onClear: () => void
  onDelete?: () => void
  onRevokeSub?: () => void
  onResetUsage?: () => void
  onChangeOwner?: () => void
}

export const BulkActionsBar = memo(({ selectedCount, onClear, onDelete, onRevokeSub, onResetUsage, onChangeOwner }: BulkActionsBarProps) => {
  const { t } = useTranslation()
  const hasMenuActions = Boolean(onRevokeSub || onResetUsage || onChangeOwner)

  if (typeof document === 'undefined') {
    return null
  }

  return createPortal(
    <div
      className={cn(
        'fixed top-4 left-1/2 z-50',
        'pointer-events-none'
      )}
    >
      <div
        className={cn(
          'flex -translate-x-1/2 items-center gap-1.5 sm:gap-2',
          'rounded-full border bg-background/95 px-2.5 py-1.5 sm:px-4 sm:py-2 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/80',
          'transition-all duration-200 ease-out',
          'pointer-events-auto',
          selectedCount > 0
            ? 'opacity-100 scale-100 translate-y-0'
            : 'opacity-0 scale-95 -translate-y-2 pointer-events-none'
        )}
      >
        <span className="text-xs sm:text-sm font-medium whitespace-nowrap">
          {selectedCount} {t('bulk.targets')}
        </span>
        {onDelete && (
          <>
            <div className="h-3 w-px bg-border sm:h-4" />
            <Button
              variant="ghost"
              size="icon"
              onClick={onDelete}
              className="h-7 w-7 text-destructive hover:bg-destructive/10 hover:text-destructive sm:h-8 sm:w-8"
              aria-label={t('usersTable.delete')}
            >
              <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </>
        )}
        {hasMenuActions && (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8" aria-label={t('more')}>
                  <MoreHorizontal className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="bottom" className="z-[60] w-48">
                {onRevokeSub && (
                  <DropdownMenuItem onClick={onRevokeSub} className="gap-2 text-sm">
                    <Link2Off className="h-4 w-4" />
                    {t('userDialog.revokeSubscription')}
                  </DropdownMenuItem>
                )}
                {onResetUsage && (
                  <DropdownMenuItem onClick={onResetUsage} className="gap-2 text-sm">
                    <RefreshCcw className="h-4 w-4" />
                    {t('userDialog.resetUsage')}
                  </DropdownMenuItem>
                )}
                {onChangeOwner && (
                  <DropdownMenuItem onClick={onChangeOwner} className="gap-2 text-sm">
                    <UserCog className="h-4 w-4" />
                    {t('setOwnerModal.title')}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
        <div className="h-3 w-px bg-border sm:h-4" />
        <Button
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
    document.body
  )
})

BulkActionsBar.displayName = 'BulkActionsBar'
