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

/** Line icons for the sidebar, by name. */
const NAV_PATHS: Record<string, React.ReactNode> = {
  newchat: (
    <>
      <path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L12 14l-4 1 1-4 7.5-7.5z" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.2-4.2" />
    </>
  ),
  approvals: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </>
  ),
  inbox: (
    <>
      <path d="M4 13l2.5-7.5h11L20 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-5z" />
      <path d="M4 13h4.5l1 2h5l1-2H20" />
    </>
  ),
  social: (
    <>
      <path d="M4 10v4h3l7 4V6L7 10H4z" />
      <path d="M17.5 9a4 4 0 0 1 0 6" />
    </>
  ),
  freelance: (
    <>
      <rect x="3.5" y="7" width="17" height="12.5" rx="2" />
      <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3.5 12.5h17" />
    </>
  ),
  news: (
    <>
      <path d="M5 4.5h11a2 2 0 0 1 2 2V19a1.5 1.5 0 0 0 3 0V9h-3" />
      <path d="M5 4.5V18a2 2 0 0 0 2 2h12.5M8 8.5h6M8 12h6M8 15.5h4" />
    </>
  ),
  memory: (
    <>
      <path d="M9.5 18h5M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z" />
    </>
  ),
  activity: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" />
    </>
  ),
  theme: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />,
};

export function NavIcon({ name, ...p }: IconProps & { name: string }) {
  return <Svg {...p}>{NAV_PATHS[name]}</Svg>;
}

/** Line icons for the Settings menu, by name. */
const SETTINGS_PATHS: Record<string, React.ReactNode> = {
  profile: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </>
  ),
  budget: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2.5" />
      <path d="M3 10h18M16 14.5h2" />
    </>
  ),
  models: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
      <path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21" />
    </>
  ),
  voice: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </>
  ),
  search: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5s1.2-6.1 3.5-8.5z" />
    </>
  ),
  calls: <path d="M5 4h3.5l1.5 4-2 1.5a10 10 0 0 0 6.5 6.5l1.5-2 4 1.5V19a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />,
  connections: (
    <>
      <path d="M9 15l6-6" />
      <path d="M10.5 6.5l1.8-1.8a4 4 0 0 1 5.7 5.7l-1.8 1.8M13.5 17.5l-1.8 1.8a4 4 0 0 1-5.7-5.7l1.8-1.8" />
    </>
  ),
  whatsapp: <path d="M4 20l1.3-4A8 8 0 1 1 8.4 19L4 20z" />,
  posting: (
    <>
      <path d="M21 3L10 14" />
      <path d="M21 3l-7 18-4-7-7-4 18-7z" />
    </>
  ),
  news: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="M3.5 6.5l8.5 6.5 8.5-6.5" />
    </>
  ),
  computer: (
    <>
      <rect x="3" y="4" width="18" height="12.5" rx="2" />
      <path d="M8.5 20.5h7M12 16.5v4" />
    </>
  ),
  permissions: (
    <>
      <path d="M12 3l7.5 3v5.5c0 4.5-3.2 8.3-7.5 9.5-4.3-1.2-7.5-5-7.5-9.5V6L12 3z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  advanced: (
    <>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </>
  ),
};

export function SettingsIcon({ name, ...p }: IconProps & { name: string }) {
  return <Svg {...p}>{SETTINGS_PATHS[name]}</Svg>;
}

export function PaperclipIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M20.5 11.5l-8.3 8.3a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9" />
    </Svg>
  );
}

export function ClipboardIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="6" y="4.5" width="12" height="16" rx="2.5" />
      <path d="M9.5 4.5V4a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v.5" />
      <path d="M9.5 10.5h5M9.5 14h5" />
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
