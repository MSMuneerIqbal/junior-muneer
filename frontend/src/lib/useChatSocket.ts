"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import type { PasteDraft } from "@/lib/paste";
import type { ChatEvent } from "@/lib/types";

/**
 * One WebSocket to the backend, reconnecting by itself.
 * Messages sent while it's (re)connecting wait in a queue and go out once it opens.
 */
export function useChatSocket(onEvent: (event: ChatEvent) => void) {
  const socket = useRef<WebSocket | null>(null);
  const handler = useRef(onEvent);
  const queue = useRef<string[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = 500;

    function connect() {
      const ws = new WebSocket(wsUrl());
      socket.current = ws;
      ws.onopen = () => {
        delay = 500;
        setConnected(true);
        while (queue.current.length) ws.send(queue.current.shift()!);
      };
      ws.onmessage = (e) => {
        try {
          handler.current(JSON.parse(e.data) as ChatEvent);
        } catch {}
      };
      ws.onclose = () => {
        setConnected(false);
        if (!stopped) {
          retry = setTimeout(connect, delay);
          delay = Math.min(delay * 2, 8000);
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      socket.current?.close();
    };
  }, []);

  const send = useCallback(
    (
      conversationId: number | null,
      text: string,
      extra?: { audio_id: string; audio_seconds: number } | { paste: PasteDraft },
    ) => {
      const payload = JSON.stringify({
        type: "message",
        conversation_id: conversationId,
        text,
        ...extra,
      });
      const ws = socket.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
      else queue.current.push(payload);
      return true;
    },
    [],
  );

  return { send, connected };
}
