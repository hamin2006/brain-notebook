import { cn } from '@/lib/utils'

/**
 * The Brain Notebook mark: an ink tile holding a small concept graph (three
 * linked nodes, one lit in the agent's iris), the product in one glyph.
 */
export function BrainMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn('size-7 shrink-0', className)}
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M10.5 20.5 L16 10.5 L22 19 Z"
        className="stroke-primary-foreground/45"
        strokeWidth="1.6"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="10.5" cy="20.5" r="2.6" className="fill-primary-foreground" />
      <circle cx="22" cy="19" r="2.6" className="fill-primary-foreground" />
      <circle cx="16" cy="10.5" r="3.1" className="fill-iris" />
    </svg>
  )
}

/** Mark plus wordmark (the localized app name). */
export function BrainWordmark({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <BrainMark />
      <span className="text-[15px] font-semibold leading-none tracking-tight text-foreground">
        {name}
      </span>
    </span>
  )
}
