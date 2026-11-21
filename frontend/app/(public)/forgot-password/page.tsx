import type { Metadata } from "next"
import { WorkspaceAuth } from "@/components/workspace-auth"

export const metadata: Metadata = { title: "Forgot password" }

export default function AuthPage() {
  return <WorkspaceAuth view="forgot" />
}
