import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { Card, CardContent } from '@/components/ui/card'
import ApiKeysTable from '@/features/api-keys/components/api-keys-table'
import ApiKeyModal from '@/features/api-keys/dialogs/api-key-modal'
import {
  APIKeyResponse,
  useRemoveApiKey,
  useRevokeApiKey,
  useListApiKeys,
  getListApiKeysQueryKey,
  APIKeyStatus,
} from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiKeyFilters } from '@/features/api-keys/components/api-key-filters'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  apiKeyAdvanceSearchFormSchema,
  type ApiKeyAdvanceSearchFormValue,
} from '@/features/api-keys/forms/api-key-advance-search-form'
import ApiKeyAdvanceSearchModal from '@/features/api-keys/dialogs/api-key-advance-search-modal'
import { ApiKeyDeleteDialog, ApiKeyRevokeDialog, ApiKeySecretDialog } from '@/features/api-keys/dialogs/api-key-action-dialogs'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'

export default function ApiKeysPage() {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canCreateApiKeys = hasPermission(admin, 'api_keys', 'create')
  const canUpdateApiKeys = hasPermission(admin, 'api_keys', 'update')
  const canDeleteApiKeys = hasPermission(admin, 'api_keys', 'delete')
  const [editingApiKey, setEditingApiKey] = useState<APIKeyResponse | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  
  const [keyToDelete, setKeyToDelete] = useState<APIKeyResponse | null>(null)
  const [keyToRevoke, setKeyToRevoke] = useState<APIKeyResponse | null>(null)
  const [newReissuedKey, setNewReissuedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:api-keys')
  const [filters, setFilters] = useState<{ status?: APIKeyStatus[]; key_id?: number }>({})
  const { search, debouncedSearch, setSearch } = useDebouncedSearch('', 300)
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)

  const advanceSearchForm = useForm<ApiKeyAdvanceSearchFormValue>({
    resolver: zodResolver(apiKeyAdvanceSearchFormSchema),
    defaultValues: {
      status: [],
      key_id: undefined,
    },
  })

  const {
    data: apiKeysResponse,
    isLoading,
    isFetching,
    refetch,
  } = useListApiKeys({
    name: debouncedSearch || undefined,
    status: filters.status?.[0],
    key_id: filters.key_id,
  })

  const apiKeys = apiKeysResponse?.api_keys || []
  const hasActiveSearch = (search || '').trim() !== '' || (debouncedSearch || '').trim() !== ''
  const hasAdvancedFilters = !!filters.status?.length || filters.key_id !== undefined
  const isCurrentlyLoading = isLoading || (isFetching && !apiKeysResponse)
  const isEmpty = !isCurrentlyLoading && apiKeys.length === 0 && !hasActiveSearch && !hasAdvancedFilters
  const isSearchEmpty = !isCurrentlyLoading && apiKeys.length === 0 && (hasActiveSearch || hasAdvancedFilters)

  const queryClient = useQueryClient()
  const deleteMutation = useRemoveApiKey({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListApiKeysQueryKey() })
      },
    },
  })
  const revokeMutation = useRevokeApiKey({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListApiKeysQueryKey() })
      },
    },
  })

  const handleEdit = (apiKey: APIKeyResponse) => {
    if (!canUpdateApiKeys) return

    setEditingApiKey(apiKey)
    setIsModalOpen(true)
  }

  const handleDelete = async () => {
    if (!keyToDelete || !canDeleteApiKeys) return
    try {
      await deleteMutation.mutateAsync({ keyId: keyToDelete.id })
      toast.success(t('apiKeys.deleteSuccess'))
      setKeyToDelete(null)
    } catch (error: any) {
      toast.error(t('apiKeys.deleteFailed'), {
        description: error?.data?.detail || error?.message,
      })
    }
  }

  const handleRevoke = async () => {
    if (!keyToRevoke || !canDeleteApiKeys) return
    try {
      const response = await revokeMutation.mutateAsync({ keyId: keyToRevoke.id })
      setNewReissuedKey(response.api_key)
      toast.success(t('apiKeys.revokeSuccess'))
      setKeyToRevoke(null)
    } catch (error: any) {
      toast.error(t('apiKeys.revokeFailed'), {
        description: error?.data?.detail || error?.message,
      })
    }
  }

  const copyToClipboard = () => {
    if (newReissuedKey) {
      navigator.clipboard.writeText(newReissuedKey)
      setCopied(true)
      toast.success(t('apiKeys.apiKeyCopySuccess'))
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleAdvanceSearchSubmit = (values: ApiKeyAdvanceSearchFormValue) => {
    setFilters(prev => ({
      ...prev,
      status: values.status && values.status.length > 0 ? values.status : undefined,
      key_id: values.key_id,
    }))
    setIsAdvanceSearchOpen(false)
  }

  const handleClearAdvanceSearch = () => {
    advanceSearchForm.reset({
      status: [],
      key_id: undefined,
    })
    setFilters(prev => ({
      ...prev,
      status: undefined,
      key_id: undefined,
    }))
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader
          title="apiKeys.title"
          description="apiKeys.description"
          buttonIcon={canCreateApiKeys ? Plus : undefined}
          buttonText={canCreateApiKeys ? 'apiKeys.createKey' : undefined}
          onButtonClick={canCreateApiKeys ? () => {
            setEditingApiKey(null)
            setIsModalOpen(true)
          } : undefined}
        />
        <Separator />
      </div>

      <div className="w-full p-4">
        <div
          className="flex flex-col gap-4 animate-slide-up transform-gpu"
          style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
        >
          <ApiKeyFilters
            search={search}
            onSearchChange={setSearch}
            isFetching={isFetching}
            onRefresh={() => refetch()}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            filters={{
              status: filters.status?.[0],
            }}
            onFilterChange={(newFilters) => {
              if (!Object.keys(newFilters).length) {
                handleClearAdvanceSearch()
              } else {
                setFilters(prev => ({ ...prev, ...newFilters, status: newFilters.status ? [newFilters.status as APIKeyStatus] : undefined }))
              }
            }}
            onAdvanceSearchOpen={() => setIsAdvanceSearchOpen(true)}
          />

          {(isCurrentlyLoading || apiKeys.length > 0) && (
            <ApiKeysTable
              onEdit={handleEdit}
              onDelete={setKeyToDelete}
              onRevoke={setKeyToRevoke}
              isCardView={viewMode === 'grid'}
              apiKeys={apiKeys}
              isLoading={isCurrentlyLoading}
              canUpdate={canUpdateApiKeys}
              canDelete={canDeleteApiKeys}
            />
          )}

          {isEmpty && (
            <Card className="mb-12">
              <CardContent className="p-8 text-center">
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t('apiKeys.noKeys', { defaultValue: 'No API keys configured' })}</h3>
                  <p className="text-muted-foreground mx-auto max-w-2xl">
                    {t('apiKeys.noKeysDescription', { defaultValue: 'Create an API key to allow programmatic access.' })}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {isSearchEmpty && (
            <Card className="mb-12">
              <CardContent className="p-8 text-center">
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                  <p className="text-muted-foreground mx-auto max-w-2xl">
                    {t('apiKeys.noSearchResults', { defaultValue: 'No API keys match your search criteria. Try adjusting your search terms or filters.' })}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {(canCreateApiKeys || canUpdateApiKeys) && (
        <ApiKeyModal
          isDialogOpen={isModalOpen}
          onOpenChange={setIsModalOpen}
          editingApiKey={editingApiKey}
        />
      )}

      <ApiKeyAdvanceSearchModal
        isDialogOpen={isAdvanceSearchOpen}
        onOpenChange={setIsAdvanceSearchOpen}
        form={advanceSearchForm}
        onSubmit={handleAdvanceSearchSubmit}
      />

      <ApiKeyDeleteDialog
        apiKey={keyToDelete}
        onOpenChange={open => {
          if (!open) setKeyToDelete(null)
        }}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />

      <ApiKeyRevokeDialog
        apiKey={keyToRevoke}
        onOpenChange={open => {
          if (!open) setKeyToRevoke(null)
        }}
        onConfirm={handleRevoke}
        isPending={revokeMutation.isPending}
      />

      <ApiKeySecretDialog
        apiKey={newReissuedKey}
        copied={copied}
        onCopy={copyToClipboard}
        onOpenChange={open => {
          if (!open) {
            setNewReissuedKey(null)
            setCopied(false)
          }
        }}
      />
    </div>
  )
}
