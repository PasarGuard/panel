import { Badge } from '@/components/ui/badge'
import { ListOrdered, Shuffle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function SubscriptionOrderBadge({ group }: { group: 'shuffle' | 'fixed' }) {
  const { t } = useTranslation()
  const shuffled = group === 'shuffle'
  const Icon = shuffled ? Shuffle : ListOrdered

  return (
    <Badge variant={shuffled ? 'secondary' : 'outline'} className="shrink-0 gap-1">
      <Icon className="size-3" aria-hidden />
      {t(shuffled ? 'hostsDialog.subscriptionOrderShuffle' : 'hostsDialog.subscriptionOrderFixed')}
    </Badge>
  )
}
