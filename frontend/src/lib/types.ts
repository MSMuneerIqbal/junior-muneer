/** Shapes the backend sends. */

export type Conversation = {
  id: number;
  title: string;
  kind: "text" | "voice" | "call" | "whatsapp";
  pinned: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type Step = {
  id: string;
  kind: "web_search" | "tool" | "team";
  name?: string;
  label: string;
  status: "running" | "done";
  // Writing team steps: the text at that step, and the Checker's or Humanizer's notes.
  detail?: string;
  notes?: string[];
};

export type Message = {
  id: number;
  role: "user" | "assistant";
  source: "user" | "outside" | "assistant";
  content: string;
  steps: Step[];
  cost_usd: number;
  audio_file: string | null;
  audio_seconds: number | null;
  created_at: string;
  approvals?: ApprovalItem[];
  paste?: PasteInfo | null;
};

export type PasteInfo = { id?: number; platform: string; kind: string; source_url: string };

export type ApprovalStatus = "waiting" | "approved" | "rejected" | "posted" | "check_manually";

export type ApprovalItem = {
  id: number;
  kind: "copy" | "api";
  platform: string;
  platform_label: string;
  item_type: string;
  action_type: string | null;
  title: string;
  text: string;
  original_text: string;
  edits: { at: string; before: string; after: string }[];
  meta: { score?: number; issues?: string[]; image_idea?: string; warnings?: string[]; [key: string]: unknown };
  status: ApprovalStatus;
  from_outside: boolean;
  can_always_allow: boolean;
  reason: string;
  open_url: string;
  images: { id: number; url: string; name: string; size: number }[];
  needs_image: boolean;
  planned_at: string | null;
  reminded_at: string | null;
  due: boolean;
  can_send: boolean;
  red_lines: string[];
  conversation_id: number | null;
  message_id: number | null;
  created_at: string;
  updated_at: string;
};

export type MemoryNote = {
  action: "saved" | "deleted";
  id: number;
  content: string;
  undone?: boolean;
};

/** Events from the chat WebSocket. */
export type ChatEvent =
  | { type: "conversation"; id: number; title: string }
  | { type: "user_message"; id: number; conversation_id: number }
  | { type: "delta"; text: string }
  | ({ type: "step" } & Step)
  | ({ type: "memory" } & MemoryNote)
  | { type: "approval"; item: ApprovalItem }
  | ({ type: "paste"; message_id: number } & PasteInfo)
  | {
      type: "done";
      conversation_id: number;
      message_id: number;
      text: string;
      steps: Step[];
      cost_usd: number;
    }
  | { type: "error"; message: string };

export type Memory = {
  id: number;
  content: string;
  source_message_id: number | null;
  created_at: string;
  updated_at: string;
};

export type UsageToday = {
  spent_usd: number;
  cap_usd: number;
  left_usd: number;
  cap_reached: boolean;
  by_mode: Record<string, number>;
  by_agent: Record<string, number>;
};

export type Activity = {
  id: number;
  created_at: string;
  kind: string;
  name: string;
  result: string;
  detail: Record<string, unknown>;
  cost_usd: number;
  conversation_id: number | null;
};

export type Settings = {
  user_name: string;
  language: "match" | "english" | "urdu";
  timezone: string;
  daily_cap_usd: number;
  paused: boolean;
  tts_voice: string;
  voice_accent: "pakistani" | "indian" | "neutral";
  tts_speed: number;
  voice_autoplay: boolean;
  call_minutes_per_day: number;
  call_quality: "natural" | "economy";
  turn_taking: "patient" | "balanced" | "quick";
  mic_type: "headset" | "laptop" | "off";
  main_model: string;
  helper_model: string;
  api_posts_per_day: number;
  news_digest_enabled: boolean;
  news_digest_time: string;
};

export type ChatSummary = {
  kind: Conversation["kind"];
  cost_usd: number;
  call_seconds: number | null;
};
