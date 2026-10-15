"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BACKEND_URL, send } from "@/lib/api";

export type CallLine = {
  id: string;
  who: "you" | "junior";
  text: string;
  final: boolean;
  ignored?: boolean; // taken as background noise, so he didn't reply
};
export type CallStatus = "idle" | "connecting" | "live" | "ended" | "error";
export type Activity = "listening" | "you" | "thinking" | "speaking" | "checking";

type ServerEvent = { type: string; [key: string]: unknown };

/**
 * A live voice call over WebRTC. The browser sends its offer to our backend, which
 * creates the call at OpenAI (so the browser never holds a key) and stays attached
 * to save the transcript and run tools. Here we only play audio and show the transcript.
 */
export function useLiveCall() {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [activity, setActivity] = useState<Activity>("listening");
  const [lines, setLines] = useState<CallLine[]>([]);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const pc = useRef<RTCPeerConnection | null>(null);
  const mic = useRef<MediaStream | null>(null);
  const speaker = useRef<HTMLAudioElement | null>(null);
  const callId = useRef<string | null>(null);
  // True from a tool call until his real answer starts (fillers don't count).
  const searching = useRef(false);
  // If no reply starts soon after you speak (it was only noise), go back to listening.
  const replyWait = useRef<ReturnType<typeof setTimeout> | null>(null);

  const upsert = useCallback((id: string, who: CallLine["who"], text: string, final: boolean, append: boolean) => {
    setLines((all) => {
      const i = all.findIndex((l) => l.id === id);
      if (i === -1) return [...all, { id, who, text, final }];
      const next = [...all];
      next[i] = { ...next[i], text: append ? next[i].text + text : text, final };
      return next;
    });
  }, []);

  const onEvent = useCallback(
    (e: ServerEvent) => {
      const itemId = String(e.item_id ?? e.response_id ?? "");
      switch (e.type) {
        case "input_audio_buffer.speech_started":
          setActivity("you");
          break;
        case "input_audio_buffer.speech_stopped":
          setActivity("thinking");
          break;
        case "conversation.item.input_audio_transcription.delta":
          upsert(`u-${itemId}`, "you", String(e.delta ?? ""), false, true);
          break;
        case "conversation.item.input_audio_transcription.completed":
          upsert(`u-${itemId}`, "you", String(e.transcript ?? ""), true, false);
          if (replyWait.current) clearTimeout(replyWait.current);
          replyWait.current = setTimeout(() => {
            // Nothing came back: the backend set it aside as noise.
            setActivity((a) => (a === "thinking" ? "listening" : a));
            setLines((all) =>
              all.map((l) => (l.id === `u-${itemId}` ? { ...l, ignored: true } : l)),
            );
          }, 4000);
          break;
        case "response.created": {
          if (replyWait.current) clearTimeout(replyWait.current);
          const filler =
            (e.response as { metadata?: { kind?: string } } | undefined)?.metadata?.kind ===
            "filler";
          if (!filler) searching.current = false;
          break;
        }
        case "response.output_audio_transcript.delta":
          setActivity(searching.current ? "checking" : "speaking");
          upsert(`j-${itemId}`, "junior", String(e.delta ?? ""), false, true);
          break;
        case "response.output_audio_transcript.done":
          upsert(`j-${itemId}`, "junior", String(e.transcript ?? ""), true, false);
          break;
        case "response.function_call_arguments.done":
          searching.current = true;
          setActivity("checking");
          break;
        case "output_audio_buffer.stopped":
        case "response.done":
          // While a search runs (and "still looking…" fillers play), keep showing it.
          setActivity(searching.current ? "checking" : "listening");
          break;
      }
    },
    [upsert],
  );

  const cleanup = useCallback(() => {
    pc.current?.close();
    pc.current = null;
    mic.current?.getTracks().forEach((t) => t.stop());
    mic.current = null;
    if (speaker.current) speaker.current.srcObject = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setLines([]);
    setMuted(false);
    setActivity("listening");
    setStatus("connecting");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser can't use the microphone here (needs localhost or HTTPS).");
      }
      const stream = await navigator.mediaDevices
        .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
        .catch(() => {
          throw new Error("Microphone access was blocked. Allow it in the browser's address bar.");
        });
      mic.current = stream;
      setMicStream(stream);

      const peer = new RTCPeerConnection();
      pc.current = peer;
      if (!speaker.current) {
        const el = new Audio();
        el.autoplay = true;
        speaker.current = el;
      }
      const audio = speaker.current;
      peer.ontrack = (e) => {
        audio.srcObject = e.streams[0];
        setRemoteStream(e.streams[0]);
      };
      peer.addTrack(stream.getAudioTracks()[0], stream);
      const channel = peer.createDataChannel("oai-events");
      channel.onmessage = (m) => {
        try {
          onEvent(JSON.parse(m.data));
        } catch {}
      };
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === "connected") {
          setStatus("live");
          setStartedAt(Date.now());
        }
        if (["failed", "closed", "disconnected"].includes(peer.connectionState)) {
          setStatus((s) => (s === "live" || s === "connecting" ? "ended" : s));
          cleanup();
        }
      };

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const answer = await send<{ sdp: string; call_id: string; conversation_id: number }>(
        "POST",
        "/api/call/start",
        { sdp: offer.sdp },
      );
      callId.current = answer.call_id;
      setConversationId(answer.conversation_id);
      await peer.setRemoteDescription({ type: "answer", sdp: answer.sdp });
    } catch (e) {
      cleanup();
      setError(e instanceof Error ? e.message : "Couldn't start the call");
      setStatus("error");
    }
  }, [cleanup, onEvent]);

  const end = useCallback(async () => {
    const id = callId.current;
    callId.current = null;
    cleanup();
    setStatus("ended");
    if (id) {
      try {
        await send("POST", "/api/call/end", { call_id: id });
      } catch {}
    }
  }, [cleanup]);

  const toggleMute = useCallback(() => {
    const track = mic.current?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setMuted(!track.enabled);
  }, []);

  // Hang up if the page is closed mid-call.
  useEffect(() => {
    const onUnload = () => {
      if (callId.current) {
        navigator.sendBeacon?.(
          `${BACKEND_URL}/api/call/end`,
          new Blob([JSON.stringify({ call_id: callId.current })], { type: "application/json" }),
        );
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      cleanup();
    };
  }, [cleanup]);

  return {
    status,
    activity,
    lines,
    muted,
    error,
    conversationId,
    startedAt,
    micStream,
    remoteStream,
    start,
    end,
    toggleMute,
  };
}
