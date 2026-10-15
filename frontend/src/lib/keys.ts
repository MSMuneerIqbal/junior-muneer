/** SWR cache keys (API paths) shared between components. */
export const CHATS_KEY = "/api/conversations";
export const USAGE_KEY = "/api/usage/today";
export const PAUSE_KEY = "/api/pause";
export const SETTINGS_KEY = "/api/settings";
export const MEMORIES_KEY = "/api/memories";
export const APPROVALS_KEY = "/api/approvals";
export const APPROVALS_COUNT_KEY = "/api/approvals/count";
export const PERMISSIONS_KEY = "/api/permissions";

/** Every approvals list, count and single item. */
export const isApprovalsKey = (key: unknown) => typeof key === "string" && key.startsWith(APPROVALS_KEY);

/** Refresh every chat list, including searched ones. */
export const isChatsKey = (key: unknown) =>
  key === CHATS_KEY || (typeof key === "string" && key.startsWith(CHATS_KEY + "?"));
