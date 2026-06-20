import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Calendar as CalendarIcon, Edit2, Key, MoreVertical, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ListColumn, ListGenerator } from '@/components/common/list-generator'
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { APIKeyResponse, RolePermissions, useGetAdminsSimple } from '@/service/api'
import { countEnabledPermissions } from '@/features/admin-roles/components/permission-editor'
import { RolePermissionFormMap } from '@/features/admin-roles/forms/admin-role-form'
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

  if (!canUpdate && !canDelete) return null

  return (
    <div onClick={event => event.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon">
            <MoreVertical className="h-4 w-4" />
            <span className="sr-only">{t('actions')}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>{t('actions')}</DropdownMenuLabel>
          {canUpdate && (
            <DropdownMenuItem
              onSelect={event => {
                event.stopPropagation()
                onEdit(apiKey)
              }}
            >
              <Edit2 className="mr-2 h-4 w-4" />
              {t('edit')}
            </DropdownMenuItem>
          )}
          {canDelete && (
            <>
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation()
                  onRevoke(apiKey)
                }}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                {t('apiKeys.revoke')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onSelect={event => {
                  event.stopPropagation()
                  onDelete(apiKey)
                }}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t('delete')}
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

  if (apiKey.is_expired) {
    return <Badge variant="destructive">{t('expired')}</Badge>
  }

  return <Badge variant={apiKey.status === 'active' ? 'green' : 'secondary'}>{t(`admins.${apiKey.status}`)}</Badge>
}

function ApiKeyPermissionsSummary({ apiKey, compact = false }: { apiKey: APIKeyResponse; compact?: boolean }) {
  const { t } = useTranslation()

  if (apiKey.inherit_permissions) {
    return <Badge variant="secondary">{t('apiKeys.inherited', { defaultValue: 'Inherited' })}</Badge>
  }

  const permissions = apiKey.permissions as RolePermissions | undefined
  const resourceCount = countEnabledResources(permissions)
  const actionCount = countEnabledPermissions(permissions as RolePermissionFormMap | undefined)

  if (compact) {
    return (
      <span className="truncate">
        {resourceCount} {t('resources', { defaultValue: 'resources' })} / {actionCount} {t('actions', { defaultValue: 'actions' })}
      </span>
    )
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      <Badge variant="outline" className="text-xs">
        {resourceCount} {t('resources', { defaultValue: 'resources' })}
      </Badge>
      <Badge variant="secondary" className="text-xs">
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
}: {
  apiKey: APIKeyResponse
  adminName?: string
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  canUpdate?: boolean
  canDelete?: boolean
}) {
  const { t } = useTranslation()

  return (
    <Card
      className={cn('group relative px-4 py-5 transition-colors', canUpdate && 'hover:bg-accent cursor-pointer', apiKey.is_expired && 'border-destructive/30')}
      onClick={() => {
        if (canUpdate) onEdit(apiKey)
      }}
    >
      <div className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <Key className={cn('mt-0.5 h-4 w-4 shrink-0', apiKey.status === 'active' && !apiKey.is_expired ? 'text-primary' : 'text-muted-foreground')} />
          <div className="min-w-0 flex-1 space-y-3">
            <div className="min-w-0 space-y-1">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate font-medium">{apiKey.name}</span>
                {adminName ? (
                  <Badge variant="outline" className="max-w-32 shrink-0 truncate px-1.5 text-[10px] font-normal">
                    {adminName}
                  </Badge>
                ) : null}
              </div>
              <div className="min-w-0">
                {apiKey.api_key_trimmed ? (
                  <code className="inline-block max-w-full truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{apiKey.api_key_trimmed}</code>
                ) : (
                  <span className="text-muted-foreground text-xs">-</span>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="text-muted-foreground flex min-w-0 items-center gap-2 text-xs">
                <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
                <ApiKeyPermissionsSummary apiKey={apiKey} compact />
              </div>
              <div className="text-muted-foreground flex min-w-0 items-center gap-2 text-xs">
                <CalendarIcon className="h-3.5 w-3.5 shrink-0" />
                <span className={cn('truncate', apiKey.is_expired && 'text-destructive font-medium')}>
                  {apiKey.expire_date ? dateUtils.formatDate(apiKey.expire_date) : t('never')}
                  {apiKey.is_expired ? ` (${t('expired')})` : ''}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <ApiKeyActionsMenu apiKey={apiKey} onEdit={onEdit} onDelete={onDelete} onRevoke={onRevoke} canUpdate={canUpdate} canDelete={canDelete} />
          <ApiKeyStatusBadge apiKey={apiKey} />
        </div>
      </div>
    </Card>
  )
}

export default function ApiKeysTable({ onEdit, onDelete, onRevoke, isCardView = false, apiKeys, isLoading, canUpdate = true, canDelete = true }: ApiKeysTableProps) {
  const { t } = useTranslation()
  const adminsQuery = useGetAdminsSimple()
  const admins = adminsQuery.data?.admins || []
  const adminNamesById = useMemo(() => new Map(admins.map(admin => [admin.id, admin.username])), [admins])

  const columns = useMemo<ListColumn<APIKeyResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('apiKeys.name'),
        width: 'minmax(12rem, 2fr)',
        skeletonClassName: 'w-40',
        cell: apiKey => {
          const adminName = adminNamesById.get(apiKey.admin_id)

          return (
            <div className="flex min-w-0 items-center gap-2">
              <Key className={cn('h-4 w-4 shrink-0', apiKey.status === 'active' && !apiKey.is_expired ? 'text-primary' : 'text-muted-foreground')} />
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-medium">{apiKey.name}</span>
                  {adminName ? (
                    <Badge variant="outline" className="max-w-28 shrink-0 truncate px-1.5 text-[10px] font-normal">
                      {adminName}
                    </Badge>
                  ) : null}
                </div>
                {apiKey.api_key_trimmed ? (
                  <code className="mt-1 inline-block max-w-full truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs md:hidden">{apiKey.api_key_trimmed}</code>
                ) : null}
              </div>
            </div>
          )
        },
      },
      {
        id: 'key',
        header: t('apiKeys.key', { defaultValue: 'API Key' }),
        width: 'minmax(10rem, 1.3fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-32',
        cell: apiKey =>
          apiKey.api_key_trimmed ? (
            <code className="inline-block max-w-full truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{apiKey.api_key_trimmed}</code>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
      },
      {
        id: 'permissions',
        header: t('adminRoles.permissions', { defaultValue: 'Permissions' }),
        width: 'minmax(10rem, 1.4fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-28',
        cell: apiKey => <ApiKeyPermissionsSummary apiKey={apiKey} />,
      },
      {
        id: 'status',
        header: t('apiKeys.status'),
        width: '7rem',
        align: 'center',
        skeletonClassName: 'w-16',
        cell: apiKey => <ApiKeyStatusBadge apiKey={apiKey} />,
      },
      {
        id: 'expire_date',
        header: t('apiKeys.expireDate'),
        width: 'minmax(9rem, 1fr)',
        hideOnMobile: true,
        skeletonClassName: 'w-24',
        cell: apiKey => (
          <span className={cn('text-muted-foreground truncate text-sm', apiKey.is_expired && 'text-destructive font-medium')}>
            {apiKey.expire_date ? dateUtils.formatDate(apiKey.expire_date) : t('never')}
          </span>
        ),
      },
      ...(canUpdate || canDelete
        ? [
            {
              id: 'actions',
              header: '',
              width: '64px',
              align: 'end' as const,
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
        showEmptyState={false}
        renderItem={apiKey => (
          <ApiKeyCard
            apiKey={apiKey}
            adminName={adminNamesById.get(apiKey.admin_id)}
            onEdit={onEdit}
            onDelete={onDelete}
            onRevoke={onRevoke}
            canUpdate={canUpdate}
            canDelete={canDelete}
          />
        )}
        renderSkeleton={index => (
          <Card key={index} className="px-4 py-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 flex-1 gap-3">
                <Skeleton className="mt-0.5 h-4 w-4 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="space-y-1.5">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-28" />
                    <Skeleton className="h-4 w-36" />
                  </div>
                </div>
              </div>
              <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
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
      className="gap-3"
      onRowClick={canUpdate ? onEdit : undefined}
      showEmptyState={false}
    />
  )
}
