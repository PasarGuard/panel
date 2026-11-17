import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { addGeodataPresetAssets, geodataObject, geodataPresetGroups, setProfileGeodata, validateXrayGeodata } from '@/features/core-editor/kit/xray-geodata'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import useDirDetection from '@/hooks/use-dir-detection'
import type { JsonObject } from '@pasarguard/xray-config-kit'
import { ChevronDown, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function XrayGeodataSection() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateProfile = useCoreEditorStore(s => s.updateXrayProfile)
  if (!profile) return null

  const raw = profile.raw?.topLevel?.geodata
  const geodata = geodataObject(raw)
  const assets = Array.isArray(geodata?.assets) ? geodata.assets : []
  const outboundTag = typeof geodata?.outbound === 'string' ? geodata.outbound : ''
  const outboundTags = new Set(profile.outbounds?.flatMap(outbound => (outbound.tag ? [outbound.tag] : [])))
  // Keep saved tags visible if an outbound was renamed or removed.
  if (outboundTag) outboundTags.add(outboundTag)
  const issues = validateXrayGeodata(raw)
  const update = (value?: JsonObject) => updateProfile(p => setProfileGeodata(p, value))
  const setField = (field: 'cron' | 'outbound', value: string) => {
    const next = { ...geodata }
    if (value === '') delete next[field]
    else next[field] = value
    update(next)
  }

  return (
    <div className="space-y-5 rounded-lg border p-4">
      <div className="flex justify-between items-center gap-3">
        <Label htmlFor="xray-geodata-enabled">{t('coreEditor.geodata.configure')}</Label>
        <Switch id="xray-geodata-enabled" checked={raw != null} onCheckedChange={enabled => update(enabled ? {} : undefined)} />
      </div>
      {raw != null && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="xray-geodata-cron">{t('coreEditor.geodata.cron')}</Label>
              <Input
                id="xray-geodata-cron"
                dir="ltr"
                placeholder="0 4 * * *"
                value={typeof geodata?.cron === 'string' ? geodata.cron : ''}
                onChange={event => setField('cron', event.target.value)}
                aria-describedby="xray-geodata-cron-hint"
              />
              <p id="xray-geodata-cron-hint" className="text-muted-foreground text-xs">
                {t('coreEditor.geodata.cronHint')}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="xray-geodata-outbound">{t('coreEditor.geodata.outbound')}</Label>
              <Select dir={dir} value={outboundTag ? `tag:${outboundTag}` : 'routing'} onValueChange={value => setField('outbound', value === 'routing' ? '' : value.slice(4))}>
                <SelectTrigger id="xray-geodata-outbound" aria-describedby="xray-geodata-outbound-hint">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="routing">{t('coreEditor.geodata.noOutbound')}</SelectItem>
                  {Array.from(outboundTags, tag => (
                    <SelectItem key={tag} value={`tag:${tag}`}>
                      {tag}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p id="xray-geodata-outbound-hint" className="text-muted-foreground text-xs">
                {t('coreEditor.geodata.outboundHint')}
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium">{t('coreEditor.geodata.assets')}</h3>
              <div className="flex flex-wrap gap-2">
                <DropdownMenu dir={dir}>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" type="button" variant="outline">
                      {t('coreEditor.geodata.addPreset')}
                      <ChevronDown aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-44">
                    {Object.entries(geodataPresetGroups).map(([region, presets], index) => (
                      <DropdownMenuGroup key={region} aria-labelledby={`geodata-preset-${region}`}>
                        {index > 0 && <DropdownMenuSeparator />}
                        <DropdownMenuLabel id={`geodata-preset-${region}`} className="text-muted-foreground text-xs">
                          {t(`nodeModal.regions.${region}`)}
                        </DropdownMenuLabel>
                        {presets.map(preset => {
                          const nextAssets = addGeodataPresetAssets(assets, preset)
                          return (
                            <DropdownMenuItem key={preset.owner} disabled={nextAssets.length === assets.length} onSelect={() => update({ ...geodata, assets: nextAssets })}>
                              {preset.owner}
                            </DropdownMenuItem>
                          )
                        })}
                      </DropdownMenuGroup>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button size="sm" type="button" variant="outline" onClick={() => update({ ...geodata, assets: [...assets, { url: '', file: '' }] })}>
                  <Plus aria-hidden />
                  {t('coreEditor.geodata.addAsset')}
                </Button>
              </div>
            </div>
            <p className="text-muted-foreground text-xs">{t('coreEditor.geodata.assetsHint')}</p>
            {assets.map((value, index) => {
              const asset = geodataObject(value)
              const setAssetField = (field: 'url' | 'file', text: string) => {
                update({ ...geodata, assets: assets.map((entry, i) => (i === index ? { ...asset, [field]: text } : entry)) })
              }
              return (
                <div key={index} className="grid items-end gap-3 rounded-md border p-3 sm:grid-cols-[2fr_1fr_auto]">
                  <div className="min-w-0 space-y-2">
                    <Label htmlFor={`xray-geodata-url-${index}`}>{t('coreEditor.geodata.url')}</Label>
                    <Input id={`xray-geodata-url-${index}`} type="url" dir="ltr" value={typeof asset?.url === 'string' ? asset.url : ''} onChange={event => setAssetField('url', event.target.value)} />
                  </div>
                  <div className="min-w-0 space-y-2">
                    <Label htmlFor={`xray-geodata-file-${index}`}>{t('coreEditor.geodata.file')}</Label>
                    <Input
                      id={`xray-geodata-file-${index}`}
                      dir="ltr"
                      placeholder="geoip.dat"
                      value={typeof asset?.file === 'string' ? asset.file : ''}
                      onChange={event => setAssetField('file', event.target.value)}
                    />
                  </div>
                  <Button
                    size="icon"
                    type="button"
                    variant="ghost"
                    aria-label={t('coreEditor.geodata.removeAsset', { number: index + 1 })}
                    onClick={() => update({ ...geodata, assets: assets.filter((_, i) => i !== index) })}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              )
            })}
          </div>
        </>
      )}
      {issues.length > 0 && (
        <ul className="text-destructive space-y-1 text-sm">
          {issues.map(issue => (
            <li key={issue.path}>
              {issue.path} · {issue.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
