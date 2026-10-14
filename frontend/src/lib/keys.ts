/** SWR cache keys (API paths) shared between components. */
export const CHATS_KEY = "/api/conversations";
export const USAGE_KEY = "/api/usage/today";
export const PAUSE_KEY = "/api/pause";
export const SETTINGS_KEY = "/api/settings";
export const MEMORIES_KEY = "/api/memories";

/** Refresh every chat list, including searched ones. */
export const isChatsKey = (key: unknown) =>
  key === CHATS_KEY || (typeof key === "string" && key.startsWith(CHATS_KEY + "?"));
