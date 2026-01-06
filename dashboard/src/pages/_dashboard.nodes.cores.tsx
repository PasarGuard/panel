import { useCallback, useState, useMemo } from 'react'
import Cores from '@/components/cores/cores-list'
import { useGetAllCores, useDeleteCoreConfig, useCreateCoreConfig } from '@/service/api'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import CoreConfigModal, { coreConfigFormSchema, CoreConfigFormValues } from '@/components/dialogs/core-config-modal'
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { LoaderButton } from '@/components/ui/loader-button'
import { useQueryClient } from '@tanstack/react-query'

const defaultConfig = {
  log: {
    loglevel: 'error',
  },
  inbounds: [
    {
      tag: 'inbound Name',
      listen: '0.0.0.0',
      port: 1122,
      protocol: 'vless',
      settings: {
        clients: [],
        decryption: 'none',
      },
      streamSettings: {
        network: 'tcp',
        tcpSettings: {},
        security: 'none',
      },
      sniffing: {},
    },
  ],
} as const

export default function CoreSettings() {
  const { data: coresData } = useGetAllCores({})
  const queryClient = useQueryClient()
  const deleteCoreConfig = useDeleteCoreConfig()
  const createCoreMutation = useCreateCoreConfig()
  const { t } = useTranslation()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCoreId, setEditingCoreId] = useState<number | undefined>(undefined)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [coreToDelete, setCoreToDelete] = useState<string | null>(null)
  const [coreIdToDelete, setCoreIdToDelete] = useState<number | null>(null)

  const coreConfigForm = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema) as any,
    defaultValues: {
      name: '',
      config: JSON.stringify(defaultConfig, null, 2),
      excluded_inbound_ids: [],
      fallback_id: [],
      restart_nodes: true,
    },
  })

  const handleEditCore = useCallback(
    (coreId: string | number) => {
      const numericCoreId = Number(coreId)
      setEditingCoreId(numericCoreId)

      const coreToEdit = coresData?.cores?.find(core => core.id === numericCoreId)

      if (coreToEdit) {
        const excludedInboundIds = coreToEdit.exclude_inbound_tags || []

        const fallbackIds = coreToEdit.fallbacks_inbound_tags || []

        coreConfigForm.reset({
          name: coreToEdit.name,
          config: JSON.stringify(coreToEdit.config, null, 2),
          excluded_inbound_ids: excludedInboundIds,
          fallback_id: fallbackIds,
          restart_nodes: true,
        })
      } else {
        coreConfigForm.reset({
          name: 'Core Name',
          config: JSON.stringify(defaultConfig, null, 2),
          excluded_inbound_ids: [],
          fallback_id: [],
          restart_nodes: true,
        })
      }

      setIsModalOpen(true)
    },
    [coresData?.cores, coreConfigForm],
  )

  const handleDuplicateCore = useCallback(
    (coreId: string | number) => {
      const numericCoreId = Number(coreId)
      const coreToDuplicate = coresData?.cores?.find(core => core.id === numericCoreId)

      if (!coreToDuplicate) {
        toast.error(t('settings.cores.coreNotFound'))
        return
      }

      try {
        const newCore = {
          ...coreToDuplicate,
          id: undefined,
          name: `${coreToDuplicate.name} (Copy)`,
        }

        createCoreMutation.mutateAsync(
          {
            data: newCore,
          },
          {
            onSuccess: () => {
              toast.success(
                t('settings.cores.duplicateSuccess', {
                  name: coreToDuplicate.name,
                }),
              )
              queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
            },
            onError: error => {
              toast.error(
                error.message ||
                  t('settings.cores.duplicateFailed', {
                    name: coreToDuplicate.name,
                  }),
              )
            },
          },
        )
      } catch (error) {
        toast.error(
          t('settings.cores.duplicateFailed', {
            name: coreToDuplicate.name,
          }),
        )
      }
    },
    [coresData?.cores, createCoreMutation, queryClient, t],
  )

  const handleDeleteCore = useCallback((coreName: string, coreId: number) => {
    setCoreToDelete(coreName)
    setCoreIdToDelete(coreId)
    setDeleteDialogOpen(true)
  }, [])

  const confirmDeleteCore = useCallback(() => {
    if (!coreToDelete || coreIdToDelete === null) return

    deleteCoreConfig.mutate(
      {
        coreId: coreIdToDelete,
        params: { restart_nodes: true },
      },
      {
        onSuccess: () => {
          toast.success(
            t('settings.cores.deleteSuccess', {
              name: `Core ${coreToDelete}`,
            }),
          )
          setDeleteDialogOpen(false)
          setCoreToDelete(null)
          queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
        },
        onError: (error: any) => {
          // Extract backend error message
          let errorMessage = t('settings.cores.deleteFailed', {
            name: `Core ${coreToDelete}`,
          })

          const responseData = error?.response?._data || error?.response?.data || error?.data
          if (responseData?.detail) {
            if (typeof responseData.detail === 'string') {
              errorMessage = responseData.detail
            } else if (Array.isArray(responseData.detail) && responseData.detail.length > 0) {
              errorMessage = responseData.detail[0]?.msg || responseData.detail[0] || errorMessage
            }
          } else if (error?.message) {
            errorMessage = error.message
          }

          toast.error(errorMessage)
          setDeleteDialogOpen(false)
          setCoreToDelete(null)
        },
      },
    )
  }, [coreToDelete, coreIdToDelete, deleteCoreConfig, queryClient, t])

  const handleModalClose = useCallback(() => {
    setIsModalOpen(false)
    setEditingCoreId(undefined)
    coreConfigForm.reset()
  }, [coreConfigForm])

  const handleDeleteDialogClose = useCallback(() => {
    setDeleteDialogOpen(false)
    setCoreToDelete(null)
    setCoreIdToDelete(null)
  }, [])

  const cores = useMemo(() => coresData?.cores ?? [], [coresData?.cores])

  return (
    <div className="flex flex-col">
      <Cores cores={cores} onEditCore={handleEditCore} onDuplicateCore={handleDuplicateCore} onDeleteCore={handleDeleteCore} isDialogOpen={isModalOpen} onOpenChange={setIsModalOpen} />

      <CoreConfigModal isDialogOpen={isModalOpen} onOpenChange={handleModalClose} form={coreConfigForm} editingCore={!!editingCoreId} editingCoreId={editingCoreId} />

      <AlertDialog open={deleteDialogOpen} onOpenChange={handleDeleteDialogClose}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.cores.delete')}</AlertDialogTitle>
            <AlertDialogDescription>
              <span dangerouslySetInnerHTML={{ __html: t('core.deleteConfirm', { name: coreToDelete }) }} />
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleDeleteDialogClose} disabled={deleteCoreConfig.isPending}>
              {t('cancel')}
            </AlertDialogCancel>
            <LoaderButton variant="destructive" onClick={confirmDeleteCore} disabled={deleteCoreConfig.isPending} isLoading={deleteCoreConfig.isPending} loadingText={t('removing')}>
              {t('delete')}
            </LoaderButton>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
