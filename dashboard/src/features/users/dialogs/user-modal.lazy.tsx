import type { ComponentProps } from 'react'
import { DeferredDialog } from '@/components/common/deferred-dialog'
import { lazyWithChunkRecovery } from '@/utils/chunk-recovery'

const UserModal = lazyWithChunkRecovery(() => import('./user-modal'))

export default function DeferredUserModal(props: ComponentProps<typeof UserModal>) {
  return (
    <DeferredDialog open={props.isDialogOpen} onOpenChange={props.onOpenChange}>
      <UserModal {...props} />
    </DeferredDialog>
  )
}
