import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { type UseEditFormValues, type UseFormValues, getDefaultUserForm } from '@/features/users/forms/user-form'
import UsersTable from '@/features/users/components/users-table'
import UsersStatistics from '@/features/users/components/users-statistics'
import { Plus } from 'lucide-react'
import UserModal from '@/features/users/dialogs/user-modal'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

const Users = () => {
  const { admin } = useAdmin()
  const canCreateUsers = hasPermission(admin, 'users', 'create')
  const [isUserModalOpen, setUserModalOpen] = useState(false)
  const userForm = useForm<UseFormValues | UseEditFormValues>({
    defaultValues: getDefaultUserForm,
  })

  const handleCreateUser = () => {
    if (!canCreateUsers) return
    userForm.reset()
    setUserModalOpen(true)
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader
          title="users"
          description="manageAccounts"
          buttonIcon={canCreateUsers ? Plus : undefined}
          buttonText={canCreateUsers ? 'createUser' : undefined}
          onButtonClick={canCreateUsers ? handleCreateUser : undefined}
        />
        <Separator />
      </div>

      <div className="w-full px-4 pt-2">
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <UsersStatistics />
        </div>

        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
          <UsersTable />
        </div>
      </div>

      {canCreateUsers && <UserModal isDialogOpen={isUserModalOpen} onOpenChange={setUserModalOpen} form={userForm} editingUser={false} />}
    </div>
  )
}

export default Users
