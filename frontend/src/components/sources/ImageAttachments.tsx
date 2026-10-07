'use client'

import { X } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'

export const MAX_ATTACHMENTS = 4
const MAX_SIDE = 1600

/** An image file as a JPEG data URL, scaled down so its longest side is at most MAX_SIDE. */
export async function readImageFile(file: File, maxSide: number = MAX_SIDE): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Canvas is not available')
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvas.toDataURL('image/jpeg', 0.9)
}

/** The image files among pasted or picked files. */
export function imageFiles(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files ?? []).filter(file => file.type.startsWith('image/'))
}

/** Thumbnails of attached images; removable while composing. */
export function AttachmentStrip({ images, onRemove }: { images: string[]; onRemove?: (index: number) => void }) {
  const { t } = useTranslation()
  if (!images.length) return null
  return (
    <div className="flex flex-wrap gap-2">
      {images.map((url, index) => (
        <div key={index} className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element -- data URL of an attached image */}
          <img src={url} alt={t('chat.attachedImage')} className="h-16 w-16 rounded-md border object-cover" />
          {onRemove && (
            <button
              type="button"
              aria-label={t('chat.removeImage')}
              onClick={() => onRemove(index)}
              className="absolute -right-1.5 -top-1.5 rounded-full border bg-background p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
