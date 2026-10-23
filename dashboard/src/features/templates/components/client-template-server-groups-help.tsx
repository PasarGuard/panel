import { CopyButton } from '@/components/common/copy-button'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { TooltipProvider } from '@/components/ui/tooltip'
import { SERVER_GROUP_EXAMPLES, supportsServerGroups } from '@/features/templates/forms/template-directives'
import { ChevronDown, Layers } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface ClientTemplateServerGroupsHelpProps {
  templateType: string
  onInsertExample: () => void
}

// Explains the `pasarguard` directive next to the client template editor.
export default function ClientTemplateServerGroupsHelp({ templateType, onInsertExample }: ClientTemplateServerGroupsHelpProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!supportsServerGroups(templateType)) {
    return null
  }

  const example = SERVER_GROUP_EXAMPLES[templateType as keyof typeof SERVER_GROUP_EXAMPLES]
  const typeKey = templateType === 'xray_subscription' ? 'xray' : templateType === 'singbox_subscription' ? 'singbox' : 'clash'

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger asChild>
        <button type="button" className="hover:bg-accent/40 flex w-full items-center justify-between gap-2 rounded-lg p-3 text-start">
          <span className="flex min-w-0 items-center gap-2">
            <Layers className="h-4 w-4 shrink-0" />
            <span className="text-sm font-medium">{t('clientTemplates.serverGroups.title')}</span>
          </span>
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 px-3 pb-3 text-sm">
        <p className="text-muted-foreground">{t('clientTemplates.serverGroups.intro')}</p>
        <p className="text-muted-foreground">{t(`clientTemplates.serverGroups.${typeKey}`)}</p>
        <p className="text-muted-foreground">{t('clientTemplates.serverGroups.select')}</p>
        <div className="relative">
          <pre dir="ltr" className="bg-muted max-h-64 overflow-auto rounded-md p-2 pe-9 font-mono text-[11px] leading-snug">
            {example}
          </pre>
          <TooltipProvider delayDuration={120}>
            <CopyButton value={example} className="absolute end-1 top-1 h-7 w-7" />
          </TooltipProvider>
        </div>
        <p className="text-muted-foreground text-xs">{t(`clientTemplates.serverGroups.insertHint.${typeKey}`)}</p>
        <p className="text-muted-foreground text-xs">{t('clientTemplates.serverGroups.rulesHint')}</p>
        <Button type="button" variant="outline" size="sm" onClick={onInsertExample}>
          {t('clientTemplates.serverGroups.insertExample')}
        </Button>
      </CollapsibleContent>
    </Collapsible>
  )
}
