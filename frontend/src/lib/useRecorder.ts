"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Recording = { blob: Blob; seconds: number; mimeType: string };

const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

function pickType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

/** Records from the microphone. The mic is released as soon as recording stops. */
export function useRecorder() {
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const finish = useRef<((r: Recording | null) => void) | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 200);
    return () => clearInterval(id);
  }, [recording]);

  const start = useCallback(async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't record audio here (the mic needs localhost or HTTPS).");
      return false;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access was blocked. Allow it in the browser's address bar.");
      return false;
    }
    const mimeType = pickType();
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunks.current = [];
    rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const seconds = (Date.now() - startedAt.current) / 1000;
      const type = rec.mimeType || mimeType || "audio/webm";
      const done = finish.current;
      finish.current = null;
      done?.(chunks.current.length ? { blob: new Blob(chunks.current, { type }), seconds, mimeType: type } : null);
    };
    recorder.current = rec;
    startedAt.current = Date.now();
    setElapsed(0);
    rec.start(250);
    setRecording(true);
    return true;
  }, []);

  /** Stops and returns the recording (or null if cancelled or empty). */
  const stop = useCallback((cancel = false): Promise<Recording | null> => {
    const rec = recorder.current;
    recorder.current = null;
    setRecording(false);
    if (!rec || rec.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      finish.current = (r) => resolve(cancel ? null : r);
      rec.stop();
    });
  }, []);

  // Release the mic if the page goes away mid-recording.
  useEffect(() => () => void recorder.current?.stop(), []);

  return { recording, elapsed, error, start, stop, setError };
}
