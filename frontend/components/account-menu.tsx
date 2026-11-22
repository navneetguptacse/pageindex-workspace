"use client"

import Link from "next/link"
import {
  ChevronDownIcon,
  CircleUserRoundIcon,
  HouseIcon,
  LogOutIcon,
} from "lucide-react"

import { UserAvatar, type ProfileIdentity } from "@/components/user-avatar"
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
  profile,
  pending,
  onSignOut,
}: {
  profile: ProfileIdentity
  pending: boolean
  onSignOut: () => void
}) {
  const username = profile.username ?? ""
  const fullName = [profile.first_name, profile.last_name]
    .filter(Boolean)
    .join(" ")
  const truncated = username.length > usernameDisplayLimit
  const handle = truncated
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
        <UserAvatar profile={profile} size="sm" />
        <span className="max-w-28 truncate">Account</span>
        <ChevronDownIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="m-1 flex max-w-64 items-center gap-3 rounded-control border bg-muted px-2 py-2 text-popover-foreground">
            <UserAvatar profile={profile} size="lg" />
            <div className="min-w-0">
              {fullName && (
                <div className="truncate text-sm/5" title={fullName}>
                  {fullName}
                </div>
              )}
              <div
                className="truncate text-xs/4 text-muted-foreground"
                title={truncated ? `@${username}` : undefined}
                aria-hidden={truncated || undefined}
              >
                @{handle}
              </div>
              {truncated && <span className="sr-only">@{username}</span>}
            </div>
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
