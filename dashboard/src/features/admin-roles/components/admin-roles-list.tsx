import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { RefreshCw, Search, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'

import useDirDetection from '@/hooks/use-dir-detection'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { cn } from '@/lib/utils'
import { queryClient } from '@/utils/query-client'
import { AdminRoleResponse, getGetRolesQueryKey, getGetRolesSimpleQueryKey, useCreateRole, useDeleteRole, useGetRoles } from '@/service/api'

import { BulkActionAlertDialog } from '@/features/users/components/bulk-action-alert-dialog'
import { BulkActionItem, BulkActionsBar } from '@/features/users/components/bulk-actions-bar'

import {
  AdminRoleFormValues,
  AdminRoleFormValuesInput,
  adminRoleFormDefaultValues,
  adminRoleFormFromResponse,
  adminRoleFormSchema,
  adminRoleFormToPayload,
  isProtectedRole,
  isReadOnlyRole,
} from '@/features/admin-roles/forms/admin-role-form'
import AdminRoleCard from '@/features/admin-roles/components/admin-role-card'
import { useAdminRolesListColumns } from '@/features/admin-roles/components/use-admin-roles-list-columns'
import AdminRoleModal from '@/features/admin-roles/dialogs/admin-role-modal'

interface AdminRolesListProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
}

