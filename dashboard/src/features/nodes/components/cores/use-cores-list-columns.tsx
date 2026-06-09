import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { CoreResponse } from '@/service/api'
import CoreActionsMenu from '@/features/nodes/components/cores/core-actions-menu'

interface UseCoresListColumnsProps {
  onEdit: (core: CoreResponse) => void
  onDuplicate?: (coreId: number | string) => void
  onDelete?: (coreName: string, coreId: number) => void
  canUpdate?: boolean
  canCreate?: boolean
  canDelete?: boolean
}

export const useCoresListColumns = ({ onEdit, onDuplicate, onDelete, canUpdate = true, canCreate = true, canDelete = true }: UseCoresListColumnsProps) => {
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
      ...(canUpdate || canCreate || canDelete
        ? [
            {
              id: 'actions',
              header: '',
              width: '24px',
              align: 'end' as const,
              hideOnMobile: false,
              cell: (core: CoreResponse) => (
                <CoreActionsMenu
                  core={core}
                  onEdit={onEdit}
                  onDuplicate={canCreate && onDuplicate ? () => onDuplicate(core.id) : undefined}
                  onDelete={canDelete && onDelete ? () => onDelete(core.name, core.id) : undefined}
                  canUpdate={canUpdate}
                  canCreate={canCreate}
                  canDelete={canDelete}
                />
              ),
            },
          ]
        : []),
    ],
    [t, onEdit, onDuplicate, onDelete, canUpdate, canCreate, canDelete],
  )
}
