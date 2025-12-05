import { useQuery } from '@tanstack/react-query'

type GoalType = 'donation' | 'github_stars' | (string & {})

interface Goal {
  id: number
  name: string
  detail: string
  price: number
  paid_amount: number
  status: 'pending' | 'completed' | 'cancelled'
  type: GoalType
  repo_owner?: string
  repo_name?: string
  created_at: string
  updated_at: string
}

interface GoalsResponse {
  next_pending: Goal[]
  last_completed: Goal[]
  last_cancelled: Goal[]
  pending_count: number
  completed_count: number
  cancelled_count: number
}

export function useAllGoals() {
  return useQuery({
    queryKey: ['all-goals'],
    queryFn: async () => {
      const response = await fetch('https://api.github.com/repos/pasarguard/ads/contents/goal.json', {
        method: 'GET',
        referrerPolicy: 'no-referrer',
        credentials: 'omit',
      })
      if (response.ok) {
        const apiData = await response.json()
        if (apiData.content && apiData.encoding === 'base64') {
          const base64Content = apiData.content.replace(/\n/g, '')
          const binaryString = atob(base64Content)
          const utf8String = decodeURIComponent(Array.from(binaryString, char => '%' + ('00' + char.charCodeAt(0).toString(16)).slice(-2)).join(''))
          const data: GoalsResponse = JSON.parse(utf8String)
          return data
        }
      }
    },
    refetchInterval: 300000, // Refetch every 5 minutes
    retry: 2,
  })
}
