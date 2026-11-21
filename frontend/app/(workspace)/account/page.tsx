import type { Metadata } from "next"
import { WorkspaceAccount } from "@/components/workspace-account"

export const metadata: Metadata = { title: "Account settings" }

export default function AccountPage() {
  return <WorkspaceAccount />
}
