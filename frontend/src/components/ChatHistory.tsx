"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useDeferredValue, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { urduClass } from "@/lib/urdu";
import { CHATS_KEY, isChatsKey } from "@/lib/keys";
import type { Conversation } from "@/lib/types";

const KIND_ICON: Record<Conversation["kind"], string> = {
  text: "",
  voice: "🎙 ",
  call: "📞 ",
  whatsapp: "🟢 ",
  briefing: "", // its title starts with ☀
};

function dayStart(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Pinned first, then Today, Yesterday, Previous 7 days, Previous 30 days, Older. */
export function groupByDate(chats: Conversation[], now = new Date()) {
  const today = dayStart(now);
  const day = 86_400_000;
  const groups: { label: string; chats: Conversation[] }[] = [
    { label: "Pinned", chats: [] },
    { label: "Today", chats: [] },
    { label: "Yesterday", chats: [] },
    { label: "Previous 7 days", chats: [] },
    { label: "Previous 30 days", chats: [] },
    { label: "Older", chats: [] },
  ];
  for (const c of chats) {
    const t = dayStart(new Date(c.updated_at));
    const i = c.pinned
      ? 0
      : t >= today
        ? 1
        : t >= today - day
          ? 2
          : t >= today - 7 * day
            ? 3
            : t >= today - 30 * day
              ? 4
              : 5;
    groups[i].chats.push(c);
  }
  return groups.filter((g) => g.chats.length);
}

function ChatRow({ chat, active }: { chat: Conversation; active: boolean }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [mode, setMode] = useState<"view" | "menu" | "rename" | "delete">("view");
  const [title, setTitle] = useState(chat.title);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await mutate(isChatsKey);
      setMode("view");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  const rename = () =>
    title.trim() && title.trim() !== chat.title
      ? run(() => send("PATCH", `/api/conversations/${chat.id}`, { title: title.trim() }))
      : setMode("view");
  const togglePin = () =>
    run(() => send("PATCH", `/api/conversations/${chat.id}`, { pinned: !chat.pinned }));
  const remove = () =>
    run(async () => {
      await send("DELETE", `/api/conversations/${chat.id}`);
      if (active) router.push("/");
    });

  if (mode === "rename") {
    return (
      <li className="px-1 py-0.5">
        <input
          autoFocus
          dir="auto"
          value={title}
          aria-label="Chat name"
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") rename();
            if (e.key === "Escape") setMode("view");
          }}
          onBlur={rename}
          className="w-full rounded-md border border-accent bg-panel px-2 py-1.5 text-sm outline-none"
        />
      </li>
    );
  }

  return (
    <li className="group relative">
      <div
        className={`flex items-center rounded-md ${active ? "bg-accent-soft" : "hover:bg-panel-2"}`}
      >
        <Link
          href={`/?c=${chat.id}`}
          dir="auto"
          className={`min-w-0 flex-1 truncate px-3 py-1.5 text-sm ${urduClass(chat.title) ? "urdu leading-normal" : ""}`}
          title={chat.title}
        >
          {chat.pinned && <span aria-label="pinned">📌 </span>}
          {KIND_ICON[chat.kind]}
          {chat.title}
        </Link>
        <button
          aria-label={`Options for ${chat.title}`}
          onClick={() => setMode(mode === "menu" ? "view" : "menu")}
          className={`px-2 text-muted hover:text-ink ${mode === "menu" ? "" : "opacity-0 group-hover:opacity-100 focus:opacity-100"} max-lg:opacity-100`}
        >
          ⋯
        </button>
      </div>
      {mode === "menu" && (
        <div className="mx-2 mb-1 flex gap-1 text-xs">
          <button className="rounded px-2 py-1 hover:bg-panel-2" onClick={() => setMode("rename")}>
            Rename
          </button>
          <button className="rounded px-2 py-1 hover:bg-panel-2" onClick={togglePin}>
            {chat.pinned ? "Unpin" : "Pin"}
          </button>
          <button
            className="rounded px-2 py-1 text-danger hover:bg-danger-soft"
            onClick={() => setMode("delete")}
          >
            Delete
          </button>
        </div>
      )}
      {mode === "delete" && (
        <div className="mx-2 mb-1 flex items-center gap-2 text-xs">
          <span>Delete this chat?</span>
          <button className="rounded bg-danger px-2 py-1 text-white" onClick={remove}>
            Delete
          </button>
          <button className="rounded px-2 py-1 hover:bg-panel-2" onClick={() => setMode("view")}>
            Cancel
          </button>
        </div>
      )}
      {error && <p className="mx-3 text-xs text-danger">{error}</p>}
    </li>
  );
}

/** The list of all chats: grouped by date, searchable, rename / pin / delete. */
export function ChatHistory() {
  const params = useSearchParams();
  const activeId = params.get("c") ? Number(params.get("c")) : null;
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query.trim());
  const key = deferred ? `${CHATS_KEY}?q=${encodeURIComponent(deferred)}` : CHATS_KEY;
  const { data, error } = useSWR<Conversation[]>(key, fetcher, { keepPreviousData: true });

  return (
    <div className="flex flex-col gap-2 pb-3">
      <Link
        href="/"
        className="mx-1 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel-2"
      >
        + New chat
      </Link>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="🔍 Search chats"
        aria-label="Search chats"
        dir="auto"
        className="mx-1 rounded-md border border-line bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent"
      />
      {error && <p className="px-3 text-sm text-danger">{error.message}</p>}
      {data && !data.length && (
        <p className="px-3 py-2 text-sm text-muted">{deferred ? "No chats found." : "No chats yet."}</p>
      )}
      {data &&
        groupByDate(data).map((group) => (
          <section key={group.label}>
            <h3 className="px-3 pt-2 pb-1 text-xs font-medium text-muted">{group.label}</h3>
            <ul className="flex flex-col">
              {group.chats.map((chat) => (
                <ChatRow key={chat.id} chat={chat} active={chat.id === activeId} />
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}
