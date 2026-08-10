import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useGetClientTemplatesSimple, useGetUserSubscriptionProfilePreview, ClientTemplateType } from '@/service/api'
import { Code2, ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface UserSubscriptionProfilePreviewModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  userId: number
  username?: string
}

export function UserSubscriptionProfilePreviewModal({ isOpen, onOpenChange, userId, username }: UserSubscriptionProfilePreviewModalProps) {
  const { t } = useTranslation()
  const [profileId, setProfileId] = useState<string>()
  const {
    data: templates,
    isLoading: isLoadingTemplates,
    error: templatesError,
  } = useGetClientTemplatesSimple(undefined, {
    query: { enabled: isOpen, staleTime: 0, gcTime: 0 },
  })
  const profiles = useMemo(
    () => (templates?.templates ?? []).filter(template => template.template_type === ClientTemplateType.xray_profile || template.template_type === ClientTemplateType.singbox_profile),
    [templates?.templates],
  )
  const selectedProfileId = profileId ? Number(profileId) : 0
  const { data, error, isFetching } = useGetUserSubscriptionProfilePreview(userId, selectedProfileId, {
    query: { enabled: isOpen && Boolean(selectedProfileId), retry: false, staleTime: 0, gcTime: 0 },
  })

  useEffect(() => {
    if (!isOpen) setProfileId(undefined)
  }, [isOpen])

  const renderedConfig = useMemo(() => {
    if (!data) return ''
    return typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  }, [data])

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] max-w-full flex-col sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Code2 className="h-5 w-5" />
            {t('subscriptionProfiles.previewTitle')}
            {username && <span className="text-muted-foreground font-mono text-sm">{username}</span>}
          </DialogTitle>
          <DialogDescription>{t('subscriptionProfiles.previewDescription', { username })}</DialogDescription>
        </DialogHeader>

        <Alert>
          <ShieldAlert className="h-4 w-4" />
          <AlertDescription>{t('subscriptionProfiles.previewSensitive')}</AlertDescription>
        </Alert>

        <Select value={profileId} onValueChange={setProfileId} disabled={isLoadingTemplates}>
          <SelectTrigger>
            <SelectValue placeholder={t('subscriptionProfiles.selectProfile')} />
          </SelectTrigger>
          <SelectContent>
            {profiles.map(profile => (
              <SelectItem key={profile.id} value={String(profile.id)}>
                {profile.name} ({profile.template_type === ClientTemplateType.xray_profile ? 'Xray' : 'Sing-box'})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="bg-muted/20 min-h-0 flex-1 overflow-auto rounded-md border p-3">
          {!profileId && <p className="text-muted-foreground text-sm">{t('subscriptionProfiles.previewPrompt')}</p>}
          {templatesError && <p className="text-destructive text-sm">{t('subscriptionProfiles.profilesError')}</p>}
          {!isLoadingTemplates && !templatesError && profiles.length === 0 && <p className="text-muted-foreground text-sm">{t('subscriptionProfiles.noProfiles')}</p>}
          {isFetching && <p className="text-muted-foreground text-sm">{t('loading', { defaultValue: 'Loading…' })}</p>}
          {error && <p className="text-destructive text-sm">{t('subscriptionProfiles.previewError')}</p>}
          {!isFetching && !error && renderedConfig && <pre className="text-xs leading-5 break-all whitespace-pre-wrap">{renderedConfig}</pre>}
        </div>

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Close' })}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
