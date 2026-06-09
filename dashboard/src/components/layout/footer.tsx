import { REPO_URL } from '@/constants/Project'
import { FC } from 'react'

const FooterContent = () => {
  return (
    <p className="inline-block flex-grow text-center text-xs text-gray-500">
      Made with ❤️ by &nbsp;
      <a className="text-blue-400" href={REPO_URL}>
        PasarGuard
      </a>{' '}
      Team
    </p>
  )
}

export const Footer: FC = ({ ...props }) => {
  return (
    <div className="relative flex w-full pt-1 pb-3" {...props}>
      <FooterContent />
    </div>
  )
}
