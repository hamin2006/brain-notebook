'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/hooks/use-auth'
import { useSidebarStore } from '@/lib/stores/sidebar-store'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useMediaQuery } from '@/lib/hooks/use-media-query'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { LanguageToggle } from '@/components/common/LanguageToggle'
import { BrainMark, BrainWordmark } from '@/components/brand/BrainMark'
import { openCommandPalette } from '@/components/common/CommandPalette'
import type { TFunction } from 'i18next'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  BookOpen,
  Sparkles,
  Mic,
  Cpu,
  Shuffle,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Library,
  Plus,
  Wrench,
  Search,
  FileText,
} from 'lucide-react'

type NavItem = { name: string; href: string; icon: typeof BookOpen }

const getPrimaryNavigation = (t: TFunction): NavItem[] => [
  { name: t('navigation.notebooks'), href: '/notebooks', icon: BookOpen },
  { name: t('navigation.askAndSearch'), href: '/search', icon: Sparkles },
  { name: t('navigation.sources'), href: '/sources', icon: Library },
  { name: t('navigation.podcasts'), href: '/podcasts', icon: Mic },
]

const getWorkspaceNavigation = (t: TFunction): NavItem[] => [
  { name: t('navigation.models'), href: '/settings/models', icon: Cpu },
  { name: t('navigation.transformations'), href: '/transformations', icon: Shuffle },
  { name: t('navigation.settings'), href: '/settings', icon: Settings },
  { name: t('navigation.advanced'), href: '/advanced', icon: Wrench },
]

type CreateTarget = 'source' | 'notebook' | 'podcast'

/** A deterministic hue for a notebook's dot, from its id. */
const NOTEBOOK_DOTS = ['bg-iris', 'bg-amber', 'bg-fern', 'bg-plum', 'bg-slate-hue', 'bg-mauve']
export function notebookDot(id: string): string {
  let hash = 0
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) | 0
  return NOTEBOOK_DOTS[Math.abs(hash) % NOTEBOOK_DOTS.length]
}

