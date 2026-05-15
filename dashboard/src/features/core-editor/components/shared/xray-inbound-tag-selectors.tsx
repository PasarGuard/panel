import { Label } from '@/components/ui/label'
import { StringTagPicker } from '@/components/common/string-tag-picker'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export interface XrayInboundTagPickerProps {
  inboundTags: string[]
  value: string[]
  onChange: (tags: string[]) => void
  /** Shown when `value` is empty (chips row). */
  emptyHint: ReactNode
  placeholder: string
  clearAllLabel: string
  className?: string
}

/** Chips + select + clear — matches core config modal inbound tag fields (without outer label). */
export function XrayInboundTagPicker({
  inboundTags,
  value,
  onChange,
  emptyHint,
  placeholder,
  clearAllLabel,
  className,
}: XrayInboundTagPickerProps) {
  return (
    <StringTagPicker
      mode="multi"
      options={inboundTags}
      valueMulti={value}
      onChangeMulti={onChange}
      emptyHint={emptyHint}
      placeholder={placeholder}
      clearAllLabel={clearAllLabel}
      addButtonLabel={placeholder}
      className={className}
    />
  )
}

export interface XrayInboundTagSelectorsProps {
  inboundTags: string[]
  fallbackTags: string[]
  excludedTags: string[]
  onFallbackChange: (tags: string[]) => void
  onExcludedChange: (tags: string[]) => void
  className?: string
}

/** Fallback + excluded inbound tags with labels — core editor bindings tab. */
export function XrayInboundTagSelectors({
  inboundTags,
  fallbackTags,
  excludedTags,
  onFallbackChange,
  onExcludedChange,
  className,
}: XrayInboundTagSelectorsProps) {
  const { t } = useTranslation()

  return (
    <div className={cn('space-y-8', className)}>
      <div className="flex flex-col gap-2.5">
        <Label>{t('coreConfigModal.fallback')}</Label>
        <XrayInboundTagPicker
          inboundTags={inboundTags}
          value={fallbackTags}
          onChange={onFallbackChange}
          emptyHint={t('coreConfigModal.selectFallback')}
          placeholder={t('coreConfigModal.selectFallback')}
          clearAllLabel={t('coreConfigModal.clearAllFallbacks')}
        />
      </div>
      <div className="flex flex-col gap-2.5">
        <Label>{t('coreConfigModal.excludedInbound')}</Label>
        <XrayInboundTagPicker
          inboundTags={inboundTags}
          value={excludedTags}
          onChange={onExcludedChange}
          emptyHint={t('coreConfigModal.selectInbound')}
          placeholder={t('coreConfigModal.selectInbound')}
          clearAllLabel={t('coreConfigModal.clearAllExcluded')}
        />
      </div>
    </div>
  )
}
