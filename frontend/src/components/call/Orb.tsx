"use client";

import { useEffect, useRef } from "react";
import type { Activity } from "@/lib/useLiveCall";

/** Live loudness (0..1) of an audio stream, read without re-rendering React. */
function meter(ctx: AudioContext, stream: MediaStream | null) {
  if (!stream || !stream.getAudioTracks().length) return () => 0;
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  return () => {
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) sum += ((v - 128) / 128) ** 2;
    return Math.min(1, Math.sqrt(sum / data.length) * 4);
  };
}

/**
 * The call's visual: a glowing core that swells with his voice, a ring of light
 * bars that dances with yours, and a scanning sweep while he looks something up.
 */
export function Orb({
  mic,
  remote,
  activity,
  muted,
}: {
  mic: MediaStream | null;
  remote: MediaStream | null;
  activity: Activity;
  muted: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const state = useRef({ activity, muted });

  useEffect(() => {
    state.current = { activity, muted };
  }, [activity, muted]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const g = el.getContext("2d");
    if (!g) return;
    const audio = new AudioContext();
    const you = meter(audio, mic);
    const him = meter(audio, remote);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let smoothYou = 0;
    let smoothHim = 0;
    let frame = 0;
    let raf = 0;

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      const size = el!.clientWidth;
      if (el!.width !== size * dpr) {
        el!.width = size * dpr;
        el!.height = size * dpr;
      }
      g!.setTransform(dpr, 0, 0, dpr, 0, 0);
      g!.clearRect(0, 0, size, size);
      const c = size / 2;
      frame += 1;
      smoothYou += ((state.current.muted ? 0 : you()) - smoothYou) * 0.25;
      smoothHim += (him() - smoothHim) * 0.25;
      const t = reduce ? 0 : frame / 60;

      // Outer ring: 64 light bars that follow your voice.
      const bars = 64;
      const ringR = size * 0.36;
      for (let i = 0; i < bars; i++) {
        const a = (i / bars) * Math.PI * 2 + t * 0.15;
        const wobble = 0.5 + 0.5 * Math.sin(a * 3 + t * 2);
        const len = size * (0.015 + smoothYou * 0.09 * (0.4 + wobble));
        g!.strokeStyle = `rgba(167, 139, 250, ${0.25 + smoothYou * 0.75})`;
        g!.lineWidth = 2;
        g!.beginPath();
        g!.moveTo(c + Math.cos(a) * ringR, c + Math.sin(a) * ringR);
        g!.lineTo(c + Math.cos(a) * (ringR + len), c + Math.sin(a) * (ringR + len));
        g!.stroke();
      }

      // Thin orbit lines.
      for (let k = 0; k < 2; k++) {
        g!.strokeStyle = `rgba(45, 212, 191, ${0.18 - k * 0.06})`;
        g!.lineWidth = 1;
        g!.beginPath();
        g!.ellipse(c, c, size * (0.3 + k * 0.04), size * (0.12 + k * 0.03), t * (0.3 + k * 0.2), 0, Math.PI * 2);
        g!.stroke();
      }

      // Scanning sweep while he's looking something up.
      if (state.current.activity === "checking") {
        const a = t * 2.5;
        const sweep = g!.createConicGradient(a, c, c);
        sweep.addColorStop(0, "rgba(45, 212, 191, 0.45)");
        sweep.addColorStop(0.12, "rgba(45, 212, 191, 0)");
        sweep.addColorStop(1, "rgba(45, 212, 191, 0)");
        g!.fillStyle = sweep;
        g!.beginPath();
        g!.arc(c, c, ringR - 4, 0, Math.PI * 2);
        g!.fill();
      }

      // Glowing core: swells and brightens with his voice.
      const breathe = reduce ? 0 : Math.sin(t * 1.6) * 0.01;
      const coreR = size * (0.17 + breathe + smoothHim * 0.07);
      const glow = g!.createRadialGradient(c, c, coreR * 0.2, c, c, coreR * 2.4);
      glow.addColorStop(0, `rgba(94, 234, 212, ${0.55 + smoothHim * 0.4})`);
      glow.addColorStop(0.4, `rgba(56, 189, 248, ${0.18 + smoothHim * 0.25})`);
      glow.addColorStop(1, "rgba(56, 189, 248, 0)");
      g!.fillStyle = glow;
      g!.beginPath();
      g!.arc(c, c, coreR * 2.4, 0, Math.PI * 2);
      g!.fill();

      const core = g!.createRadialGradient(c - coreR * 0.3, c - coreR * 0.3, coreR * 0.1, c, c, coreR);
      core.addColorStop(0, "rgba(240, 253, 250, 0.95)");
      core.addColorStop(0.5, "rgba(45, 212, 191, 0.9)");
      core.addColorStop(1, "rgba(14, 116, 144, 0.95)");
      g!.fillStyle = core;
      g!.beginPath();
      g!.arc(c, c, coreR, 0, Math.PI * 2);
      g!.fill();

      raf = requestAnimationFrame(draw);
    }
    draw();
    return () => {
      cancelAnimationFrame(raf);
      void audio.close();
    };
  }, [mic, remote]);

  return <canvas ref={canvas} className="size-[min(82vw,340px)] shrink-0 md:size-[min(40vw,440px)]" aria-hidden />;
}
