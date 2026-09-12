import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { findUnknownApiServices, getSelectedOptional, OPTIONAL_API_SERVICES, REQUIRED_API_SERVICES, setRawOptionalService } from '@/lib/xray-api-services'
import type { Profile } from '@pasarguard/xray-config-kit'
import { Webhook } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

// The structured editor keeps unmodeled top-level keys (incl. `api`) on
// `profile.raw.topLevel` (see UNMODELED_TOP_LEVEL_KEYS_TO_PRESERVE in xray-adapter.ts),
// which is structurally a config object for the api-services helpers.
function readTopLevel(profile: Profile): Record<string, unknown> {
  return (profile.raw?.topLevel ?? {}) as Record<string, unknown>
}

function withApiService(profile: Profile, service: string, enabled: boolean): Profile {
  return { ...profile, raw: setRawOptionalService(profile.raw, service, enabled) } as Profile
}

export function XrayApiSection() {
  const { t } = useTranslation()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateXrayProfile = useCoreEditorStore(s => s.updateXrayProfile)

  const { selected, unknown } = useMemo(() => {
    const topLevel = profile ? readTopLevel(profile) : {}
    return {
      selected: getSelectedOptional(topLevel),
      unknown: findUnknownApiServices(topLevel),
    }
  }, [profile])

  if (!profile) return null

  const toggle = (service: string, enabled: boolean) => {
    updateXrayProfile(p => withApiService(p, service, enabled))
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Webhook className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
            {t('coreEditor.api.title', { defaultValue: 'API Services' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-muted-foreground text-xs">
            {t('coreEditor.api.hint', {
              defaultValue: 'gRPC API services exposed by this core. The node always enables the required services; enable optional ones as needed.',
            })}
          </p>
          <div className="space-y-2 rounded-md border p-3">
            {REQUIRED_API_SERVICES.map(svc => (
              <label key={svc} className="flex items-center gap-2 opacity-60">
                <Checkbox checked disabled />
                <span className="text-sm">{svc}</span>
                <span className="text-muted-foreground text-xs">{t('coreEditor.api.alwaysOn', { defaultValue: 'always on' })}</span>
              </label>
            ))}
            {OPTIONAL_API_SERVICES.map(svc => (
              <label key={svc} className="flex cursor-pointer items-center gap-2">
                <Checkbox checked={selected.includes(svc)} onCheckedChange={checked => toggle(svc, checked === true)} />
                <span className="text-sm">{svc}</span>
              </label>
            ))}
          </div>
          {unknown.length > 0 && (
            <p className="text-destructive text-xs">
              {t('coreEditor.api.unknown', {
                defaultValue: 'Unrecognized API service(s): {{names}}. Fix them in the Advanced tab.',
                names: unknown.join(', '),
              })}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
