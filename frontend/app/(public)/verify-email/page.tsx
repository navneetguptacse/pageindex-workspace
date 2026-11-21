import type { Metadata } from "next"
import { WorkspaceAuth } from "@/components/workspace-auth"

export const metadata: Metadata = { title: "Verify email" }

export default function AuthPage() {
  return <WorkspaceAuth view="verify-email" />
}
