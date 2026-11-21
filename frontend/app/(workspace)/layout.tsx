import type { ReactNode } from "react"
import { WorkspaceGate } from "@/components/workspace-gate"

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return <WorkspaceGate>{children}</WorkspaceGate>
}
