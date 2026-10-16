/** The Paste box: text from another site, sent as outside content. */

export type PasteDraft = {
  text: string;
  platform: string;
  kind: string;
  source_url: string;
};

export const PASTE_PLATFORMS = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "facebook", label: "Facebook" },
  { value: "instagram", label: "Instagram" },
  { value: "x", label: "X" },
  { value: "upwork", label: "Upwork" },
  { value: "fiverr", label: "Fiverr" },
  { value: "email", label: "Email" },
  { value: "other", label: "Other" },
];

export const PASTE_KINDS = [
  { value: "post", label: "Post" },
  { value: "comment", label: "Comment" },
  { value: "job", label: "Job post" },
  { value: "client_message", label: "Client message" },
  { value: "email", label: "Email" },
  { value: "other", label: "Other" },
];

export const platformLabel = (v: string) => PASTE_PLATFORMS.find((p) => p.value === v)?.label ?? v;
export const kindLabel = (v: string) => PASTE_KINDS.find((k) => k.value === v)?.label ?? v;

/** Long text pasted into the message box is probably someone else's: offer the Paste box. */
export const LONG_PASTE_CHARS = 500;

const HOSTS: [RegExp, string][] = [
  [/linkedin\.com/, "linkedin"],
  [/facebook\.com|fb\.com/, "facebook"],
  [/instagram\.com/, "instagram"],
  [/(^|\.)x\.com|twitter\.com/, "x"],
  [/upwork\.com/, "upwork"],
  [/fiverr\.com/, "fiverr"],
  [/mail\.google\.com|outlook\./, "email"],
];

/** Guess the platform from a link, and a likely type for it. */
export function guessFromUrl(url: string): { platform?: string; kind?: string } {
  let host = "";
  try {
    host = new URL(url).hostname;
  } catch {
    return {};
  }
  const platform = HOSTS.find(([re]) => re.test(host))?.[1];
  if (!platform) return {};
  if (platform === "upwork" && /\/jobs?\//.test(url)) return { platform, kind: "job" };
  if (platform === "upwork" && /\/messages\//.test(url)) return { platform, kind: "client_message" };
  if (platform === "fiverr" && /\/inbox\//.test(url)) return { platform, kind: "client_message" };
  if (platform === "email") return { platform, kind: "email" };
  return { platform };
}

export const emptyPaste = (text = ""): PasteDraft => ({ text, platform: "other", kind: "post", source_url: "" });
