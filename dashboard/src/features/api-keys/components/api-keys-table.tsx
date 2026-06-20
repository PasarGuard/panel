import { useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Calendar as CalendarIcon, KeyRound, MoreVertical, Pencil, RotateCcw, ShieldCheck, Trash2, UserRound } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ListColumn, ListGenerator } from '@/components/common/list-generator'
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'
import { Skeleton } from '@/components/ui/skeleton'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { APIKeyResponse, RolePermissions, useGetAdminsSimple } from '@/service/api'
import { countEnabledPermissions } from '@/features/admin-roles/components/permission-editor'
import { RolePermissionFormMap } from '@/features/admin-roles/forms/admin-role-form'
import { AdminStatusBadge } from '@/features/admins/components/admin-status-badge'
import { dateUtils } from '@/utils/dateFormatter'

interface ApiKeysTableProps {
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  isCardView?: boolean
  apiKeys: APIKeyResponse[]
  isLoading: boolean
  canUpdate?: boolean
  canDelete?: boolean
  enableSelection?: boolean
  selectedRowIds?: number[]
  onSelectionChange?: (ids: number[]) => void
}

function countEnabledResources(permissions: RolePermissions | undefined): number {
  if (!permissions) return 0

  return Object.values(permissions).reduce((total, resource) => {
    if (!resource || typeof resource !== 'object') return total

    const hasEnabledPermission = Object.values(resource as Record<string, unknown>).some(value => {
      if (value === true) return true
      return !!value && typeof value === 'object' && Number((value as { scope?: unknown }).scope) > 0
    })

    return hasEnabledPermission ? total + 1 : total
  }, 0)
}