export function AppSidebar() {
  const { t } = useTranslation()
  const primary = getPrimaryNavigation(t)
  const workspace = getWorkspaceNavigation(t)
  const pathname = usePathname()
  const { logout } = useAuth()
  const { isCollapsed: storedCollapsed, toggleCollapse } = useSidebarStore()
  // Phones get the icon rail so the page keeps its width
  const isSmall = useMediaQuery('(max-width: 767px)')
  const isCollapsed = storedCollapsed || isSmall
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()
  const { data: notebooks } = useNotebooks(false)

  // The active item is the longest href that prefixes the current path.
  // Longest-wins keeps `/settings` from also highlighting on `/settings/models`
  // (the Models page is a URL child of the Settings page but a distinct item).
  const activeHref = [...primary, ...workspace]
    .filter((item) => pathname === item.href || pathname?.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href

  const [createMenuOpen, setCreateMenuOpen] = useState(false)
  const [isMac, setIsMac] = useState(true) // Default to Mac for SSR

  useEffect(() => {
    setIsMac(navigator.platform.toLowerCase().includes('mac'))
  }, [])

  const handleCreateSelection = (target: CreateTarget) => {
    setCreateMenuOpen(false)
    if (target === 'source') openSourceDialog()
    else if (target === 'notebook') openNotebookDialog()
    else if (target === 'podcast') openPodcastDialog()
  }

  const renderItem = (item: NavItem, compact = false) => {
    const isActive = item.href === activeHref
    const button = (
      <Button
        variant="ghost"
        className={cn(
          'relative w-full gap-2.5 text-[13px] sidebar-menu-item',
          compact ? 'h-8' : 'h-9',
          isActive
            ? 'bg-card font-semibold text-foreground shadow-soft ring-1 ring-inset ring-border hover:bg-card'
            : 'font-medium text-muted-foreground hover:text-foreground',
          isCollapsed ? 'justify-center px-2' : 'justify-start px-2.5'
        )}
      >
        <item.icon className={cn('h-4 w-4', isActive ? 'text-iris' : 'opacity-80')} />
        {!isCollapsed && <span>{item.name}</span>}
      </Button>
    )
    if (isCollapsed) {
      return (
        <Tooltip key={item.href}>
          <TooltipTrigger asChild>
            <Link href={item.href}>{button}</Link>
          </TooltipTrigger>
          <TooltipContent side="right">{item.name}</TooltipContent>
        </Tooltip>
      )
    }
    return (
      <Link key={item.href} href={item.href}>
        {button}
      </Link>
    )
  }

  const createMenu = (
    <DropdownMenu open={createMenuOpen} onOpenChange={setCreateMenuOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="default"
          size="icon-sm"
          className="shrink-0"
          aria-label={t('common.create')}
          title={t('common.create')}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side={isCollapsed ? 'right' : 'bottom'} className="w-48">
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            handleCreateSelection('notebook')
          }}
          className="gap-2"
        >
          <BookOpen className="h-4 w-4" />
          {t('common.notebook')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            handleCreateSelection('source')
          }}
          className="gap-2"
        >
          <FileText className="h-4 w-4" />
          {t('common.source')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            handleCreateSelection('podcast')
          }}
          className="gap-2"
        >
          <Mic className="h-4 w-4" />
          {t('common.podcast')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          'app-sidebar flex h-full flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-300',
          isCollapsed ? 'w-[60px]' : 'w-[264px]'
        )}
      >
        {/* Brand */}
        <div className={cn('flex h-14 items-center group', isCollapsed ? 'justify-center px-2' : 'justify-between pl-4 pr-2')}>
          {isCollapsed ? (
            <button
              type="button"
              onClick={toggleCollapse}
              className="relative flex size-9 items-center justify-center rounded-lg hover:bg-sidebar-accent"
              aria-label={t('brain.expandSidebar')}
              data-testid="sidebar-toggle"
            >
              <BrainMark className="transition-opacity group-hover:opacity-0" />
              <PanelLeftOpen className="absolute h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          ) : (
            <>
              <Link href="/notebooks" className="rounded-lg">
                <BrainWordmark name={t('common.appName')} />
              </Link>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={toggleCollapse}
                className="text-muted-foreground"
                aria-label={t('brain.collapseSidebar')}
                data-testid="sidebar-toggle"
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>

        {/* Search / ask + create */}
        <div className={cn('flex items-center gap-2 pb-3 pt-1', isCollapsed ? 'flex-col px-2' : 'px-3')}>
          {isCollapsed ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={openCommandPalette}
                  aria-label={t('brain.searchOrJump')}
                >
                  <Search className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">{t('brain.searchOrJump')}</TooltipContent>
            </Tooltip>
          ) : (
            <button
              type="button"
              onClick={openCommandPalette}
              className="flex h-8 flex-1 items-center gap-2 rounded-lg border bg-card px-2.5 text-left text-[13px] text-muted-foreground shadow-soft transition-colors hover:border-foreground/20 hover:text-foreground"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="flex-1 truncate">{t('brain.searchOrJump')}</span>
              <kbd className="pointer-events-none rounded border bg-muted px-1.5 font-mono text-[10px] leading-4 text-muted-foreground">
                {isMac ? '⌘' : 'Ctrl'} K
              </kbd>
            </button>
          )}
          {createMenu}
        </div>

        <nav className={cn('flex-1 overflow-y-auto pb-3', isCollapsed ? 'px-2' : 'px-3')}>
          <div className="space-y-0.5">{primary.map((item) => renderItem(item))}</div>

          {!isCollapsed && notebooks && notebooks.length > 0 && (
            <div className="mt-6">
              <div className="mb-1.5 flex items-center justify-between px-2.5">
                <h3 className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70">
                  {t('navigation.notebooks')}
                </h3>
                <button
                  type="button"
                  onClick={() => handleCreateSelection('notebook')}
                  className="rounded p-0.5 text-muted-foreground/70 hover:bg-sidebar-accent hover:text-foreground"
                  aria-label={t('notebooks.newNotebook')}
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="space-y-0.5">
                {notebooks.slice(0, 12).map((notebook) => {
                  const href = `/notebooks/${encodeURIComponent(notebook.id)}`
                  const isActive = pathname === href || pathname === `/notebooks/${notebook.id}`
                  return (
                    <Link
                      key={notebook.id}
                      href={href}
                      className={cn(
                        'group/nb flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] transition-colors',
                        isActive
                          ? 'bg-card font-medium text-foreground shadow-soft ring-1 ring-inset ring-border'
                          : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
                      )}
                    >
                      <span className={cn('size-2 shrink-0 rounded-full', notebookDot(notebook.id))} />
                      <span className="flex-1 truncate">{notebook.name}</span>
                      <span className="font-mono text-[10px] text-muted-foreground/60 opacity-0 transition-opacity group-hover/nb:opacity-100">
                        {notebook.source_count}
                      </span>
                    </Link>
                  )
                })}
              </div>
            </div>
          )}

          <div className={cn('mt-6', isCollapsed && 'border-t border-sidebar-border pt-3')}>
            {!isCollapsed && (
              <h3 className="mb-1.5 px-2.5 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70">
                {t('navigation.manage')}
              </h3>
            )}
            <div className="space-y-0.5">{workspace.map((item) => renderItem(item, true))}</div>
          </div>
        </nav>

        {/* Footer: theme, language, sign out */}
        <div
          className={cn(
            'flex border-t border-sidebar-border p-2',
            isCollapsed ? 'flex-col items-center gap-1' : 'items-center gap-1'
          )}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <ThemeToggle iconOnly />
              </div>
            </TooltipTrigger>
            <TooltipContent side={isCollapsed ? 'right' : 'top'}>{t('common.theme')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <LanguageToggle iconOnly />
              </div>
            </TooltipTrigger>
            <TooltipContent side={isCollapsed ? 'right' : 'top'}>{t('common.language')}</TooltipContent>
          </Tooltip>
          {!isCollapsed && <div className="flex-1" />}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground"
                onClick={logout}
                aria-label={t('common.signOut')}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side={isCollapsed ? 'right' : 'top'}>{t('common.signOut')}</TooltipContent>
          </Tooltip>
        </div>
      </aside>
    </TooltipProvider>
  )
}
