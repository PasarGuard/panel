import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { CoreResponse } from '@/service/api'
import CoreActionsMenu from '@/components/cores/core-actions-menu'

interface UseCoresListColumnsProps {
  onEdit: (core: CoreResponse) => void
  onDuplicate?: (coreId: number | string) => void
  onDelete?: (coreName: string, coreId: number) => void
}

export const useCoresListColumns = ({ onEdit, onDuplicate, onDelete }: UseCoresListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<CoreResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '2.5fr',
        cell: core => (
          <div className="flex min-w-0 items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full bg-green-500" />
            <span className="truncate font-medium">{core.name}</span>
          </div>
        ),
      },
      {
        id: 'actions',
        header: '',
        width: '24px',
        align: 'end',
        hideOnMobile: false,
        cell: core => (
          <CoreActionsMenu
            core={core}
            onEdit={onEdit}
            onDuplicate={onDuplicate ? () => onDuplicate(core.id) : undefined}
            onDelete={onDelete ? () => onDelete(core.name, core.id) : undefined}
          />
        ),
      },
    ],
    [t, onEdit, onDuplicate, onDelete],
  )
}
