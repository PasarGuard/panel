import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { getGetHostCustomizationsQueryKey, HostCustomization, useGetHostCustomizations, useModifyHostCustomization } from '@/service/api'
import { getErrorMessage } from '@/utils/error-utils'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

function HostCustomizationCard({ host }: { host: HostCustomization }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [remark, setRemark] = useState(host.custom_remark ?? '')
  const [isDisabled, setIsDisabled] = useState(host.is_disabled ?? false)
  const modifyCustomization = useModifyHostCustomization()

  useEffect(() => {
    setRemark(host.custom_remark ?? '')
    setIsDisabled(host.is_disabled ?? false)
  }, [host.custom_remark, host.is_disabled])

  const isDirty = remark.trim() !== (host.custom_remark ?? '') || isDisabled !== (host.is_disabled ?? false)

  const save = async (data: { remark: string; is_disabled: boolean }) => {
    try {
      await modifyCustomization.mutateAsync({ hostId: host.host_id, data: { remark: data.remark.trim() || null, is_disabled: data.is_disabled } })
      await queryClient.invalidateQueries({ queryKey: getGetHostCustomizationsQueryKey() })
      toast.success(t('hostCustomizations.saved', { defaultValue: 'Host updated for your users' }))
    } catch (error) {
      toast.error(getErrorMessage(error))
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-medium" dir="auto">
              {host.custom_remark || host.remark}
            </p>
            {host.custom_remark && (
              <p className="text-muted-foreground truncate text-xs" dir="auto">
                {t('hostCustomizations.original', { defaultValue: 'Original: {{remark}}', remark: host.remark })}
              </p>
            )}
            {host.inbound_tag && <p className="text-muted-foreground truncate text-xs">{host.inbound_tag}</p>}
          </div>
          {host.host_disabled && <Badge variant="secondary">{t('hostCustomizations.disabledByOwner', { defaultValue: 'Disabled by owner' })}</Badge>}
        </div>
        <Input
          value={remark}
          onChange={event => setRemark(event.target.value)}
          placeholder={host.remark}
          maxLength={256}
          dir="auto"
          aria-label={t('hostCustomizations.customRemark', { defaultValue: 'Name for your users' })}
        />
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={!isDisabled} onCheckedChange={checked => setIsDisabled(!checked)} />
            {t('hostCustomizations.visible', { defaultValue: 'Show to my users' })}
          </label>
          <LoaderButton size="sm" disabled={!isDirty} isLoading={modifyCustomization.isPending} onClick={() => save({ remark, is_disabled: isDisabled })}>
            {t('save')}
          </LoaderButton>
        </div>
      </CardContent>
    </Card>
  )
}

export default function HostCustomizationsList() {
  const { t } = useTranslation()
  const { data, isLoading } = useGetHostCustomizations()

  if (isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-40 w-full" />
        ))}
      </div>
    )
  }

  if (!data?.length) {
    return <p className="text-muted-foreground text-sm">{t('hostCustomizations.empty', { defaultValue: 'No hosts are available to you yet.' })}</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground text-sm">
        {t('hostCustomizations.description', {
          defaultValue: 'Rename or hide hosts for your own users. Host settings stay managed by the owner.',
        })}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data.map(host => (
          <HostCustomizationCard key={host.host_id} host={host} />
        ))}
      </div>
    </div>
  )
}
