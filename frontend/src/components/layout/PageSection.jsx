/**
 * @typedef {Object} SectionHeaderProps
 * @property {string} [eyebrow]
 * @property {string} title
 * @property {string} [description]
 * @property {import('react').ReactNode} [actionSlot]
 */

/**
 * @param {SectionHeaderProps} props
 */
export function SectionHeader({ eyebrow, title, description, actionSlot }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-2">
        {eyebrow ? (
          <div className="chip chip-accent">{eyebrow}</div>
        ) : null}
        <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{title}</h2>
        {description ? (
          <p className="max-w-2xl text-xs text-text-muted md:text-sm">{description}</p>
        ) : null}
      </div>
      {actionSlot}
    </div>
  )
}

/**
 * @param {import('./types.js').PageSectionProps} props
 */
export function PageSection({ id, className = '', children }) {
  return (
    <section
      id={id}
      className={`scroll-mt-20 mx-auto w-full max-w-6xl px-4 py-10 md:px-6 md:py-14 ${className}`}
    >
      {children}
    </section>
  )
}

export default PageSection
