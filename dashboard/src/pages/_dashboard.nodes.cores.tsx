import { Outlet } from 'react-router'

export default function CoresLayout() {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Outlet />
    </div>
  )
}
