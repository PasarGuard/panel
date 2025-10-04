import { useQuery } from '@tanstack/react-query'
import { $fetch } from '@/service/http'

interface Goal {
  id: number
  name: string
  detail: string
  price: number
  paid_amount: number
  status: 'pending' | 'completed'
  created_at: string
  updated_at: string
}

export function useCurrentGoal() {
  return useQuery({
    queryKey: ['current-goal'],
    queryFn: async () => {
      const response = await $fetch<Goal>('https://donate.pasarguard.org/api/v1/goal/current', {
        method: 'GET',
      })
      return response
    },
    refetchInterval: 60000, // Refetch every minute
    retry: 2,
  })
}

