"use client";

import useSWR, { useSWRConfig } from "swr";
import { api, ApiError, BACKEND_URL, fetcher, send } from "@/lib/api";
import { APPROVALS_COUNT_KEY, isApprovalsKey, PERMISSIONS_KEY } from "@/lib/keys";
import type { ApprovalItem } from "@/lib/types";

export const itemKey = (id: number) => `/api/approvals/${id}`;

/**
 * One approval item, kept fresh everywhere it shows (chat card, Approvals page):
 * every action updates this item's cache and refreshes every approvals list.
 */
export function useApprovalItem(initial: ApprovalItem) {
  const { data } = useSWR<ApprovalItem>(itemKey(initial.id), fetcher, { fallbackData: initial });
  const { mutate } = useSWRConfig();
  const item = data ?? initial;

  async function act(
    action: "approve" | "posted" | "reject" | "restore" | "edit" | "add_image" | "remove_image",
    body?: object | File | number,
  ) {
    let updated: ApprovalItem;
    if (action === "add_image") {
      const form = new FormData();
      form.append("file", body as File);
      const r = await fetch(`${BACKEND_URL}${itemKey(item.id)}/images`, { method: "POST", body: form });
      if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).detail ?? r.statusText);
      updated = await api<ApprovalItem>(itemKey(item.id));
    } else if (action === "remove_image") {
      await api(`${itemKey(item.id)}/images/${body as number}`, { method: "DELETE" });
      updated = await api<ApprovalItem>(itemKey(item.id));
    } else {
      updated =
        action === "edit"
          ? await send<ApprovalItem>("PATCH", itemKey(item.id), body)
          : await send<ApprovalItem>("POST", `${itemKey(item.id)}/${action}`, body ?? {});
    }
    await mutate(itemKey(item.id), updated, { revalidate: false });
    void mutate((key) => isApprovalsKey(key) && key !== itemKey(item.id));
    if (action === "approve") void mutate(PERMISSIONS_KEY);
    return updated;
  }

  return { item, act };
}

export function useWaitingCount() {
  const { data } = useSWR<{ waiting: number }>(APPROVALS_COUNT_KEY, fetcher, { refreshInterval: 30_000 });
  return data?.waiting;
}
