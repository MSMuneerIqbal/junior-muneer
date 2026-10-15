/** Small line icons (24×24, stroke = currentColor), so they match light and dark mode. */

type IconProps = { className?: string; title?: string };

function Svg({ className = "h-5 w-5", title, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

export function MicIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
      <path d="M12 17.5V21" />
    </Svg>
  );
}

export function StopIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function SendIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 19V5" />
      <path d="M6 11l6-6 6 6" />
    </Svg>
  );
}

export function SidebarLeftIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16" />
    </Svg>
  );
}

export function SidebarRightIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M15 4v16" />
    </Svg>
  );
}
