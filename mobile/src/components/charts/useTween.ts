/**
 * Animation helpers for the hand-built SVG charts.
 *
 * Why JS tweens instead of Reanimated animated props: SVG animated props behave
 * differently across iOS, Android and react-native-web. A ~600 ms ease-out tween
 * on a handful of chart nodes is cheap and renders identically everywhere,
 * which matters more for a demo that runs on all three platforms.
 */
import { useEffect, useRef, useState, type DependencyList } from 'react';
import { type LayoutChangeEvent } from 'react-native';

const easeOutCubic = (k: number) => 1 - Math.pow(1 - k, 3);

/** 0 → 1 progress on mount (and again whenever `deps` change). */
export function useEntrance(duration = 650, deps: DependencyList = []): number {
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf = 0;
    const start = Date.now();
    const step = () => {
      const k = Math.min(1, (Date.now() - start) / duration);
      setP(easeOutCubic(k));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return p;
}

/** Smoothly animates from the previous value to `target`. */
export function useTween(target: number, duration = 600): number {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    let raf = 0;
    const a = from.current;
    const start = Date.now();
    const step = () => {
      const k = Math.min(1, (Date.now() - start) / duration);
      const val = a + (target - a) * easeOutCubic(k);
      setV(val);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = target;
    };
  }, [target, duration]);
  return v;
}

/** Measures the width available to a chart (charts are fluid, never fixed-width). */
export function useWidth(initial = 0): [number, (e: LayoutChangeEvent) => void] {
  const [w, setW] = useState(initial);
  const onLayout = (e: LayoutChangeEvent) => {
    const nw = Math.floor(e.nativeEvent.layout.width);
    if (Math.abs(nw - w) > 1) setW(nw);
  };
  return [w, onLayout];
}

/** "Nice" axis maximum (1, 2, 2.5, 5 × 10^n) so gridlines land on round numbers. */
export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / exp;
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nf * exp;
}
