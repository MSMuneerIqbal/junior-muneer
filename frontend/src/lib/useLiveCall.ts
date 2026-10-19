"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BACKEND_URL, send, wsUrl } from "@/lib/api";

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

/** Gemini Live calls: 16-bit PCM both ways over our backend's WebSocket (16 kHz up, 24 kHz down). */
function pcmToFloat(data: ArrayBuffer): Float32Array<ArrayBuffer> {
  const pcm = new Int16Array(data);
  const out = new Float32Array(new ArrayBuffer(pcm.length * 4));
  for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 0x8000;
  return out;
}

/**
 * A live voice call, with the engine chosen in Settings → Live calls:
 * - OpenAI Realtime over WebRTC: the browser sends its offer to our backend, which creates the call at OpenAI
 *   (so the browser never holds a key) and stays attached to save the transcript and run tools.
 * - Gemini Live: the browser streams the microphone to our backend's WebSocket, which talks to Gemini (again,
 *   no key in the browser) and streams his voice back.
 * Here we only play audio and show the transcript.
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
  // Gemini Live: the socket, the microphone (16 kHz) and speaker (24 kHz) audio, and his queued voice.
  const socket = useRef<WebSocket | null>(null);
  const captureCtx = useRef<AudioContext | null>(null);
  const playCtx = useRef<AudioContext | null>(null);
  const playing = useRef<Set<AudioBufferSourceNode>>(new Set());
  const playAt = useRef(0);
  const turn = useRef(0);


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
          break;
        case "conversation.item.deleted":
          // The backend took it out of the conversation: it was only noise.
          setLines((all) =>
            all.map((l) => (l.id === `u-${itemId}` ? { ...l, ignored: true } : l)),
          );
          setActivity((a) => (a === "thinking" ? "listening" : a));
          break;
        case "response.created": {
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

  const stopVoice = useCallback(() => {
    // You spoke over him (or the call ended): stop what's playing and what's queued.
    playing.current.forEach((s) => {
      try {
        s.stop();
      } catch {}
    });
    playing.current.clear();
    playAt.current = 0;
  }, []);

  const cleanup = useCallback(() => {
    pc.current?.close();
    pc.current = null;
    if (socket.current && socket.current.readyState <= WebSocket.OPEN) {
      try {
        socket.current.send(JSON.stringify({ type: "end" }));
      } catch {}
      socket.current.close();
    }
    socket.current = null;
    stopVoice();
    void captureCtx.current?.close();
    captureCtx.current = null;
    void playCtx.current?.close();
    playCtx.current = null;
    mic.current?.getTracks().forEach((t) => t.stop());
    mic.current = null;
    if (speaker.current) speaker.current.srcObject = null;
  }, [stopVoice]);

  /** His voice: 24 kHz PCM chunks, played one after another without gaps. */
  const playChunk = useCallback((data: ArrayBuffer) => {
    const ctx = playCtx.current;
    if (!ctx) return;
    const samples = pcmToFloat(data);
    const buffer = ctx.createBuffer(1, samples.length, 24000);
    buffer.copyToChannel(samples, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const out = (ctx as AudioContext & { junior?: MediaStreamAudioDestinationNode }).junior;
    if (out) source.connect(out);
    const at = Math.max(ctx.currentTime, playAt.current);
    source.start(at);
    playAt.current = at + buffer.duration;
    playing.current.add(source);
    source.onended = () => playing.current.delete(source);
  }, []);

  const startGemini = useCallback(
    async (stream: MediaStream) => {
      // The microphone at 16 kHz (the browser resamples), sent as Int16 PCM every 100 ms.
      const capture = new AudioContext({ sampleRate: 16000 });
      captureCtx.current = capture;
      await capture.audioWorklet.addModule("/pcm-capture.worklet.js");
      const node = new AudioWorkletNode(capture, "pcm-capture");
      capture.createMediaStreamSource(stream).connect(node);
      // His voice at 24 kHz, also as a stream for the call screen's sound bars.
      const play = new AudioContext({ sampleRate: 24000 });
      playCtx.current = play;
      const out = play.createMediaStreamDestination();
      (play as AudioContext & { junior?: MediaStreamAudioDestinationNode }).junior = out;
      setRemoteStream(out.stream);
      turn.current = 0;

      const ws = new WebSocket(wsUrl("/ws/call/gemini"));
      ws.binaryType = "arraybuffer";
      socket.current = ws;
      node.port.onmessage = (m: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(m.data);
      };
      ws.onmessage = (m) => {
        if (m.data instanceof ArrayBuffer) {
          setActivity(searching.current ? "checking" : "speaking");
          playChunk(m.data);
          return;
        }
        let e: ServerEvent;
        try {
          e = JSON.parse(String(m.data));
        } catch {
          return;
        }
        const n = turn.current;
        switch (e.type) {
          case "live":
            setConversationId(Number(e.conversation_id));
            setStatus("live");
            setStartedAt(Date.now());
            break;
          case "you":
            setActivity(e.final ? "thinking" : "you");
            upsert(`u-${n}`, "you", String(e.text ?? ""), Boolean(e.final), false);
            break;
          case "junior":
            searching.current = false;
            upsert(`j-${n}`, "junior", String(e.text ?? ""), Boolean(e.final), false);
            break;
          case "checking":
            searching.current = true;
            setActivity("checking");
            break;
          case "interrupted":
            stopVoice();
            setActivity("you");
            break;
          case "turn_complete":
            turn.current = n + 1;
            setActivity("listening");
            break;
          case "error":
            setError(String(e.message ?? "The call stopped"));
            setStatus("error");
            break;
          case "ended":
            setError(e.reason ? `Call ended: ${String(e.reason)}` : null);
            setStatus("ended");
            break;
        }
      };
      ws.onclose = () => {
        setStatus((s) => (s === "live" || s === "connecting" ? "ended" : s));
        socket.current = null;
      };
    },
    [playChunk, stopVoice, upsert],
  );

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

      // Which engine (Settings → Live calls → Voice engine).
      const limits = await send<{ engine?: string }>("GET", "/api/call/limits");
      if (limits.engine === "gemini") {
        await startGemini(stream);
        return;
      }

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
  }, [cleanup, onEvent, startGemini]);

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
