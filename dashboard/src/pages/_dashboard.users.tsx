import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { type UseEditFormValues, type UseFormValues, getDefaultUserForm } from '@/features/users/forms/user-form'
import UsersTable from '@/features/users/components/users-table'
import UsersStatistics from '@/features/users/components/users-statistics'
import { Plus } from 'lucide-react'
import UserModal from '@/features/users/dialogs/user-modal.lazy'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'
import { useCallback, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useCommandCreate } from '@/hooks/use-command-create'

const Users = () => {
  const { admin } = useAdmin()
  const canCreateUsers = hasPermission(admin, 'users', 'create')
  const [isUserModalOpen, setUserModalOpen] = useState(false)
  const userForm = useForm<UseFormValues | UseEditFormValues>({
    defaultValues: getDefaultUserForm,
  })

  const handleCreateUser = useCallback(() => {
    if (!canCreateUsers) return
    userForm.reset()
    setUserModalOpen(true)
  }, [canCreateUsers, userForm])

  useCommandCreate('user', handleCreateUser)

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full">
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
        <UsersStatistics />
        <UsersTable />
      </div>

      {canCreateUsers && <UserModal isDialogOpen={isUserModalOpen} onOpenChange={setUserModalOpen} form={userForm} editingUser={false} />}
    </div>
  )
}

export default Users