function ApiKeyActionsMenu({
  apiKey,
  onEdit,
  onDelete,
  onRevoke,
  canUpdate = true,
  canDelete = true,
}: {
  apiKey: APIKeyResponse
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  canUpdate?: boolean
  canDelete?: boolean
}) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  if (!canUpdate && !canDelete) return null

  return (
    <div onClick={event => event.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8">
            <MoreVertical className="!h-3.5 !w-3.5" />
            <span className="sr-only">{t('actions')}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
          {canUpdate && (
            <DropdownMenuItem
              onSelect={event => {
                event.preventDefault()
                event.stopPropagation()
                onEdit(apiKey)
              }}
            >
              <Pencil className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />
              <span className="min-w-0 truncate">{t('edit')}</span>
            </DropdownMenuItem>
          )}
          {canDelete && (
            <>
              <DropdownMenuItem
                onSelect={event => {
                  event.preventDefault()
                  event.stopPropagation()
                  onRevoke(apiKey)
                }}
              >
                <RotateCcw className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />
                <span className="min-w-0 truncate">{t('apiKeys.revoke')}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive"
                onSelect={event => {
                  event.preventDefault()
                  event.stopPropagation()
                  onDelete(apiKey)
                }}
              >
                <Trash2 className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />
                <span className="min-w-0 truncate">{t('delete')}</span>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function ApiKeyStatusBadge({ apiKey }: { apiKey: APIKeyResponse }) {
  const { t } = useTranslation()
  const status = apiKey.is_expired ? 'expired' : apiKey.status || 'active'

  return (
    <div className="flex flex-col gap-y-2 py-1">
      <div className="hidden md:block">
        <AdminStatusBadge isSudo={false} status={status} label={t(`status.${status}`, { defaultValue: status })} />
      </div>
      <div className="md:hidden">
        <AdminStatusBadge compact isSudo={false} status={status} />
      </div>
    </div>
  )
}

function ApiKeyPermissionsSummary({ apiKey, compact = false }: { apiKey: APIKeyResponse; compact?: boolean }) {
  const { t } = useTranslation()

  if (apiKey.inherit_permissions) {
    return (
      <Badge variant="secondary" className="w-fit shrink-0 text-[10px] font-medium">
        {t('apiKeys.inherited', { defaultValue: 'Inherited' })}
      </Badge>
    )
  }

  const permissions = apiKey.permissions as RolePermissions | undefined
  const resourceCount = countEnabledResources(permissions)
  const actionCount = countEnabledPermissions(permissions as RolePermissionFormMap | undefined)

  if (compact) {
    return (
      <span className="truncate leading-none">
        {resourceCount} {t('resources', { defaultValue: 'resources' })} / {actionCount} {t('actions', { defaultValue: 'actions' })}
      </span>
    )
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      <Badge variant="outline" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
        {resourceCount} {t('resources', { defaultValue: 'resources' })}
      </Badge>
      <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
        {actionCount} {t('actions', { defaultValue: 'actions' })}
      </Badge>
    </div>
  )
}

function ApiKeyCard({
  apiKey,
  adminName,
  onEdit,
  onDelete,
  onRevoke,
  canUpdate = true,
  canDelete = true,
  selectionControl,
  selected = false,
}: {
  apiKey: APIKeyResponse
  adminName?: string
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  canUpdate?: boolean
  canDelete?: boolean
  selectionControl?: ReactNode
  selected?: boolean
}) {
  const { t } = useTranslation()
  const isActive = apiKey.status === 'active' && !apiKey.is_expired

  return (
    <Card
      className={cn(
        'group bg-background relative overflow-hidden rounded-md px-3.5 py-3 transition-colors sm:px-4',
        canUpdate && 'hover:bg-muted/40 cursor-pointer',
        selected && 'border-primary/50 bg-muted/40',
        apiKey.is_expired && 'border-amber-500/30',
      )}
      onClick={() => {
        if (canUpdate) onEdit(apiKey)
      }}
    >
      <div className="flex min-w-0 items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-md', isActive ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground')}>
          <KeyRound className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0 space-y-1.5">
              <div className="flex min-w-0 items-center gap-x-2">
                <span className="min-w-0 truncate text-sm font-medium">{apiKey.name}</span>
                {adminName ? (
                  <Badge variant="outline" className="flex max-w-32 shrink-0 items-center gap-1 px-1.5 text-[10px] font-normal opacity-80 sm:max-w-36">
                    <UserRound className="h-3 w-3 shrink-0" />
                    <span className="min-w-0 truncate">{adminName}</span>
                  </Badge>
                ) : null}
              </div>
              {apiKey.api_key_trimmed ? (
                <code className="bg-muted/80 inline-block max-w-full truncate rounded px-1.5 py-0.5 font-mono text-xs">{apiKey.api_key_trimmed}</code>
              ) : (
                <span className="text-muted-foreground text-xs">-</span>
              )}
            </div>

            <div className="flex shrink-0 items-start gap-1.5">
              <ApiKeyStatusBadge apiKey={apiKey} />
              <ApiKeyActionsMenu apiKey={apiKey} onEdit={onEdit} onDelete={onDelete} onRevoke={onRevoke} canUpdate={canUpdate} canDelete={canDelete} />
            </div>
          </div>

          <div className="border-border/70 grid gap-2 border-t pt-2 text-xs sm:grid-cols-2">
            <div className="text-muted-foreground flex min-w-0 items-center gap-1.5 leading-none">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
              <ApiKeyPermissionsSummary apiKey={apiKey} compact />
            </div>
            <div className="text-muted-foreground flex min-w-0 items-center gap-1.5 leading-none sm:justify-end">
              <CalendarIcon className="h-3.5 w-3.5 shrink-0" />
              <span className={cn('truncate', apiKey.is_expired && 'text-destructive font-medium')}>{apiKey.expire_date ? dateUtils.formatDate(apiKey.expire_date) : t('never')}</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function ApiKeysTable({
  onEdit,
  onDelete,
  onRevoke,
  isCardView = false,
  apiKeys,
  isLoading,
  canUpdate = true,
  canDelete = true,
  enableSelection = false,
  selectedRowIds = [],
  onSelectionChange,
}: ApiKeysTableProps) {
  const { t } = useTranslation()
  const adminsQuery = useGetAdminsSimple()
  const admins = adminsQuery.data?.admins || []
  const adminNamesById = useMemo(() => new Map(admins.map(admin => [admin.id, admin.username])), [admins])

  const columns = useMemo<ListColumn<APIKeyResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('apiKeys.name'),
        width: 'minmax(14rem, 2fr)',
        skeletonClassName: 'w-40',
        cell: apiKey => {
          const adminName = adminNamesById.get(apiKey.admin_id)

          return (
            <div className="flex min-w-0 items-start gap-x-2 px-0.5 py-1">
              <div className="pt-0.5">
                <KeyRound className={cn('h-4 w-4 shrink-0', apiKey.status === 'active' && !apiKey.is_expired ? 'text-primary' : 'text-muted-foreground/70')} />
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-y-1 overflow-hidden">
                <div className="flex min-w-0 items-center gap-x-1.5 overflow-hidden">
                  <span className="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap">{apiKey.name}</span>
                  {adminName ? (
                    <Badge variant="outline" className="flex max-w-28 shrink-0 items-center gap-1 px-1.5 text-[10px] font-normal opacity-80">
                      <UserRound className="h-3 w-3 shrink-0" />
                      <span className="min-w-0 truncate">{adminName}</span>
                    </Badge>
                  ) : null}
                </div>
              </div>
            </div>
          )
        },
      },
      {
        id: 'key',
        header: t('apiKeys.key', { defaultValue: 'API Key' }),
        width: 'minmax(10rem, 1.2fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-32',
        cell: apiKey =>
          apiKey.api_key_trimmed ? (
            <code className="bg-muted/80 inline-block max-w-full truncate rounded px-1.5 py-0.5 font-mono text-xs">{apiKey.api_key_trimmed}</code>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
      },
      {
        id: 'permissions',
        header: t('adminRoles.permissions', { defaultValue: 'Permissions' }),
        width: 'minmax(9rem, 1.2fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-28',
        cell: apiKey => <ApiKeyPermissionsSummary apiKey={apiKey} />,
      },
      {
        id: 'status',
        header: t('apiKeys.status'),
        width: '7.5rem',
        hideOnMobile: true,
        skeletonClassName: 'h-7 w-[88px] rounded-full',
        cell: apiKey => <ApiKeyStatusBadge apiKey={apiKey} />,
      },
      {
        id: 'expire_date',
        header: t('apiKeys.expireDate'),
        width: 'minmax(9rem, 1fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-24',
        cell: apiKey => (
          <span className={cn('text-muted-foreground truncate text-sm', apiKey.is_expired && 'font-medium text-amber-600 dark:text-amber-400')}>
            {apiKey.expire_date ? dateUtils.formatDate(apiKey.expire_date) : t('never')}
          </span>
        ),
      },
      ...(canUpdate || canDelete
        ? [
            {
              id: 'actions',
              header: '',
              width: '56px',
              align: 'center' as const,
              hideOnMobile: true,
              skeletonClassName: 'w-8',
              cell: (apiKey: APIKeyResponse) => <ApiKeyActionsMenu apiKey={apiKey} onEdit={onEdit} onDelete={onDelete} onRevoke={onRevoke} canUpdate={canUpdate} canDelete={canDelete} />,
            },
          ]
        : []),
    ],
    [adminNamesById, canDelete, canUpdate, onDelete, onEdit, onRevoke, t],
  )

  if (isCardView) {
    return (
      <ListGeneratorGrid
        data={apiKeys}
        getRowId={apiKey => apiKey.id}
        isLoading={isLoading}
        loadingRows={6}
        className="gap-4"
        gridClassName="gap-3 md:grid-cols-2 xl:grid-cols-3"
        enableSelection={enableSelection}
        injectSelectionProps={enableSelection}
        selectedRowIds={selectedRowIds}
        onSelectionChange={ids => onSelectionChange?.(ids.map(id => Number(id)))}
        showEmptyState={false}
        renderItem={apiKey => (
          <ApiKeyCard apiKey={apiKey} adminName={adminNamesById.get(apiKey.admin_id)} onEdit={onEdit} onDelete={onDelete} onRevoke={onRevoke} canUpdate={canUpdate} canDelete={canDelete} />
        )}
        renderSkeleton={index => (
          <Card key={index} className="rounded-md px-3 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 flex-1 gap-3">
                <Skeleton className="mt-0.5 h-4 w-4 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1 space-y-2.5">
                  <div className="space-y-1.5">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Skeleton className="h-3.5 w-28" />
                    <Skeleton className="h-4 w-36" />
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
                <Skeleton className="h-6 w-9 rounded-full md:w-[88px]" />
              </div>
            </div>
          </Card>
        )}
      />
    )
  }

  return (
    <ListGenerator
      data={apiKeys}
      columns={columns}
      getRowId={apiKey => apiKey.id}
      isLoading={isLoading}
      loadingRows={6}
      className="gap-1.5"
      rowClassName="py-2"
      onRowClick={canUpdate ? onEdit : undefined}
      enableSelection={enableSelection}
      selectedRowIds={selectedRowIds}
      onSelectionChange={ids => onSelectionChange?.(ids.map(id => Number(id)))}
      showEmptyState={false}
    />
  )
}
