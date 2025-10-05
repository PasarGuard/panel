import PageHeader from '@/components/page-header'
import { Separator } from '@/components/ui/separator'
import { Plus } from 'lucide-react'
import Groups from '@/components/groups/Groups'
import { useState } from 'react'

export default function GroupsPage() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  return (
    <div className="flex flex-col gap-2 w-full items-start">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader title="groups" description="manageGroups" buttonIcon={Plus} buttonText="createGroup" onButtonClick={() => setIsDialogOpen(true)} />
        <Separator />
      </div>

      <div className="px-4 w-full pt-2">
        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <Groups isDialogOpen={isDialogOpen} onOpenChange={setIsDialogOpen} />
        </div>
      </div>
    </div>
  )
}
