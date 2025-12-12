import React, { useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { useUpdateGeofiles, NodeResponse, GeoFilseRegion } from '@/service/api'
import { LoaderButton } from '../ui/loader-button'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'

interface UpdateGeofilesDialogProps {
  node: NodeResponse
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

export default function UpdateGeofilesDialog({ node, isOpen, onOpenChange }: UpdateGeofilesDialogProps) {
  const { t } = useTranslation()

  const GEO_REGIONS: { value: GeoFilseRegion; label: string }[] = [
    { value: 'iran', label: t('nodeModal.regions.iran', { defaultValue: 'Iran' }) },
    { value: 'china', label: t('nodeModal.regions.china', { defaultValue: 'China' }) },
    { value: 'russia', label: t('nodeModal.regions.russia', { defaultValue: 'Russia' }) },
  ]
  const dir = useDirDetection()
  const [selectedRegion, setSelectedRegion] = useState<GeoFilseRegion | undefined>(undefined)
  const updateGeofilesMutation = useUpdateGeofiles()

  React.useEffect(() => {
    if (isOpen) {
      setSelectedRegion(undefined)
    }
  }, [isOpen])

  const handleUpdate = async () => {
    try {
      const response = await updateGeofilesMutation.mutateAsync({
        nodeId: node.id,
        data: {
          region: selectedRegion,
        },
      })
      const message = (response as any)?.detail || t('nodeModal.updateGeofilesSuccess', { defaultValue: 'Geo files updated successfully' })
      toast.success(message)
      onOpenChange(false)
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
      queryClient.invalidateQueries({ queryKey: [`/api/node/${node.id}`] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.updateGeofilesFailed', {
          message: error?.message || 'Unknown error',
          defaultValue: 'Failed to update Geo files: {message}',
        }),
      )
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('sm:max-w-[500px]', dir === 'rtl' && 'sm:text-right')}>
        <DialogHeader className={cn(dir === 'rtl' && 'text-right')}>
          <DialogTitle className={cn(dir === 'rtl' && 'text-right')}>
            {t('nodeModal.updateGeofilesTitle', { defaultValue: 'Update Geofiles' })}
          </DialogTitle>
          <DialogDescription className={cn(dir === 'rtl' && 'text-right')}>
            {t('nodeModal.updateGeofilesDescription', {
              nodeName: node.name,
              defaultValue: `Update geofiles for node «${node.name}»`,
            })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className={cn('text-sm font-medium', dir === 'rtl' && 'text-right')}>
              {t('nodeModal.selectRegion', { defaultValue: 'Select Region' })}
            </label>
            <Select
              value={selectedRegion || 'all'}
              onValueChange={value => setSelectedRegion(value === 'all' ? undefined : (value as GeoFilseRegion))}
            >
              <SelectTrigger className={cn(dir === 'rtl' && 'text-right')}>
                <SelectValue placeholder={t('nodeModal.allRegions', { defaultValue: 'All Regions' })} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('nodeModal.allRegions', { defaultValue: 'All Regions' })}</SelectItem>
                {GEO_REGIONS.map(region => (
                  <SelectItem key={region.value} value={region.value}>
                    {region.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className={cn('text-xs text-muted-foreground', dir === 'rtl' && 'text-right')}>
              {t('nodeModal.updateGeofilesHint', {
                defaultValue: 'Leave empty to update all regions, or select a specific region',
              })}
            </p>
          </div>
        </div>

        <DialogFooter className='gap-2'>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={updateGeofilesMutation.isPending}>
            {t('cancel')}
          </Button>
          <LoaderButton
            className='!m-0'
            onClick={handleUpdate}
            disabled={updateGeofilesMutation.isPending}
            isLoading={updateGeofilesMutation.isPending}
            loadingText={t('nodeModal.updating', { defaultValue: 'Updating...' })}
          >
            {t('nodeModal.update', { defaultValue: 'Update' })}
          </LoaderButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

