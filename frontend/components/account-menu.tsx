"use client"

import Link from "next/link"
import {
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

export function AccountMenu({
  username,
  pending,
  onSignOut,
}: {
  username: string
  pending: boolean
  onSignOut: () => void
}) {
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
          <DropdownMenuLabel className="max-w-64 truncate">
            {username}
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
