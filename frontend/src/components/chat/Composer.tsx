"use client";

import { useRef, useState, type KeyboardEvent } from "react";

/** The message box. Enter sends; Shift+Enter makes a new line. */
export function Composer({
  onSend,
  busy,
  notice,
}: {
  onSend: (text: string) => boolean;
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
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-line bg-panel px-3 py-2 focus-within:border-accent">
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
          className="max-h-[200px] min-h-[28px] flex-1 resize-none bg-transparent py-1 outline-none placeholder:text-muted"
        />
        <button
          onClick={submit}
          disabled={!text.trim() || busy}
          aria-label="Send"
          className="rounded-full bg-accent px-3.5 py-1.5 text-sm font-medium text-accent-fg disabled:opacity-40"
        >
          {busy ? "…" : "Send"}
        </button>
      </div>
      {notice && <p className="mx-auto mt-1.5 max-w-3xl text-xs text-warn">{notice}</p>}
    </div>
  );
}
