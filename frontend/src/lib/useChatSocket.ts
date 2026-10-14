"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import type { ChatEvent } from "@/lib/types";

/**
 * One WebSocket to the backend, reconnecting by itself.
 * `send` returns false when the socket isn't open (the caller shows an error).
 */
export function useChatSocket(onEvent: (event: ChatEvent) => void) {
  const socket = useRef<WebSocket | null>(null);
  const handler = useRef(onEvent);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = 500;

    function connect() {
      const ws = new WebSocket(WS_URL);
      socket.current = ws;
      ws.onopen = () => {
        delay = 500;
        setConnected(true);
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

  const send = useCallback((conversationId: number | null, text: string) => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "message", conversation_id: conversationId, text }));
    return true;
  }, []);

  return { send, connected };
}
