"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  FileTextIcon,
  LayoutDashboardIcon,
  Layers3Icon,
  MessageSquareIcon,
  ScanSearchIcon,
  Table2Icon,
  Trash2Icon,
} from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

const navigation = [
  { title: "Overview", href: "/workspace", icon: LayoutDashboardIcon },
  { title: "Documents", href: "/documents", icon: FileTextIcon },
  { title: "Chat", href: "/chat", icon: MessageSquareIcon },
  { title: "Search", href: "/search", icon: ScanSearchIcon },
  { title: "Extract", href: "/extract", icon: Table2Icon },
]

export function AppSidebar() {
  const pathname = usePathname()
  const { setOpenMobile } = useSidebar()

  function navItem({ title, href, icon: Icon }: (typeof navigation)[number]) {
    const active = pathname === href
    return (
      <SidebarMenuItem key={href}>
        <SidebarMenuButton
          className="gap-3 px-3"
          render={
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              onClick={() => setOpenMobile(false)}
            />
          }
          isActive={active}
          tooltip={title}
        >
          <Icon aria-hidden="true" />
          <span>{title}</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader className="h-14 justify-center px-4">
        <Link
          className="flex w-fit items-center gap-2.5 font-semibold tracking-tight"
          href="/workspace"
          onClick={() => setOpenMobile(false)}
        >
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Layers3Icon aria-hidden="true" className="size-5" />
          </span>
          <span>PageIndex</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup className="px-2.5 pt-4">
          <SidebarGroupLabel className="px-3 text-xs font-semibold">
            Workspace
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu aria-label="Workspace navigation" className="gap-1">
              {navigation.map(navItem)}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="border-t px-2.5 py-3">
        <SidebarMenu>
          {navItem({ title: "Trash", href: "/trash", icon: Trash2Icon })}
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
