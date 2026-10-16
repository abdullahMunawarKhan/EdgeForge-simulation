import { useEffect, useRef, useState } from 'react'

const DEFAULT_LINKS = [
  { label: 'Overview', href: '#overview' },
  { label: 'Workflow', href: '#workflow' },
  { label: 'Scenario Lab', href: '#scenario' },
  { label: 'Failure Analysis', href: '#failure-analysis' },
  { label: 'Coverage', href: '#coverage' },
  { label: 'Next Test', href: '#next-test' },
]

export function Navbar({ links = DEFAULT_LINKS }) {
  const [isOpen, setIsOpen] = useState(false)
  const [activeId, setActiveId] = useState('overview')

  const [signal, setSignal] = useState({
    left: 0,
    width: 0,
    visible: false,
  })

  const navRef = useRef(null)
  const linkRefs = useRef([])

  const closeMenu = () => setIsOpen(false)

  const moveSignal = (index) => {
    const nav = navRef.current
    const link = linkRefs.current[index]

    if (!nav || !link) return

    const navRect = nav.getBoundingClientRect()
    const linkRect = link.getBoundingClientRect()

    setSignal({
      left: linkRect.left - navRect.left,
      width: linkRect.width,
      visible: true,
    })
  }

  const moveSignalToActive = () => {
    const index = links.findIndex(
      (link) => link.href.replace('#', '') === activeId
    )

    if (index !== -1) {
      moveSignal(index)
    }
  }

  const handleLinkClick = (href) => {
    const id = href.replace('#', '')

    setActiveId(id)
    closeMenu()

    const index = links.findIndex((link) => link.href === href)

    if (index !== -1) {
      moveSignal(index)
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return

    const updateFromHash = () => {
      const hash = window.location.hash.replace('#', '')

      if (links.some((link) => link.href === `#${hash}`)) {
        setActiveId(hash)
      }
    }

    updateFromHash()

    window.addEventListener('hashchange', updateFromHash)

    const sectionIds = [
      'hero',
      'overview',
      'workflow',
      'scenario',
      'failure-analysis',
      'coverage',
      'next-test',
      'benefits',
    ]

    const sections = sectionIds
      .map((id) => document.getElementById(id))
      .filter(Boolean)

    let observer = null

    if ('IntersectionObserver' in window && sections.length > 0) {
      observer = new IntersectionObserver(
        (entries) => {
          const visible = entries.filter(
            (entry) => entry.isIntersecting
          )

          if (visible.length > 0) {
            visible.sort(
              (a, b) =>
                Math.abs(a.boundingClientRect.top) -
                Math.abs(b.boundingClientRect.top)
            )

            setActiveId(visible[0].target.id)
          }
        },
        {
          rootMargin: '-10% 0px -55% 0px',
          threshold: [0, 0.25],
        }
      )

      sections.forEach((section) => observer.observe(section))
    }

    return () => {
      window.removeEventListener('hashchange', updateFromHash)

      if (observer) {
        observer.disconnect()
      }
    }
  }, [links])

  useEffect(() => {
    moveSignalToActive()

    const handleResize = () => {
      moveSignalToActive()
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [activeId, links])

  return (
    <header className="w-full border-b border-border-subtle bg-bg">
      {/* =========================================================
          SINGLE DESKTOP NAVBAR
      ========================================================= */}
      <div className="mx-auto hidden h-[72px] max-w-6xl items-center justify-between px-4 md:px-6 lg:flex">

        {/* EDGEFORGE */}
        <a
          href="#hero"
          onClick={() => handleLinkClick('#hero')}
          aria-label="EDGEFORGE home"
          className="group shrink-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span className="text-[24px] font-bold leading-none tracking-[-0.035em] text-text transition-colors duration-200 group-hover:text-accent">
            EDGEFORGE
          </span>
        </a>

        {/* NAVIGATION */}
        <nav
          ref={navRef}
          aria-label="Primary navigation"
          className="relative flex h-full items-center gap-7 xl:gap-9"
        >
          {/* Base rail */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute bottom-0 left-0 right-0 h-px bg-border-subtle"
          />

          {/* Flowing green signal */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute bottom-[-1px] h-[3px] rounded-full bg-accent transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{
              left: `${signal.left}px`,
              width: `${signal.width}px`,
              opacity: signal.visible ? 1 : 0,
              boxShadow:
                '0 0 10px rgba(80, 220, 130, 0.65), 0 0 25px rgba(80, 220, 130, 0.2)',
            }}
          />

          {/* Travelling glow */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute bottom-[-3px] h-[7px] w-8 -translate-x-1/2 rounded-full bg-accent blur-[5px] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{
              left: `${signal.left + signal.width / 2}px`,
              opacity: signal.visible ? 0.55 : 0,
            }}
          />

          {links.map((link, index) => {
            const isActive =
              activeId === link.href.replace('#', '')

            return (
              <a
                key={link.href}
                ref={(element) => {
                  linkRefs.current[index] = element
                }}
                href={link.href}
                onClick={() => handleLinkClick(link.href)}
                onMouseEnter={() => moveSignal(index)}
                onFocus={() => moveSignal(index)}
                className={`relative flex h-full items-center whitespace-nowrap text-[14px] font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  isActive
                    ? 'text-text'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                {link.label}
              </a>
            )
          })}
        </nav>
      </div>

      {/* =========================================================
          MOBILE NAVBAR
      ========================================================= */}
      <div className="flex h-[64px] items-center justify-between px-4 lg:hidden">
        <a
          href="#hero"
          onClick={() => handleLinkClick('#hero')}
          aria-label="EDGEFORGE home"
          className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span className="text-[22px] font-bold tracking-[-0.035em] text-text">
            EDGEFORGE
          </span>
        </a>

        <button
          type="button"
          onClick={() => setIsOpen((current) => !current)}
          aria-expanded={isOpen}
          aria-controls="mobile-navigation"
          aria-label={
            isOpen ? 'Close navigation menu' : 'Open navigation menu'
          }
          className="flex h-9 w-9 items-center justify-center rounded border border-border-subtle text-text transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span
            aria-hidden="true"
            className="flex w-5 flex-col gap-[5px]"
          >
            <span
              className={`h-px w-full bg-current transition-transform duration-200 ${
                isOpen ? 'translate-y-[3px] rotate-45' : ''
              }`}
            />

            <span
              className={`h-px w-full bg-current transition-opacity duration-200 ${
                isOpen ? 'opacity-0' : ''
              }`}
            />

            <span
              className={`h-px w-full bg-current transition-transform duration-200 ${
                isOpen ? '-translate-y-[3px] -rotate-45' : ''
              }`}
            />
          </span>
        </button>
      </div>

      {/* =========================================================
          MOBILE MENU
      ========================================================= */}
      {isOpen && (
        <div
          id="mobile-navigation"
          className="border-t border-border-subtle bg-bg px-4 py-3 lg:hidden"
        >
          <nav
            aria-label="Mobile navigation"
            className="mx-auto flex max-w-6xl flex-col gap-1"
          >
            {links.map((link) => {
              const isActive =
                activeId === link.href.replace('#', '')

              return (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={() => handleLinkClick(link.href)}
                  className={`flex min-h-[48px] items-center justify-between rounded px-3 text-[15px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${
                    isActive
                      ? 'bg-accent/[0.08] font-semibold text-accent'
                      : 'text-text-muted hover:bg-surface-hover/50 hover:text-text'
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    {isActive && (
                      <span
                        aria-hidden="true"
                        className="h-1.5 w-1.5 rounded-full bg-accent"
                      />
                    )}

                    {link.label}
                  </span>

                  <span
                    aria-hidden="true"
                    className="text-text-subtle"
                  >
                    →
                  </span>
                </a>
              )
            })}
          </nav>
        </div>
      )}
    </header>
  )
}

export default Navbar