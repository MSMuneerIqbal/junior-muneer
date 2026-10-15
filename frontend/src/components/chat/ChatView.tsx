"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { CallView } from "@/components/call/CallView";
import { Composer } from "@/components/chat/Composer";
import type { VoiceMessage } from "@/components/chat/MicButton";
import { AssistantMessage, ErrorNotice, UserMessage } from "@/components/chat/MessageView";
import { fetcher } from "@/lib/api";
import { isApprovalsKey, isChatsKey, PAUSE_KEY, SETTINGS_KEY, USAGE_KEY } from "@/lib/keys";
import type { ApprovalItem, ChatEvent, MemoryNote, Message, Step } from "@/lib/types";
import { useChatSocket } from "@/lib/useChatSocket";
import { speakMessage } from "@/lib/player";
import type { ChatSummary, Settings } from "@/lib/types";

/** The answer being written right now. */
type Turn = {
  conversationId: number | null;
  userText: string;
  userAudioId?: string;
  userMessageId?: number;
  text: string;
  steps: Step[];
  notes: MemoryNote[];
  approvals: ApprovalItem[];
  status: "streaming" | "done" | "error";
  error?: string;
  messageId?: number;
};

function upsertStep(steps: Step[], step: Step): Step[] {
  const i = steps.findIndex((s) => s.id === step.id);
  return i === -1 ? [...steps, step] : steps.map((s, j) => (j === i ? step : s));
}

/** One of your recent messages (last 3 minutes) has no answer saved yet. */
function answerPending(messages: Message[] | undefined): boolean {
  if (!messages?.length) return false;
  const yours = messages.filter((m) => m.role === "user");
  const answers = messages.length - yours.length;
  const last = yours[yours.length - 1];
  return yours.length > answers && !!last && Date.now() - Date.parse(last.created_at) < 180_000;
}