export default function AdminRolesList({ isDialogOpen, onOpenChange }: AdminRolesListProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [editingRole, setEditingRole] = useState<AdminRoleResponse | null>(null)
  const [isReadOnly, setIsReadOnly] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:admin-roles')
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([])
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)
  const createRole = useCreateRole()
  const deleteRole = useDeleteRole()

  const { data: rolesData, isLoading, isFetching, refetch } = useGetRoles({ limit: 100, offset: 0, sort: 'created_at' })

  const form = useForm<AdminRoleFormValuesInput, unknown, AdminRoleFormValues>({
    resolver: zodResolver(adminRoleFormSchema),
    defaultValues: adminRoleFormDefaultValues,
  })

  const handleEdit = (role: AdminRoleResponse) => {
    setEditingRole(role)
    setIsReadOnly(isReadOnlyRole(role))
    form.reset(adminRoleFormFromResponse(role))
    onOpenChange(true)
  }

  const getDuplicateRoleName = (name: string) => {
    const existingNames = new Set((rolesData?.roles || []).map(role => role.name.toLowerCase()))
    const baseName = `${name} (copy)`
    if (!existingNames.has(baseName.toLowerCase())) return baseName

    for (let index = 2; index < 1000; index += 1) {
      const nextName = `${name} (copy ${index})`
      if (!existingNames.has(nextName.toLowerCase())) return nextName
    }

    return `${baseName} ${Date.now()}`
  }

  const handleDuplicate = async (role: AdminRoleResponse) => {
    try {
      const values = adminRoleFormSchema.parse({
        ...adminRoleFormFromResponse(role),
        name: getDuplicateRoleName(role.name),
      })
      const payload = adminRoleFormToPayload(values)

      await createRole.mutateAsync({ data: payload })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('adminRoles.duplicateSuccess', {
          name: role.name,
          defaultValue: 'Role "{{name}}" has been duplicated successfully.',
        }),
      })
      await Promise.all([queryClient.invalidateQueries({ queryKey: getGetRolesQueryKey() }), queryClient.invalidateQueries({ queryKey: getGetRolesSimpleQueryKey() })])
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('adminRoles.duplicateFailed', { name: role.name, defaultValue: 'Failed to duplicate role "{{name}}".' }),
      })
    }
  }

  const handleDialogChange = (open: boolean) => {
    if (!open) {
      setEditingRole(null)
      setIsReadOnly(false)
      form.reset(adminRoleFormDefaultValues)
    }
    onOpenChange(open)
  }

  const handleRefresh = async () => {
    await refetch()
  }

  const filteredRoles = useMemo(() => {
    const list = rolesData?.roles || []
    const query = searchQuery.toLowerCase().trim()
    const filtered = query
      ? list.filter(role => {
          const localized = t(`adminRoles.names.${role.name}`, { defaultValue: role.name }).toLowerCase()
          return role.name.toLowerCase().includes(query) || localized.includes(query)
        })
      : list

    return [...filtered].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
  }, [rolesData?.roles, searchQuery, t])

  const isCurrentlyLoading = isLoading || (isFetching && !rolesData)
  const hasSearch = searchQuery.trim() !== ''
  const isEmpty = !isCurrentlyLoading && filteredRoles.length === 0 && !hasSearch
  const isSearchEmpty = !isCurrentlyLoading && filteredRoles.length === 0 && hasSearch

  const listColumns = useAdminRolesListColumns({ onEdit: handleEdit, onDuplicate: handleDuplicate })

  const clearSelection = () => setSelectedRoleIds([])

  const deletableSelectedIds = useMemo(() => {
    const map = new Map((rolesData?.roles || []).map(role => [role.id, role]))
    return selectedRoleIds.filter(id => {
      const role = map.get(id)
      return role && !isProtectedRole(role)
    })
  }, [rolesData?.roles, selectedRoleIds])

  const handleBulkDelete = async () => {
    if (!deletableSelectedIds.length) return
    try {
      const results = await Promise.allSettled(deletableSelectedIds.map(roleId => deleteRole.mutateAsync({ roleId })))
      const failed = results.filter(r => r.status === 'rejected').length
      const succeeded = results.length - failed
      if (succeeded) {
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('adminRoles.bulkDeleteSuccess', { count: succeeded, defaultValue: '{{count}} roles deleted successfully.' }),
        })
      }
      if (failed) {
        toast.error(t('error', { defaultValue: 'Error' }), {
          description: t('adminRoles.bulkDeletePartial', { count: failed, defaultValue: '{{count}} roles could not be deleted.' }),
        })
      }
      clearSelection()
      setConfirmBulkDelete(false)
      await Promise.all([queryClient.invalidateQueries({ queryKey: getGetRolesQueryKey() }), queryClient.invalidateQueries({ queryKey: getGetRolesSimpleQueryKey() })])
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('adminRoles.bulkDeleteFailed', { defaultValue: 'Failed to delete selected roles.' }),
      })
    }
  }

  const bulkActions: BulkActionItem[] =
    deletableSelectedIds.length > 0
      ? [
          {
            key: 'delete',
            label: t('delete', { defaultValue: 'Delete' }),
            icon: Trash2,
            onClick: () => setConfirmBulkDelete(true),
            direct: true,
            destructive: true,
          },
        ]
      : []

  return (
    <div className={cn('w-full flex-1 space-y-4', dir === 'rtl' && 'rtl')}>
      <div dir={dir} className="flex items-center gap-2 md:gap-4">
        <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
          <Search className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'text-muted-foreground top-1/2 h-4 w-4 -translate-y-1/2')} />
          <Input placeholder={t('search', { defaultValue: 'Search' })} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className={cn('pr-10 pl-8', dir === 'rtl' && 'pr-8 pl-10')} />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'text-muted-foreground hover:text-foreground top-1/2 -translate-y-1/2')}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Button
            type="button"
            size="icon-md"
            variant="ghost"
            onClick={handleRefresh}
            className={cn('h-9 w-9 rounded-lg border', isFetching && 'opacity-70')}
            aria-label={t('autoRefresh.refreshNow', { defaultValue: 'Refresh now' })}
            title={t('autoRefresh.refreshNow', { defaultValue: 'Refresh now' })}
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
          </Button>
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </div>
      </div>

      <BulkActionsBar selectedCount={deletableSelectedIds.length} onClear={clearSelection} actions={bulkActions} />

      {isEmpty && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('adminRoles.empty', { defaultValue: 'No roles' })}</h3>
              <p className="text-muted-foreground mx-auto max-w-2xl">
                {t('adminRoles.emptyDescription', { defaultValue: 'Create a role to assign granular permissions, limits, features, and access restrictions to admins.' })}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {isSearchEmpty && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('noResults', { defaultValue: 'No results' })}</h3>
              <p className="text-muted-foreground mx-auto max-w-2xl">{t('adminRoles.noSearchResults', { defaultValue: 'No roles match your search.' })}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {(isCurrentlyLoading || (!isEmpty && !isSearchEmpty)) &&
        (viewMode === 'grid' ? (
          <ListGeneratorGrid
            data={filteredRoles}
            getRowId={role => role.id}
            isLoading={isCurrentlyLoading}
            loadingRows={6}
            className="gap-4"
            enableSelection
            injectSelectionProps
            isRowSelectable={role => !isProtectedRole(role)}
            selectedRowIds={selectedRoleIds}
            onSelectionChange={ids => setSelectedRoleIds(ids.map(id => Number(id)))}
            showEmptyState={false}
            renderItem={role => <AdminRoleCard role={role} onEdit={handleEdit} onDuplicate={handleDuplicate} />}
            renderSkeleton={i => (
              <Card key={i} className="px-4 py-5">
                <div className="flex items-center gap-2 sm:gap-3">
                  <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-5 w-24 sm:w-32" />
                    <Skeleton className="h-4 w-20 sm:w-24" />
                  </div>
                  <Skeleton className="h-8 w-8 shrink-0" />
                </div>
              </Card>
            )}
          />
        ) : (
          <ListGenerator
            data={filteredRoles}
            columns={listColumns}
            getRowId={role => role.id}
            isLoading={isCurrentlyLoading}
            loadingRows={6}
            className="gap-3"
            onRowClick={handleEdit}
            enableSelection
            isRowSelectable={role => !isProtectedRole(role)}
            selectedRowIds={selectedRoleIds}
            onSelectionChange={ids => setSelectedRoleIds(ids.map(id => Number(id)))}
            showEmptyState={false}
          />
        ))}

      <AdminRoleModal isDialogOpen={isDialogOpen} onOpenChange={handleDialogChange} form={form} editingRole={!!editingRole} editingRoleId={editingRole?.id} readOnly={isReadOnly} />

      <BulkActionAlertDialog
        open={confirmBulkDelete}
        onOpenChange={setConfirmBulkDelete}
        title={t('adminRoles.bulkDeleteTitle', { defaultValue: 'Delete selected roles' })}
        description={t('adminRoles.bulkDeletePrompt', {
          count: deletableSelectedIds.length,
          defaultValue: 'Are you sure you want to delete {{count}} selected roles? This action cannot be undone.',
        })}
        actionLabel={t('delete', { defaultValue: 'Delete' })}
        onConfirm={handleBulkDelete}
        isPending={deleteRole.isPending}
        destructive
      />
    </div>
  )
}
