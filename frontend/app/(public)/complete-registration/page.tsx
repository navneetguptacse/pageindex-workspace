import type { Metadata } from "next"
import { WorkspaceAuth } from "@/components/workspace-auth"

export const metadata: Metadata = { title: "Complete registration" }

export default function AuthPage() {
  return <WorkspaceAuth view="finish-signup" />
}
