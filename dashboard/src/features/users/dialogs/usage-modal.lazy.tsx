import type { ComponentProps } from 'react'
import { DeferredDialog } from '@/components/common/deferred-dialog'
import { lazyWithChunkRecovery } from '@/utils/chunk-recovery'

const UsageModal = lazyWithChunkRecovery(() => import('./usage-modal'))

export default function DeferredUsageModal(props: ComponentProps<typeof UsageModal>) {
  return (
    <DeferredDialog open={props.open} onOpenChange={open => !open && props.onClose()}>
      <UsageModal {...props} />
    </DeferredDialog>
  )
}
