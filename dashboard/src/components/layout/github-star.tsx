import { useTheme } from '@/components/common/theme-provider'
import { REPO_URL } from '@/constants/Project'
import GitHubButton from 'react-github-btn'

export const GithubStar = () => {
  const { theme } = useTheme()
  const gBtnColor = theme === 'dark' ? 'dark_dimmed' : theme
  return (
    <GitHubButton
      href={REPO_URL}
      data-color-scheme={`no-preference: ${gBtnColor}; light: ${gBtnColor}; dark: ${gBtnColor};`}
      data-size="large"
      data-show-count="true"
      aria-label="Star PasarGuard on GitHub"
    >
      Star
    </GitHubButton>
  )
}