export function ChatView() {
  const params = useSearchParams();
  const conversationId = params.get("c") ? Number(params.get("c")) : null;
  const messagesKey = conversationId ? `/api/conversations/${conversationId}/messages` : null;
  // The latest turn, kept in step with every update, for event handlers.
  const turnRef = useRef<Turn | null>(null);
  // If you came back while an answer was still being written, check every 2 s until it's saved.
  const { data: saved, error: loadError, mutate } = useSWR<Message[]>(messagesKey, fetcher, {
    refreshInterval: (data) => (!turnRef.current && answerPending(data) ? 2000 : 0),
  });
  const { mutate: mutateGlobal } = useSWRConfig();

  const { data: pause } = useSWR<{ paused: boolean }>(PAUSE_KEY, fetcher);
  const { data: summary } = useSWR<ChatSummary>(
    conversationId ? `/api/conversations/${conversationId}/summary` : null,
    fetcher,
  );
  const { data: settings } = useSWR<Settings>(SETTINGS_KEY, fetcher);
  const autoplay = settings?.voice_autoplay ?? true;
  const [turn, setTurnState] = useState<Turn | null>(null);
  const setTurn = useCallback((next: Turn | null | ((t: Turn | null) => Turn | null)) => {
    const value = typeof next === "function" ? next(turnRef.current) : next;
    turnRef.current = value;
    setTurnState(value);
  }, []);
  // Memory notes stay under the answer they came with (this session only).
  const [notesByMessage, setNotesByMessage] = useState<Record<number, MemoryNote[]>>({});

  const onEvent = useCallback(
    (event: ChatEvent) => {
      switch (event.type) {
        case "conversation":
          window.history.replaceState(null, "", `/?c=${event.id}`);
          setTurn((t) => t && { ...t, conversationId: event.id });
          mutateGlobal(isChatsKey);
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
        case "approval":
          setTurn((t) => t && { ...t, approvals: [...t.approvals, event.item] });
          mutateGlobal(isApprovalsKey);
          break;
        case "done": {
          const t = turnRef.current;
          if (t?.notes.length) {
            const notes = t.notes;
            setNotesByMessage((n) => ({ ...n, [event.message_id]: notes }));
          }
          // You spoke, so he answers aloud too (if auto-play is on).
          if (t?.userAudioId && autoplay && event.text) void speakMessage(event.message_id);
          setTurn((t) => t && { ...t, status: "done", messageId: event.message_id, text: event.text });
          mutateGlobal(`/api/conversations/${event.conversation_id}/messages`);
          mutateGlobal(`/api/conversations/${event.conversation_id}/summary`);
          mutateGlobal(isChatsKey);
          mutateGlobal(USAGE_KEY);
          break;
        }
        case "error":
          setTurn((t) => t && { ...t, status: "error", error: event.message });
          mutateGlobal(isChatsKey);
          if (messagesKey) mutate();
          break;
      }
    },
    [mutate, mutateGlobal, messagesKey, autoplay, setTurn],
  );

  const { send, connected } = useChatSocket(onEvent);
  const router = useRouter();
  const [inCall, setInCall] = useState(false);
  const busy = turn?.status === "streaming";

  function onSend(text: string): boolean {
    if (!send(conversationId, text)) return false;
    setTurn({ conversationId, userText: text, text: "", steps: [], notes: [], approvals: [], status: "streaming" });
    return true;
  }

  function onVoice(voice: VoiceMessage) {
    send(conversationId, voice.text, { audio_id: voice.audioId, audio_seconds: voice.seconds });
    setTurn({
      conversationId,
      userText: voice.text,
      userAudioId: voice.audioId,
      text: "",
      steps: [],
      notes: [],
      approvals: [],
      status: "streaming",
    });
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
      <div className="flex items-center justify-between gap-3 border-b border-line px-3 py-1.5 sm:px-6">
        <span className="truncate text-xs text-muted" data-testid="chat-summary">
          {summary?.kind === "call" && summary.call_seconds !== null
            ? `📞 Live call · ${Math.floor(summary.call_seconds / 60)}:${String(
                Math.round(summary.call_seconds % 60),
              ).padStart(2, "0")} · $${summary.cost_usd.toFixed(4)}`
            : summary && summary.cost_usd > 0
              ? `This chat: $${summary.cost_usd.toFixed(4)}`
              : ""}
        </span>
        <button
          onClick={() => setInCall(true)}
          className="rounded-full border border-line px-3 py-1 text-sm hover:bg-panel-2"
          title="Talk hands-free, like a phone call"
        >
          📞 Live call
        </button>
      </div>
      {inCall && (
        <CallView
          onClose={(id) => {
            setInCall(false);
            if (id) router.push(`/?c=${id}`);
          }}
        />
      )}
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
                <UserMessage key={m.id} text={m.content} audioId={m.audio_file} />
              ) : (
                <AssistantMessage
                  key={m.id}
                  messageId={m.id}
                  text={m.content}
                  steps={m.steps}
                  cost={m.cost_usd}
                  notes={notesByMessage[m.id]}
                  approvals={m.approvals}
                />
              ),
            )}
            {showUser && <UserMessage text={liveTurn.userText} audioId={liveTurn.userAudioId} />}
            {showAnswer && (
              <AssistantMessage
                text={liveTurn.text}
                steps={liveTurn.steps}
                notes={liveTurn.notes}
                approvals={liveTurn.approvals}
                streaming={liveTurn.status === "streaming"}
              />
            )}
            {liveTurn?.status === "error" && <ErrorNotice message={liveTurn.error ?? "Error"} />}
          </div>
        )}
      </div>
      {pause?.paused && (
        <div className="bg-warn-soft px-4 py-1.5 text-center text-sm text-warn">
          ⏸ Everything is paused. Chat still works; background work and actions are stopped.
        </div>
      )}
      <Composer
        onSend={onSend}
        onVoice={onVoice}
        busy={busy}
        notice={
          connected ? undefined : "Connecting to the backend… messages are sent once it's up."
        }
      />
    </div>
  );
}
