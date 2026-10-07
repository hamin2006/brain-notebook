'use client'

import { useRouter, useParams } from 'next/navigation'
import { useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import { useSourceChat } from '@/lib/hooks/use-source-chat'
import { ChatPanel } from '@/components/sources/ChatPanel'
import { useNavigation } from '@/lib/hooks/use-navigation'
import { SourceDetailContent } from '@/components/sources/SourceDetailContent'
import { AppShell } from '@/components/layout/AppShell'

export default function SourceDetailPage() {
  const router = useRouter()
  const params = useParams()
  const sourceId = params?.id ? decodeURIComponent(params.id as string) : ''
  const navigation = useNavigation()

  // Initialize source chat
  const chat = useSourceChat(sourceId)

  const handleBack = useCallback(() => {
    const returnPath = navigation.getReturnPath()
    router.push(returnPath)
    navigation.clearReturnTo()
  }, [navigation, router])

  return (
    <AppShell>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex h-12 flex-shrink-0 items-center border-b px-4">
          <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5 text-muted-foreground">
            <ArrowLeft className="h-4 w-4" />
            {navigation.getReturnLabel()}
          </Button>
        </div>

        {/* Source detail + chat with this source */}
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="min-h-0 overflow-y-auto">
            <div className="mx-auto w-full max-w-4xl px-6 py-8">
              <SourceDetailContent
                sourceId={sourceId}
                showChatButton={false}
                onClose={handleBack}
              />
            </div>
          </div>

          <aside className="hidden min-h-0 flex-col border-l bg-sidebar/60 lg:flex">
            <ChatPanel
              messages={chat.messages}
              isStreaming={chat.isStreaming}
              contextIndicators={chat.contextIndicators}
              onSendMessage={(message, model) => chat.sendMessage(message, model)}
              modelOverride={chat.currentSession?.model_override}
              onModelChange={(model) => {
                if (chat.currentSessionId) {
                  chat.updateSession(chat.currentSessionId, { model_override: model })
                }
              }}
              sessions={chat.sessions}
              currentSessionId={chat.currentSessionId}
              onCreateSession={(title) => chat.createSession({ title })}
              onSelectSession={chat.switchSession}
              onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
              onDeleteSession={chat.deleteSession}
              loadingSessions={chat.loadingSessions}
            />
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
