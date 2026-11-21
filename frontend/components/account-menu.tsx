"use client"

import Link from "next/link"
import {
  AtSignIcon,
  ChevronDownIcon,
  CircleUserRoundIcon,
  HouseIcon,
  LogOutIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const usernameDisplayLimit = 12

export function AccountMenu({
  username,
  pending,
  onSignOut,
}: {
  username: string
  pending: boolean
  onSignOut: () => void
}) {
  const truncated = username.length > usernameDisplayLimit
  const displayName = truncated
    ? `${username.slice(0, usernameDisplayLimit)}...`
    : username

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            size="sm"
            variant="ghost"
            aria-label="Account menu"
            disabled={pending}
          />
        }
      >
        <CircleUserRoundIcon />
        <span className="max-w-28 truncate">Account</span>
        <ChevronDownIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="m-1 flex max-w-64 items-center gap-2 rounded-control border bg-muted px-2 py-1.5 text-sm/5 font-medium text-popover-foreground">
            <AtSignIcon className="size-icon shrink-0" aria-hidden="true" />
            <span
              className="min-w-0 truncate"
              title={truncated ? username : undefined}
              aria-hidden={truncated || undefined}
            >
              {displayName}
            </span>
            {truncated && <span className="sr-only">{username}</span>}
          </DropdownMenuLabel>
          <DropdownMenuItem render={<Link href="/account" />}>
            <CircleUserRoundIcon />
            Profile & settings
          </DropdownMenuItem>
          <DropdownMenuItem render={<Link href="/" />}>
            <HouseIcon />
            Home
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem onClick={onSignOut}>
            <LogOutIcon />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
