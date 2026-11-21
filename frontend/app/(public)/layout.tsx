import type { ReactNode } from "react"
import Link from "next/link"
import { Layers3Icon } from "lucide-react"

import { PublicAccountNavigation } from "@/components/public-account-navigation"
import { ThemeToggle } from "@/components/theme-toggle"

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b bg-background">
        <div className="mx-auto flex min-h-16 max-w-6xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-2 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2 font-semibold tracking-tight"
          >
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Layers3Icon className="size-5" aria-hidden="true" />
            </span>
            PageIndex
          </Link>
          <nav
            aria-label="Account navigation"
            className="flex items-center gap-1 sm:gap-2"
          >
            <ThemeToggle />
            <PublicAccountNavigation />
          </nav>
        </div>
      </header>
      {children}
      <footer className="border-t bg-background">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-sm sm:px-6">
          <Link href="/" className="font-semibold">
            PageIndex
          </Link>
          <nav
            aria-label="Footer navigation"
            className="flex flex-wrap gap-x-4 gap-y-2 text-muted-foreground"
          >
            <Link
              href="/workspace"
              className="hover:text-foreground hover:underline"
            >
              Workspace
            </Link>
            <Link
              href="/account"
              className="hover:text-foreground hover:underline"
            >
              Account
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
