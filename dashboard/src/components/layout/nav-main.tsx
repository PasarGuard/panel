import { ChevronRight, type LucideIcon } from 'lucide-react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { SidebarGroup, SidebarGroupLabel, SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem, useSidebar } from '@/components/ui/sidebar'
import { NavLink, useLocation } from 'react-router'
import { useTranslation } from 'react-i18next'

export function NavMain({
  items,
}: {
  items: {
    title: string
    url: string
    icon: LucideIcon
    isActive?: boolean
    items?: {
      title: string
      url: string
      icon: LucideIcon
    }[]
  }[]
}) {
  const location = useLocation()
  const { t } = useTranslation()
  const { setOpenMobile } = useSidebar()

  const handleNavigation = () => {
    setOpenMobile(false)
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{t('platform')}</SidebarGroupLabel>
      <SidebarMenu>
        {items.map(item => (
          <Collapsible key={item.title} defaultOpen={item.isActive || location.pathname.startsWith(item.url)}>
            <SidebarMenuItem>
              <CollapsibleTrigger asChild>
                <NavLink to={item.url} onClick={handleNavigation}>
                  {({ isActive }) => (
                    <SidebarMenuButton tooltip={t(item.title)} isActive={isActive}>
                      <item.icon />
                      <span>{t(item.title)}</span>
                    </SidebarMenuButton>
                  )}
                </NavLink>
              </CollapsibleTrigger>
              {item.items?.length ? (
                <>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuAction className="rtl: data-[state=open]:rotate-90 data-[state=open]:rtl:-rotate-90">
                      <ChevronRight className="rtl:rotate-180" />
                      <span className="sr-only">Toggle</span>
                    </SidebarMenuAction>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {item.items?.map(subItem => (
                        <SidebarMenuSubItem key={subItem.title}>
                          <SidebarMenuSubButton asChild className="flex items-center gap-2 h-8" isActive={location.pathname === subItem.url}>
                            <NavLink to={subItem.url} end onClick={handleNavigation}>
                              <subItem.icon />
                              <span>{t(subItem.title)}</span>
                            </NavLink>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      ))}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </>
              ) : null}
            </SidebarMenuItem>
          </Collapsible>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
