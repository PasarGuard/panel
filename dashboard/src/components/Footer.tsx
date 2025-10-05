import { REPO_URL } from '@/constants/Project'
import { FC } from 'react'

const FooterContent = () => {


  return (
    <p className="inline-block flex-grow text-center text-gray-500 text-xs">
      Made with ❤️ in &nbsp;
      <a className="text-blue-400" href={REPO_URL}>
          PasarGuard Team
      </a>
    </p>
  )
}

export const Footer: FC = ({ ...props }) => {
  return (
    <div className="flex w-full pt-1 pb-3 relative" {...props}>
      <FooterContent />
    </div>
  )
}