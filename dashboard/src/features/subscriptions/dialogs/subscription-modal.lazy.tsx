import type { ComponentProps } from 'react'
import { DeferredDialog } from '@/components/common/deferred-dialog'
import { lazyWithChunkRecovery } from '@/utils/chunk-recovery'

const SubscriptionModal = lazyWithChunkRecovery(() => import('./subscription-modal'))

export default function DeferredSubscriptionModal(props: ComponentProps<typeof SubscriptionModal>) {
  return (
    <DeferredDialog open={props.open ?? props.subscribeUrl !== null} onOpenChange={open => !open && props.onCloseModal()}>
      <SubscriptionModal {...props} />
    </DeferredDialog>
  )
}
