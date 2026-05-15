import { useCallback, useMemo, useState } from 'react'
import Cores from '@/features/nodes/components/cores/cores-list'
import { useGetAllCores, useDeleteCoreConfig, useCreateCoreConfig } from '@/service/api'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { LoaderButton } from '@/components/ui/loader-button'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'

export default function CoresIndexPage() {
  const { data: coresData } = useGetAllCores({})
  const queryClient = useQueryClient()
  const deleteCoreConfig = useDeleteCoreConfig()
  const createCoreMutation = useCreateCoreConfig()
  const { t } = useTranslation()
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [coreToDelete, setCoreToDelete] = useState<string | null>(null)
  const [coreIdToDelete, setCoreIdToDelete] = useState<number | null>(null)

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
              queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
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
      } catch {
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
          queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
        },
        onError: (error: any) => {
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

  const handleDeleteDialogClose = useCallback(() => {
    setDeleteDialogOpen(false)
    setCoreToDelete(null)
    setCoreIdToDelete(null)
  }, [])

  const cores = useMemo(() => coresData?.cores ?? [], [coresData?.cores])

  return (
    <div className="flex flex-col px-4">
      <Cores cores={cores} onDuplicateCore={handleDuplicateCore} onDeleteCore={handleDeleteCore} />

      <AlertDialog open={deleteDialogOpen} onOpenChange={handleDeleteDialogClose}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              {t('settings.cores.delete')}
            </AlertDialogTitle>
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
