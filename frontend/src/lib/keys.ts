/** SWR cache keys (API paths) shared between components. */
export const CHATS_KEY = "/api/conversations";
export const USAGE_KEY = "/api/usage/today";
export const PAUSE_KEY = "/api/pause";
export const SETTINGS_KEY = "/api/settings";
export const MEMORIES_KEY = "/api/memories";
export const APPROVALS_KEY = "/api/approvals";
export const APPROVALS_COUNT_KEY = "/api/approvals/count";
export const PERMISSIONS_KEY = "/api/permissions";
export const ORDERS_DUE_KEY = "/api/orders/due";

/** Every approvals list, count and single item. */
export const isApprovalsKey = (key: unknown) => typeof key === "string" && key.startsWith(APPROVALS_KEY);

/** Jobs and orders lists (a sent proposal or delivery changes them). */
export const isFreelanceKey = (key: unknown) =>
  typeof key === "string" && (key.startsWith("/api/orders") || key.startsWith("/api/jobs"));

/** Refresh every chat list, including searched ones. */
export const isChatsKey = (key: unknown) =>
  key === CHATS_KEY || (typeof key === "string" && key.startsWith(CHATS_KEY + "?"));
