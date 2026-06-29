import { CoreCommandMenu } from '@/features/core-editor/components/shared/core-command-menu'
import { CoreSectionTabs } from '@/features/core-editor/components/shell/core-section-sidebar'
import { StickySaveBar } from '@/features/core-editor/components/shell/sticky-save-bar'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

interface CoreEditorLayoutProps {
  header: ReactNode
  sectionHeader?: ReactNode
  main: ReactNode
  dirty: boolean
  canSave?: boolean
  saveLabel?: string
  onSave: () => void
  onDiscard: () => void
  saving: boolean
  showRestart?: boolean
  restartNodes: boolean
  onRestartChange: (v: boolean) => void
  className?: string
}

export function CoreEditorLayout({ header, sectionHeader, main, dirty, canSave, saveLabel, onSave, onDiscard, saving, showRestart, restartNodes, onRestartChange, className }: CoreEditorLayoutProps) {
  return (
    <div className={cn('flex min-h-0 flex-1 flex-col gap-0', className)}>
      <CoreCommandMenu />
      <div className="px-4 pt-3 pb-2 md:pt-6 md:pb-0">{header}</div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {sectionHeader}
        <CoreSectionTabs />
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-4">{main}</div>
      </div>
      <StickySaveBar
        dirty={dirty}
        canSave={canSave}
        saveLabel={saveLabel}
        onSave={onSave}
        onDiscard={onDiscard}
        saving={saving}
        showRestart={showRestart}
        restartNodes={restartNodes}
        onRestartChange={onRestartChange}
      />
    </div>
  )
}
