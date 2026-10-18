"use client";

import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { MicButton, type VoiceMessage } from "@/components/chat/MicButton";
import { ModeSelect } from "@/components/chat/ModeSelect";
import { PasteBox } from "@/components/chat/PasteBox";
import { ClipboardIcon, PaperclipIcon, SendIcon } from "@/components/icons";
import { BACKEND_URL } from "@/lib/api";
import { emptyPaste, LONG_PASTE_CHARS, type PasteDraft } from "@/lib/paste";
import { urduClass } from "@/lib/urdu";

/** The message box. Enter sends; Shift+Enter makes a new line. */
export function Composer({
  onSend,
  onVoice,
  busy,
  notice,
  initialText = "",
}: {
  onSend: (text: string, paste?: PasteDraft) => boolean;
  onVoice: (voice: VoiceMessage) => void;
  busy: boolean;
  notice?: string;
  // Text to start with, e.g. "Write idea 3" from the Social page (you still press Send).
  initialText?: string;
}) {
  const [text, setText] = useState(initialText);
  const [paste, setPaste] = useState<PasteDraft | null>(null);
  // Long text you pasted into the message box was moved to the Paste box (can be undone).
  const [moved, setMoved] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [attaching, setAttaching] = useState(false);
  const [fileProblem, setFileProblem] = useState<string | null>(null);
  const pasteText = paste?.text.trim() ?? "";
  const canSend = !busy && (!!text.trim() || !!pasteText);

  function grow() {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  function submit() {
    if (!canSend) return;
    if (onSend(text.trim(), pasteText ? { ...paste!, text: pasteText } : undefined)) {
      setText("");
      setPaste(null);
      setMoved(false);
      requestAnimationFrame(grow);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function onPasteText(e: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = e.clipboardData.getData("text");
    if (paste || text.trim() || pasted.trim().length < LONG_PASTE_CHARS) return;
    e.preventDefault();
    setPaste(emptyPaste(pasted.trim()));
    setMoved(true);
    box.current?.focus();
  }

  /** 📎: the file is kept by the app; its tag ("[file 3: CV.pdf (PDF, 52 KB)]") goes at the start of your message. */
  async function attach(file: File) {
    setAttaching(true);
    setFileProblem(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${BACKEND_URL}/api/files`, { method: "POST", body: form });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail ?? r.statusText);
      setText((t) => `${body.tag}\n${t}`.trimEnd() + (t ? "" : "\n"));
      requestAnimationFrame(() => {
        grow();
        box.current?.focus();
      });
    } catch (e) {
      setFileProblem(e instanceof Error ? `Couldn't attach it: ${e.message}` : "Couldn't attach it");
    } finally {
      setAttaching(false);
      if (picker.current) picker.current.value = "";
    }
  }

  function keepAsMine() {
    if (!paste) return;
    setText(paste.text);
    setPaste(null);
    setMoved(false);
    requestAnimationFrame(grow);
  }

  return (
    <div className="border-t border-line bg-bg px-3 pt-3 pb-4 sm:px-6">
      {paste && (
        <PasteBox
          value={paste}
          onChange={setPaste}
          onClose={() => {
            setPaste(null);
            setMoved(false);
          }}
          hint={
            moved ? (
              <>
                Long text went to the Paste box, so he treats it as someone else&apos;s words.{" "}
                <button type="button" onClick={keepAsMine} className="font-medium text-accent hover:underline">
                  It&apos;s my own message
                </button>
              </>
            ) : undefined
          }
        />
      )}
      <div className="relative mx-auto flex max-w-3xl items-end gap-1.5 rounded-3xl border border-line bg-panel py-1.5 pr-1.5 pl-2 shadow-sm focus-within:border-accent">
        <button
          type="button"
          onClick={() => (paste ? setPaste(null) : setPaste(emptyPaste()))}
          aria-label={paste ? "Close the Paste box" : "Paste from another site"}
          aria-pressed={!!paste}
          title="Paste a post, job or message from another site"
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
            paste ? "bg-accent-soft text-accent" : "text-muted hover:bg-panel-2 hover:text-ink"
          }`}
        >
          <ClipboardIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={attaching}
          aria-label="Attach a file"
          title="Attach a file (e.g. to save it to your Google Drive)"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-panel-2 hover:text-ink disabled:opacity-50"
        >
          {attaching ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted border-t-transparent" />
          ) : (
            <PaperclipIcon className="h-5 w-5" />
          )}
        </button>
        <input
          ref={picker}
          type="file"
          className="hidden"
          aria-label="File to attach"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void attach(file);
          }}
        />
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
          onPaste={onPasteText}
          placeholder={paste ? "What should I do with it? e.g. write a short comment" : "Message Junior Muneer…"}
          aria-label="Message"
          className={`max-h-[200px] min-h-[28px] flex-1 resize-none self-center bg-transparent py-1.5 outline-none placeholder:text-muted ${urduClass(text)}`}
        />
        <MicButton onVoice={onVoice} disabled={busy} />
        <button
          onClick={submit}
          disabled={!canSend}
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
      <div className="mx-auto mt-2 flex max-w-3xl flex-wrap items-center gap-x-3 gap-y-1 px-1">
        <ModeSelect />
        {notice && <p className="text-xs text-warn">{notice}</p>}
        {fileProblem && (
          <p role="alert" className="text-xs text-danger">
            {fileProblem}
          </p>
        )}
      </div>
    </div>
  );
}
