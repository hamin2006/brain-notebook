'use client'

import { useParams } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { CheatSheetWorkspace } from '@/components/cheat-sheets/CheatSheetWorkspace'

export default function CheatSheetPage() {
  const params = useParams()
  const notebookId = params?.id ? decodeURIComponent(params.id as string) : ''
  const sheetId = params?.sheetId ? decodeURIComponent(params.sheetId as string) : ''

  return (
    <AppShell>
      <CheatSheetWorkspace notebookId={notebookId} sheetId={sheetId} />
    </AppShell>
  )
}
