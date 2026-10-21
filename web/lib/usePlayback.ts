"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clamp } from "./replay";

export const SPEEDS = [1, 2, 5, 10, 20];

// A clock that runs at `speed` times real time between `start` and `end`. `t` updates every frame, for drawing cars;
// `slow` updates four times a second, for the panels that would only flicker if redrawn every frame.
export function usePlayback(start: number, end: number, initial = start) {
  const [t, setT] = useState(initial);
  const [slow, setSlow] = useState(initial);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(10);
  const live = useRef({ t: initial, speed: 10 });
  const slowAt = useRef(0);

  useEffect(() => {
    live.current.speed = speed;
  }, [speed]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000); // a hidden tab must not make the clock jump
      last = now;
      let next = live.current.t + dt * live.current.speed;
      let stop = false;
      if (next >= end) {
        next = end;
        stop = true;
      }
      live.current.t = next;
      setT(next);
      if (now - slowAt.current > 250 || stop) {
        slowAt.current = now;
        setSlow(next);
      }
      if (stop) setPlaying(false);
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, end]);

  const seek = useCallback(
    (x: number) => {
      const v = clamp(x, start, end);
      live.current.t = v;
      setT(v);
      setSlow(v);
    },
    [start, end],
  );
  const skip = useCallback((dt: number) => seek(live.current.t + dt), [seek]);
  const toggle = useCallback(() => {
    if (!playing && live.current.t >= end) seek(start);
    setPlaying((p) => !p);
  }, [playing, end, start, seek]);

  return { t, slow, playing, speed, setSpeed, seek, skip, toggle };
}
