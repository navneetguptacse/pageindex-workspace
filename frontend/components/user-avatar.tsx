import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import type { WorkspaceStatus } from "@/lib/api"

export type ProfileIdentity = Pick<
  WorkspaceStatus,
  "username" | "first_name" | "last_name" | "avatar_url"
>

export function UserAvatar({
  profile,
  size,
}: {
  profile: ProfileIdentity
  size?: "sm" | "lg"
}) {
  const initials = [profile.first_name, profile.last_name]
    .filter((name): name is string => Boolean(name))
    .map((name) => Array.from(name)[0])
    .join("")
  return (
    <Avatar size={size} aria-hidden="true">
      {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
      <AvatarFallback className="bg-accent font-semibold text-accent-foreground group-data-[size=sm]/avatar:text-[0.6875rem]/none">
        {(initials || profile.username?.slice(0, 2) || "?").toUpperCase()}
      </AvatarFallback>
    </Avatar>
  )
}
