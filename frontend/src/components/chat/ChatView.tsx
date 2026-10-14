"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Composer } from "@/components/chat/Composer";
import { AssistantMessage, ErrorNotice, UserMessage } from "@/components/chat/MessageView";
import { fetcher } from "@/lib/api";
import type { ChatEvent, MemoryNote, Message, Step } from "@/lib/types";
import { useChatSocket } from "@/lib/useChatSocket";

/** The answer being written right now. */
type Turn = {
  conversationId: number | null;
  userText: string;
  userMessageId?: number;
  text: string;
  steps: Step[];
  notes: MemoryNote[];
  status: "streaming" | "done" | "error";
  error?: string;
  messageId?: number;
};

export const CHATS_KEY = "/api/conversations";
export const USAGE_KEY = "/api/usage/today";

function upsertStep(steps: Step[], step: Step): Step[] {
  const i = steps.findIndex((s) => s.id === step.id);
  return i === -1 ? [...steps, step] : steps.map((s, j) => (j === i ? step : s));
}

export function ChatView() {
  const params = useSearchParams();
  const conversationId = params.get("c") ? Number(params.get("c")) : null;
  const messagesKey = conversationId ? `/api/conversations/${conversationId}/messages` : null;
  const { data: saved, error: loadError, mutate } = useSWR<Message[]>(messagesKey, fetcher);
  const { mutate: mutateGlobal } = useSWRConfig();

  const [turn, setTurn] = useState<Turn | null>(null);
  // Memory notes stay under the answer they came with (this session only).
  const [notesByMessage, setNotesByMessage] = useState<Record<number, MemoryNote[]>>({});

  const onEvent = useCallback(
    (event: ChatEvent) => {
      switch (event.type) {
        case "conversation":
          window.history.replaceState(null, "", `/?c=${event.id}`);
          setTurn((t) => t && { ...t, conversationId: event.id });
          mutateGlobal(CHATS_KEY);
          break;
        case "user_message":
          setTurn((t) => t && { ...t, userMessageId: event.id });
          break;
        case "delta":
          setTurn((t) => t && { ...t, text: t.text + event.text });
          break;
        case "step": {
          const { type, ...step } = event;
          void type;
          setTurn((t) => t && { ...t, steps: upsertStep(t.steps, step) });
          break;
        }
        case "memory": {
          const { type, ...note } = event;
          void type;
          setTurn((t) => t && { ...t, notes: [...t.notes, note] });
          break;
        }
        case "done":
          setTurn((t) => {
            if (t?.notes.length) {
              setNotesByMessage((n) => ({ ...n, [event.message_id]: t.notes }));
            }
            return t && { ...t, status: "done", messageId: event.message_id, text: event.text };
          });
          mutateGlobal(`/api/conversations/${event.conversation_id}/messages`);
          mutateGlobal(CHATS_KEY);
          mutateGlobal(USAGE_KEY);
          break;
        case "error":
          setTurn((t) => t && { ...t, status: "error", error: event.message });
          mutateGlobal(CHATS_KEY);
          if (messagesKey) mutate();
          break;
      }
    },
    [mutate, mutateGlobal, messagesKey],
  );

  const { send, connected } = useChatSocket(onEvent);
  const busy = turn?.status === "streaming";

  function onSend(text: string): boolean {
    if (!send(conversationId, text)) return false;
    setTurn({ conversationId, userText: text, text: "", steps: [], notes: [], status: "streaming" });
    return true;
  }

  // Only show the live turn in the chat it belongs to.
  const liveTurn = turn && turn.conversationId === conversationId ? turn : null;
  const messages = saved ?? [];
  const showUser = liveTurn && !messages.some((m) => m.id === liveTurn.userMessageId);
  const showAnswer =
    liveTurn && liveTurn.status !== "error" && !messages.some((m) => m.id === liveTurn.messageId);

  // Keep the newest text in view while it streams, unless you scrolled up.
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  useEffect(() => {
    const el = scroller.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, liveTurn?.text, liveTurn?.steps.length]);

  const empty = !messages.length && !liveTurn;

  return (
    <div className="flex h-full flex-col">
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {empty ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <p className="text-2xl font-semibold">What&apos;s on your mind?</p>
            <p className="text-muted">
              Chat in English, اردو or Roman Urdu. Ask about anything, or what&apos;s new today.
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
            {loadError && <ErrorNotice message={`Couldn't load this chat: ${loadError.message}`} />}
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} text={m.content} />
              ) : (
                <AssistantMessage
                  key={m.id}
                  text={m.content}
                  steps={m.steps}
                  cost={m.cost_usd}
                  notes={notesByMessage[m.id]}
                />
              ),
            )}
            {showUser && <UserMessage text={liveTurn.userText} />}
            {showAnswer && (
              <AssistantMessage
                text={liveTurn.text}
                steps={liveTurn.steps}
                notes={liveTurn.notes}
                streaming={liveTurn.status === "streaming"}
              />
            )}
            {liveTurn?.status === "error" && <ErrorNotice message={liveTurn.error ?? "Error"} />}
          </div>
        )}
      </div>
      <Composer
        onSend={onSend}
        busy={busy}
        disabledReason={connected ? undefined : "Connecting to the backend…"}
      />
    </div>
  );
}
