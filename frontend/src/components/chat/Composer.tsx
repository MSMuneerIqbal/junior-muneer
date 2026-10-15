"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { MicButton, type VoiceMessage } from "@/components/chat/MicButton";
import { SendIcon } from "@/components/icons";
import { urduClass } from "@/lib/urdu";

/** The message box. Enter sends; Shift+Enter makes a new line. */
export function Composer({
  onSend,
  onVoice,
  busy,
  notice,
}: {
  onSend: (text: string) => boolean;
  onVoice: (voice: VoiceMessage) => void;
  busy: boolean;
  notice?: string;
}) {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  function grow() {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  function submit() {
    const value = text.trim();
    if (!value || busy) return;
    if (onSend(value)) {
      setText("");
      requestAnimationFrame(grow);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="border-t border-line bg-bg px-3 pt-3 pb-4 sm:px-6">
      <div className="relative mx-auto flex max-w-3xl items-end gap-1.5 rounded-3xl border border-line bg-panel py-1.5 pr-1.5 pl-4 shadow-sm focus-within:border-accent">
        <textarea
          ref={box}
          rows={1}
          dir="auto"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            grow();
          }}
          onKeyDown={onKeyDown}
          placeholder="Message Junior Muneer…"
          aria-label="Message"
          className={`max-h-[200px] min-h-[28px] flex-1 resize-none self-center bg-transparent py-1.5 outline-none placeholder:text-muted ${urduClass(text)}`}
        />
        <MicButton onVoice={onVoice} disabled={busy} />
        <button
          onClick={submit}
          disabled={!text.trim() || busy}
          aria-label="Send"
          title="Send (Enter)"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg transition hover:brightness-110 disabled:opacity-30"
        >
          {busy ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent-fg border-t-transparent" />
          ) : (
            <SendIcon className="h-5 w-5" />
          )}
        </button>
      </div>
      {notice && <p className="mx-auto mt-1.5 max-w-3xl text-xs text-warn">{notice}</p>}
    </div>
  );
}
