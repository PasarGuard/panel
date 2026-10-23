import ClientProfile from '@/features/templates/components/client-profile'
import { useBulkDeleteClientProfiles, useGetClientProfiles, ClientProfileResponse } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import ClientProfileModal from '@/features/templates/dialogs/client-profile-modal'
import { clientProfileFormDefaultValues, clientProfileToFormValues, createClientProfileFormResolver, type ClientProfileFormValues } from '@/features/templates/forms/client-profile-form'
import { useState, useMemo, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { RefreshCw, Search, X } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'
import { useClientProfilesListColumns } from '@/features/templates/components/use-client-profiles-list-columns'
import { getApiErrorDetail, invalidateClientProfileQueries } from '@/features/templates/components/use-client-profile-options'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { BulkActionsBar } from '@/features/users/components/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/features/users/components/bulk-action-alert-dialog'
import { toast } from 'sonner'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'

export default function ClientProfiles() {
  const { admin } = useAdmin()
  const canCreateProfiles = hasPermission(admin, 'client_profiles', 'create')
  const canUpdateProfiles = hasPermission(admin, 'client_profiles', 'update')
  const canDeleteProfiles = hasPermission(admin, 'client_profiles', 'delete')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingProfile, setEditingProfile] = useState<ClientProfileResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:client-profiles')
  const [selectedProfileIds, setSelectedProfileIds] = useState<number[]>([])
  const [bulkAction, setBulkAction] = useState<'delete' | null>(null)
  const { data, isLoading, isFetching, refetch } = useGetClientProfiles()
  const bulkDeleteClientProfilesMutation = useBulkDeleteClientProfiles()
  const { t } = useTranslation()
  const dir = useDirDetection()
  const form = useForm<ClientProfileFormValues>({
    resolver: createClientProfileFormResolver(t),
    defaultValues: structuredClone(clientProfileFormDefaultValues),
  })

  useEffect(() => {
    const handleOpenDialog = () => {
      if (!canCreateProfiles) return
      setEditingProfile(null)
      form.reset(structuredClone(clientProfileFormDefaultValues))
      setIsDialogOpen(true)
    }
    window.addEventListener('openClientProfileDialog', handleOpenDialog)
    return () => window.removeEventListener('openClientProfileDialog', handleOpenDialog)
  }, [canCreateProfiles, form])

  const handleEdit = (profile: ClientProfileResponse) => {
    if (!canUpdateProfiles) return

    setEditingProfile(profile)
    form.reset(clientProfileToFormValues(profile))
    setIsDialogOpen(true)
  }

  const filteredProfiles = useMemo(() => {
    const profiles = data?.profiles || []
    if (!searchQuery.trim()) return profiles
    const query = searchQuery.toLowerCase().trim()
    return profiles.filter((profile: ClientProfileResponse) => profile.name?.toLowerCase().includes(query) || profile.note?.toLowerCase().includes(query))
  }, [data, searchQuery])

  const listColumns = useClientProfilesListColumns({
    onEdit: handleEdit,
    canCreate: canCreateProfiles,
    canUpdate: canUpdateProfiles,
    canDelete: canDeleteProfiles,
  })
  const clearSelection = () => {
    setSelectedProfileIds([])
  }

  const handleBulkDelete = async () => {
    if (!canDeleteProfiles || !selectedProfileIds.length) return

    try {
      const response = await bulkDeleteClientProfilesMutation.mutateAsync({
        data: {
          ids: selectedProfileIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('clientProfiles.bulkDeleteSuccess', {
          count: response.count,
          defaultValue: '{{count}} client profiles deleted.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateClientProfileQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description:
          getApiErrorDetail(error) ||
          t('clientProfiles.bulkDeleteFailed', {
            defaultValue: 'Failed to delete the selected client profiles.',
          }),
      })
    }
  }

  const isCurrentlyLoading = isLoading || (isFetching && !data)
  const isEmpty = !isCurrentlyLoading && filteredProfiles.length === 0 && !searchQuery.trim()
  const isSearchEmpty = !isCurrentlyLoading && filteredProfiles.length === 0 && searchQuery.trim() !== ''

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full flex-1 space-y-4 px-4">
        <div dir={dir} className="flex items-center gap-2 pt-4 md:gap-4">
          <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
            <Search className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'text-muted-foreground top-1/2 h-4 w-4 -translate-y-1/2')} />
            <Input placeholder={t('search')} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className={cn('pr-10 pl-8', dir === 'rtl' && 'pr-8 pl-10')} />
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
              onClick={() => refetch()}
              className={cn('h-9 w-9 rounded-lg border', isFetching && 'opacity-70')}
              aria-label={t('autoRefresh.refreshNow')}
              title={t('autoRefresh.refreshNow')}
            >
              <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
            </Button>
            <ViewToggle value={viewMode} onChange={setViewMode} />
          </div>
        </div>
        {canDeleteProfiles && (
          <BulkActionsBar selectedCount={selectedProfileIds.length} onClear={clearSelection} onDelete={selectedProfileIds.length > 0 ? () => setBulkAction('delete') : undefined} />
        )}

        {(isCurrentlyLoading || filteredProfiles.length > 0) &&
          (viewMode === 'grid' ? (
            <ListGeneratorGrid
              data={filteredProfiles}
              getRowId={profile => profile.id}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="gap-4"
              gridClassName=""
              gridStyle={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
              enableSelection={canDeleteProfiles}
              injectSelectionProps={canDeleteProfiles}
              selectedRowIds={selectedProfileIds}
              onSelectionChange={ids => setSelectedProfileIds(ids.map(id => Number(id)))}
              showEmptyState={false}
              renderItem={profile => <ClientProfile onEdit={handleEdit} profile={profile} canCreate={canCreateProfiles} canUpdate={canUpdateProfiles} canDelete={canDeleteProfiles} />}
              renderSkeleton={i => (
                <Card key={i} className="px-4 py-5 sm:px-5 sm:py-6">
                  <div className="flex items-start justify-between gap-2 sm:gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-x-2">
                        <Skeleton className="h-5 w-24 sm:w-32" />
                      </div>
                      <div className="mt-2">
                        <Skeleton className="h-4 w-16" />
                      </div>
                    </div>
                    <Skeleton className="h-8 w-8 shrink-0" />
                  </div>
                </Card>
              )}
            />
          ) : (
            <ListGenerator
              data={filteredProfiles}
              columns={listColumns}
              getRowId={profile => profile.id}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="gap-3"
              onRowClick={canUpdateProfiles ? handleEdit : undefined}
              enableSelection={canDeleteProfiles}
              selectedRowIds={selectedProfileIds}
              onSelectionChange={ids => setSelectedProfileIds(ids.map(id => Number(id)))}
              showEmptyState={false}
            />
          ))}

        {isEmpty && !isCurrentlyLoading && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('clientProfiles.noProfiles', { defaultValue: 'No client profiles yet' })}</h3>
                <p className="text-muted-foreground mx-auto max-w-2xl">
                  {t('clientProfiles.noProfilesDescription', {
                    defaultValue: 'A profile groups client templates and subscription settings. Create one and assign it to users or user templates.',
                  })}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {isSearchEmpty && !isCurrentlyLoading && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                <p className="text-muted-foreground mx-auto max-w-2xl">{t('clientProfiles.noSearchResults', { defaultValue: 'No client profiles match your search.' })}</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {(canCreateProfiles || canUpdateProfiles) && (
        <ClientProfileModal
          isDialogOpen={isDialogOpen}
          onOpenChange={open => {
            if (open && editingProfile && !canUpdateProfiles) return
            if (open && !editingProfile && !canCreateProfiles) return
            if (!open) {
              setEditingProfile(null)
              form.reset(structuredClone(clientProfileFormDefaultValues))
            }
            setIsDialogOpen(open)
          }}
          form={form}
          editingProfile={!!editingProfile}
          editingProfileId={editingProfile?.id}
        />
      )}
      {canDeleteProfiles && (
        <BulkActionAlertDialog
          open={bulkAction === 'delete'}
          onOpenChange={open => setBulkAction(open ? 'delete' : null)}
          title={t('clientProfiles.bulkDeleteTitle', { defaultValue: 'Delete selected client profiles' })}
          description={t('clientProfiles.bulkDeletePrompt', {
            count: selectedProfileIds.length,
            defaultValue: 'Delete {{count}} selected client profiles? Their users will get the default subscription settings. This cannot be undone.',
          })}
          actionLabel={t('delete')}
          onConfirm={handleBulkDelete}
          isPending={bulkDeleteClientProfilesMutation.isPending}
          destructive
        />
      )}
    </div>
  )
}
