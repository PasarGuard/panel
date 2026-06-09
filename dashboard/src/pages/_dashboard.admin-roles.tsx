import { useState } from 'react'
import { Plus } from 'lucide-react'

import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import AdminRolesList from '@/features/admin-roles/components/admin-roles-list'

export default function AdminRolesPage() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader title="adminRoles.title" description="adminRoles.description" buttonIcon={Plus} buttonText="adminRoles.createRole" onButtonClick={() => setIsDialogOpen(true)} />
        <Separator />
      </div>

      <div className="w-full p-4">
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <AdminRolesList isDialogOpen={isDialogOpen} onOpenChange={setIsDialogOpen} />
        </div>
      </div>
    </div>
  )
}
