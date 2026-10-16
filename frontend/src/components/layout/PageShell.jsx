/**
 * @typedef {Object} PageShellProps
 * @property {import('react').ReactNode} children
 */

/**
 * @param {PageShellProps} props
 */
export function PageShell({ children }) {
  return (
    <div id="top" className="min-h-full w-full bg-bg text-text">
      {children}
    </div>
  )
}

export default PageShell
