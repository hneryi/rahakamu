/**
 * Hand-drawn line icons (24×24, 2 px stroke) rendered with react-native-svg.
 *
 * Why not an icon font: fonts need loading on web and in the S-mobiili WebView,
 * and SF Symbols are iOS-only. A dozen inline SVGs are tiny, render identically
 * on iOS, Android and web, and inherit the theme colour.
 */
import Svg, { Circle, Path, Rect } from 'react-native-svg';

export type IconName =
  | 'home'
  | 'chart'
  | 'target'
  | 'book'
  | 'mic'
  | 'camera'
  | 'send'
  | 'settings'
  | 'close'
  | 'chevronRight'
  | 'chevronLeft'
  | 'chevronDown'
  | 'thumbUp'
  | 'thumbDown'
  | 'speaker'
  | 'speakerOff'
  | 'sparkle'
  | 'plus'
  | 'trash'
  | 'image'
  | 'info'
  | 'check'
  | 'stop'
  | 'shield'
  | 'globe'
  | 'edit'
  | 'flame'
  | 'refresh'
  | 'user';

type Props = { name: IconName; size?: number; color: string; strokeWidth?: number; fill?: string };

export function Icon({ name, size = 22, color, strokeWidth = 2, fill = 'none' }: Props) {
  const p = { stroke: color, strokeWidth, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {(() => {
        switch (name) {
          case 'home':
            return (
              <>
                <Path d="M3 10.5 12 3l9 7.5" {...p} />
                <Path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" {...p} fill={fill} />
              </>
            );
          case 'chart':
            return (
              <>
                <Path d="M4 20V10M10 20V4M16 20v-8M22 20H2" {...p} />
              </>
            );
          case 'target':
            return (
              <>
                <Circle cx={12} cy={12} r={9} {...p} />
                <Circle cx={12} cy={12} r={5} {...p} />
                <Circle cx={12} cy={12} r={1.4} {...p} fill={color} />
              </>
            );
          case 'book':
            return (
              <>
                <Path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5v-15Z" {...p} fill={fill} />
                <Path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20v-3" {...p} />
                <Path d="M9 7h7" {...p} />
              </>
            );
          case 'mic':
            return (
              <>
                <Rect x={9} y={2.5} width={6} height={12} rx={3} {...p} fill={fill} />
                <Path d="M5 11a7 7 0 0 0 14 0M12 18v3.5M8.5 21.5h7" {...p} />
              </>
            );
          case 'camera':
            return (
              <>
                <Path d="M3 8a2 2 0 0 1 2-2h2.5l1.5-2h6l1.5 2H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8Z" {...p} />
                <Circle cx={12} cy={13} r={3.6} {...p} />
              </>
            );
          case 'send':
            return <Path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" {...p} strokeWidth={strokeWidth + 0.4} />;
          case 'settings':
            return (
              <>
                <Circle cx={12} cy={12} r={3} {...p} />
                <Path
                  d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"
                  {...p}
                />
              </>
            );
          case 'close':
            return <Path d="M6 6l12 12M18 6 6 18" {...p} />;
          case 'chevronRight':
            return <Path d="m9 5 7 7-7 7" {...p} />;
          case 'chevronLeft':
            return <Path d="m15 5-7 7 7 7" {...p} />;
          case 'chevronDown':
            return <Path d="m5 9 7 7 7-7" {...p} />;
          case 'thumbUp':
            return (
              <>
                <Path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3Z" {...p} fill={fill} />
                <Path d="M7 11l4-8a2.5 2.5 0 0 1 2.5 2.5V9h5.3a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.6 20H7" {...p} fill={fill} />
              </>
            );
          case 'thumbDown':
            return (
              <>
                <Path d="M17 13V4h3a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-3Z" {...p} fill={fill} />
                <Path d="M17 13l-4 8a2.5 2.5 0 0 1-2.5-2.5V15H5.2a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.4 4H17" {...p} fill={fill} />
              </>
            );
          case 'speaker':
            return (
              <>
                <Path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4v-5Z" {...p} fill={fill} />
                <Path d="M15.5 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" {...p} />
              </>
            );
          case 'speakerOff':
            return (
              <>
                <Path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4v-5Z" {...p} />
                <Path d="m16 9.5 5 5M21 9.5l-5 5" {...p} />
              </>
            );
          case 'sparkle':
            return (
              <>
                <Path d="M12 3c.6 3.9 2.1 5.4 6 6-3.9.6-5.4 2.1-6 6-.6-3.9-2.1-5.4-6-6 3.9-.6 5.4-2.1 6-6Z" {...p} fill={fill === 'none' ? color : fill} />
                <Path d="M19 15.5c.25 1.6.9 2.25 2.5 2.5-1.6.25-2.25.9-2.5 2.5-.25-1.6-.9-2.25-2.5-2.5 1.6-.25 2.25-.9 2.5-2.5Z" {...p} fill={color} strokeWidth={1} />
              </>
            );
          case 'plus':
            return <Path d="M12 5v14M5 12h14" {...p} />;
          case 'trash':
            return (
              <>
                <Path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13" {...p} />
                <Path d="M10 11v5M14 11v5" {...p} />
              </>
            );
          case 'image':
            return (
              <>
                <Rect x={3} y={4} width={18} height={16} rx={2.5} {...p} />
                <Circle cx={9} cy={9.5} r={1.8} {...p} />
                <Path d="m21 16-5-5-9 9" {...p} />
              </>
            );
          case 'info':
            return (
              <>
                <Circle cx={12} cy={12} r={9} {...p} />
                <Path d="M12 11v5.5M12 7.6v.2" {...p} />
              </>
            );
          case 'check':
            return <Path d="m5 12.5 4.5 4.5L19 7" {...p} />;
          case 'stop':
            return <Rect x={7} y={7} width={10} height={10} rx={2} {...p} fill={color} />;
          case 'shield':
            return (
              <>
                <Path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6L12 3Z" {...p} />
                <Path d="m9 12 2.2 2.2L15.5 10" {...p} />
              </>
            );
          case 'globe':
            return (
              <>
                <Circle cx={12} cy={12} r={9} {...p} />
                <Path d="M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3Z" {...p} />
              </>
            );
          case 'edit':
            return <Path d="M4 20h4L19 9a2.1 2.1 0 0 0-4-4L4 16v4ZM13.5 6.5l4 4" {...p} />;
          case 'flame':
            return (
              <Path
                d="M12 21c3.9 0 7-2.8 7-6.6 0-2.9-1.7-5-3.3-6.6-.4 1.6-1.3 2.7-2.4 3C13.8 7.4 12.2 4.6 9.5 3c.3 2.9-1 4.8-2.6 6.6C5.7 11 5 12.6 5 14.4 5 18.2 8.1 21 12 21Z"
                {...p}
                fill={fill}
              />
            );
          case 'refresh':
            return (
              <>
                <Path d="M20 11a8 8 0 0 0-14.3-4.6L4 8M4 4v4h4" {...p} />
                <Path d="M4 13a8 8 0 0 0 14.3 4.6L20 16M20 20v-4h-4" {...p} />
              </>
            );
          case 'user':
            return (
              <>
                <Circle cx={12} cy={8} r={4} {...p} />
                <Path d="M4 21c.8-4 4-6 8-6s7.2 2 8 6" {...p} />
              </>
            );
        }
      })()}
    </Svg>
  );
}
