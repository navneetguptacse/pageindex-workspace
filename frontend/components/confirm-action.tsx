"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { ErrorNotice } from "@/components/workspace-ui"
import { errorMessage } from "@/lib/api"

export function ConfirmAction({
  title,
  description,
  action,
  onConfirm,
  onClose,
}: {
  title: string
  description: string
  action: string
  onConfirm: () => Promise<void>
  onClose: () => void
}) {
  const [working, setWorking] = useState(false)
  const [error, setError] = useState("")

  async function confirm() {
    setWorking(true)
    setError("")
    try {
      await onConfirm()
      onClose()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setWorking(false)
    }
  }

  return (
    <AlertDialog
      open
      onOpenChange={(open) => {
        if (!open && !working) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={working}>Cancel</AlertDialogCancel>
          <Button variant="destructive" disabled={working} onClick={confirm}>
            {working && <Spinner data-icon="inline-start" />}
            {action}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
