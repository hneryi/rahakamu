/**
 * Money value that counts up/down to its new value (ease-out, ~700 ms).
 * Gives balance and safe-to-spend numbers a sense of "live" data without
 * re-rendering the whole card on every frame (state is local to this text).
 */
import { useEffect, useRef, useState } from 'react';

import { useT } from '@/i18n';
import { Text, type AppTextProps } from './Text';

type Props = Omit<AppTextProps, 'children'> & { value: number; decimals?: number; sign?: boolean; duration?: number };

export function AnimatedMoney({ value, decimals, sign, duration = 700, ...text }: Props) {
  const { money } = useT();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = Date.now();
    const a = from.current;
    let raf = 0;
    const step = () => {
      const k = Math.min(1, (Date.now() - start) / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(a + (value - a) * eased);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = value;
    };
  }, [value, duration]);
  return (
    <Text money {...text}>
      {money(shown, { decimals: decimals ?? (Math.abs(value) >= 100 ? 0 : 2), sign })}
    </Text>
  );
}
