import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Input } from '@/components/ui/input'
import { Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ApiKeyFilters } from '@/features/api-keys/components/api-key-filters'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  apiKeyAdvanceSearchFormSchema,
  type ApiKeyAdvanceSearchFormValue,
} from '@/features/api-keys/forms/api-key-advance-search-form'
import ApiKeyAdvanceSearchModal from '@/features/api-keys/dialogs/api-key-advance-search-modal'

export default function ApiKeysPage() {
  const { t } = useTranslation()
  const [editingApiKey, setEditingApiKey] = useState<APIKeyResponse | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  
  const [keyToDelete, setKeyToDelete] = useState<APIKeyResponse | null>(null)
  const [keyToRevoke, setKeyToRevoke] = useState<APIKeyResponse | null>(null)
  const [newReissuedKey, setNewReissuedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const [isCardView, setIsCardView] = useState(false)
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
    setEditingApiKey(apiKey)
    setIsModalOpen(true)
  }

  const handleDelete = async () => {
    if (!keyToDelete) return
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
    if (!keyToRevoke) return
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
          buttonIcon={Plus}
          buttonText="apiKeys.createKey"
          onButtonClick={() => {
            setEditingApiKey(null)
            setIsModalOpen(true)
          }}
        />
        <Separator />
      </div>

      <div className="w-full px-4 pt-2">
        <div
          className="flex flex-col gap-4 animate-slide-up transform-gpu"
          style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
        >
          <ApiKeyFilters
            search={search}
            onSearchChange={setSearch}
            isFetching={isFetching}
            onRefresh={() => refetch()}
            viewMode={isCardView ? 'grid' : 'list'}
            onViewModeChange={(mode) => setIsCardView(mode === 'grid')}
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

          <ApiKeysTable
            onEdit={handleEdit}
            onDelete={setKeyToDelete}
            onRevoke={setKeyToRevoke}
            isCardView={isCardView}
            apiKeys={apiKeys}
            isLoading={isLoading}
          />
        </div>
      </div>

      <ApiKeyModal
        isOpen={isModalOpen}
        onOpenChange={setIsModalOpen}
        editingApiKey={editingApiKey}
      />

      <ApiKeyAdvanceSearchModal
        isDialogOpen={isAdvanceSearchOpen}
        onOpenChange={setIsAdvanceSearchOpen}
        form={advanceSearchForm}
        onSubmit={handleAdvanceSearchSubmit}
      />

      <AlertDialog open={!!keyToDelete} onOpenChange={() => setKeyToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('apiKeys.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('apiKeys.deletePrompt', { name: keyToDelete?.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
            >
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!keyToRevoke} onOpenChange={() => setKeyToRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('apiKeys.revokeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('apiKeys.revokePrompt')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevoke}>
              {t('confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!newReissuedKey} onOpenChange={() => setNewReissuedKey(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('apiKeys.apiKey')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('apiKeys.apiKeyShowWarning')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex items-center gap-2 py-4">
            <Input
              readOnly
              value={newReissuedKey || ''}
              className="font-mono"
            />
            <Button size="icon" variant="outline" onClick={copyToClipboard}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setNewReissuedKey(null)}>
              {t('close')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
