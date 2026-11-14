/**
 * One animated human character (Sisu or Aava), built from the layered master
 * art in art/{sisu,aava}.tsx.
 *
 * Layer stack (back → front), every layer a full-size canvas sharing one viewBox:
 *   floor glow · halo (listening)
 *   figure (breathing / hops) {
 *     head-back (hair-back, rotates with the head)
 *     body + arms (rest pose; the free arm fades out for the gesture)
 *     head-front (ears, face, mouth variants, eyes + moving pupils,
 *                 blink / happy lids, morphing brows, hair-front; Sisu's sweat drop)
 *       └ glasses (own view: Aava pushes them back up when concerned)
 *     gesture arm (celebrate: Sisu thumbs-up, Aava "idea" finger + sparkle)
 *   }
 *   thinking bubble · celebrate sparkles
 *
 * Head tilts / bobs and body moves are Animated.View transforms around pivots
 * in art units (reliable on iOS, Android and web). Inside the SVG only
 * opacity (variant cross-fades), circle cx/cy (pupils) and path d (brows,
 * sweat drop) are animated. Static art is memoized and never re-renders while
 * animating; optional layers mount only while their state is (or just was) active.
 */
import { memo, useMemo, type ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { useAnimatedProps, useAnimatedStyle, type SharedValue } from 'react-native-reanimated';
import Svg, { Circle, Defs, Ellipse, G, Path, RadialGradient, Stop } from 'react-native-svg';

import { AAVA_ART } from './art/aava';
import { SISU_ART } from './art/sisu';
import type { MouthKey, PersonaArt, PupilCircle } from './art/types';
import { HaloRings, Sparkles, ThinkBubble } from './Effects';
import { computeLayout, type CharacterLayout } from './layout';
import { NECK, POSES, TALK_MOUTHS } from './motion';
import { PERSONAS } from './personas';
import { usePose, type Pose } from './pose';
import { useHumanRig, useLingerSet } from './rig';
import type { CharacterState, PersonaComponentProps, PersonaId } from './types';

const AnimatedG = Animated.createAnimatedComponent(G);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);
const AnimatedPath = Animated.createAnimatedComponent(Path);

const ARTS: Record<PersonaId, PersonaArt> = { sisu: SISU_ART, aava: AAVA_ART };

type PoseSV = SharedValue<Pose>;

// ---------------------------------------------------------------------------
// Small animated SVG parts
// ---------------------------------------------------------------------------

/** A full-size SVG canvas for one layer. */
const Canvas = memo(function Canvas({ L, children }: { L: CharacterLayout; children: ReactNode }) {
  return (
    <Svg width={L.canvas.width} height={L.canvas.height} viewBox={L.viewBox} style={styles.fill}>
      {children}
    </Svg>
  );
});

/** Shows one variant group with an animated opacity read from the pose. */
function Variant({
  pose,
  pick,
  children,
}: {
  pose: PoseSV;
  pick: (p: Pose) => number;
  children: ReactNode;
}) {
  const props = useAnimatedProps(() => ({ opacity: pick(pose.value) }));
  return <AnimatedG animatedProps={props}>{children}</AnimatedG>;
}

function MouthVariant({ pose, k, p, art }: { pose: PoseSV; k: MouthKey; p: string; art: PersonaArt }) {
  const props = useAnimatedProps(() => ({ opacity: Math.min(1, pose.value.mouth[k]) }));
  const Comp = art.mouths[k];
  return (
    <AnimatedG animatedProps={props}>
      <Comp p={p} />
    </AnimatedG>
  );
}

function PupilDot({ pose, c }: { pose: PoseSV; c: PupilCircle }) {
  const props = useAnimatedProps(() => ({ cx: c.cx + pose.value.gx, cy: c.cy + pose.value.gy }));
  return <AnimatedCircle animatedProps={props} r={c.r} fill={c.fill} opacity={c.opacity} />;
}

function Pupils({ pose, circles }: { pose: PoseSV; circles: readonly PupilCircle[] }) {
  return (
    <>
      {circles.map((c, i) => (
        <PupilDot key={i} pose={pose} c={c} />
      ))}
    </>
  );
}

function Brows({ pose, art }: { pose: PoseSV; art: PersonaArt }) {
  const left = useAnimatedProps(() => ({ d: pose.value.browL }));
  const right = useAnimatedProps(() => ({ d: pose.value.browR }));
  const { stroke, strokeWidth } = art.brows;
  return (
    <G transform={art.headTransform}>
      <AnimatedPath animatedProps={left} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" />
      <AnimatedPath animatedProps={right} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" />
    </G>
  );
}

/** Sisu's sweat drop at the temple when concerned (slides down, fades). */
function SweatDrop({ pose }: { pose: PoseSV }) {
  const props = useAnimatedProps(() => {
    const p = pose.value.sweat;
    const x = 282;
    const y = 128 + p * 22;
    const s = 1;
    return {
      d: `M${x} ${y - 9 * s} C${x + 5 * s} ${y - 2 * s} ${x + 6.5 * s} ${y + 2 * s} ${x + 6.5 * s} ${y + 4.5 * s} C${x + 6.5 * s} ${y + 8.5 * s} ${x + 3.5 * s} ${y + 11 * s} ${x} ${y + 11 * s} C${x - 3.5 * s} ${y + 11 * s} ${x - 6.5 * s} ${y + 8.5 * s} ${x - 6.5 * s} ${y + 4.5 * s} C${x - 6.5 * s} ${y + 2 * s} ${x - 5 * s} ${y - 2 * s} ${x} ${y - 9 * s} Z`,
      opacity: pose.value.mouth.concerned * Math.sin(Math.PI * Math.min(1, p * 1.25)) * 0.95,
    };
  });
  return <AnimatedPath animatedProps={props} fill="#9AD8FF" stroke="#E8F7FF" strokeWidth={1.4} transform={SISU_ART.headTransform} />;
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------

const pickHalf = (p: Pose) => {
  'worklet';
  return p.lidHalf;
};
const pickClosed = (p: Pose) => {
  'worklet';
  return p.lidClosed;
};
const pickHappy = (p: Pose) => {
  'worklet';
  return p.lidHappy;
};
const pickArmRest = (p: Pose) => {
  'worklet';
  return 1 - Math.min(1, p.gesture * 1.6);
};
const pickSparkle = (p: Pose) => {
  'worklet';
  return p.sparkle;
};

function mouthsFor(state: CharacterState): MouthKey[] {
  const m = POSES[state].mouth;
  return m === 'talk' ? [...TALK_MOUTHS] : [m];
}

const FloorGlow = memo(function FloorGlow({ size, color, id }: { size: number; color: string; id: string }) {
  return (
    <Svg width={size} height={size * 0.36} style={[styles.floor, { top: size * 0.7 }]}>
      <Defs>
        <RadialGradient id={id} cx="0.5" cy="0.5" r="0.5">
          <Stop offset="0" stopColor={color} stopOpacity="0.22" />
          <Stop offset="0.55" stopColor={color} stopOpacity="0.07" />
          <Stop offset="1" stopColor={color} stopOpacity="0" />
        </RadialGradient>
      </Defs>
      <Ellipse cx={size / 2} cy={size * 0.25} rx={size * 0.5} ry={size * 0.13} fill={`url(#${id})`} />
    </Svg>
  );
});

function HumanCharacterImpl({ persona, state, size, uid, label, style, testID }: PersonaComponentProps) {
  const art = ARTS[persona];
  const meta = PERSONAS[persona];
  const rig = useHumanRig(state, persona);
  const pose = usePose(rig, art.brows);
  const L = useMemo(() => computeLayout(persona, size), [persona, size]);
  const k = L.k;
  const linger = rig.profile.blendMs + 180;

  const lift = useMemo(() => {
    const m = /translate\(\s*[-\d.]+[ ,]+([-\d.]+)\s*\)/.exec(art.bodyTransform);
    return m ? parseFloat(m[1]) : 0;
  }, [art.bodyTransform]);

  // Which optional layers are mounted (current state + the one fading out).
  const stateList = useMemo(() => [state], [state]);
  const states = useLingerSet(stateList, linger);
  const mouthKeys = useMemo(() => {
    const set = new Set<MouthKey>();
    states.forEach((s) => mouthsFor(s).forEach((m) => set.add(m)));
    return [...set];
  }, [states]);
  const has = (s: CharacterState) => states.includes(s);

  // --- animated styles ------------------------------------------------------
  const neckOrigin = L.origin(NECK[0], NECK[1]);
  const figureOrigin = L.origin(202, L.crop[1] + L.crop[3]);
  const elbowOrigin = L.origin(348, 440 + lift);

  const figureStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: pose.value.y * k }, { scaleX: pose.value.sx }, { scaleY: pose.value.sy }],
  }));
  const headBackStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: pose.value.bob * k }, { rotate: `${pose.value.tilt}deg` }],
  }));
  const headFrontStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: pose.value.bob * k }, { rotate: `${pose.value.tilt}deg` }],
  }));
  const glassesStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: pose.value.glasses * k }],
  }));
  const gestureStyle = useAnimatedStyle(() => {
    const g = pose.value.gesture;
    const inv = 1 - g;
    return {
      opacity: Math.min(1, g * 1.6),
      transform: [{ translateY: inv * inv * 80 * k }, { rotate: `${pose.value.pump * g - 10 * inv}deg` }],
    };
  });

  const P = (layer: string) => `${uid}-${layer}-`;
  const canvasPos = { left: L.canvas.left, top: L.canvas.top, width: L.canvas.width, height: L.canvas.height };
  const headCenter = L.toBox(persona === 'aava' ? 200 : 205, persona === 'aava' ? 160 : 168);

  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      testID={testID}
      style={[styles.box, { width: size, height: size }, style]}
    >
      <FloorGlow size={size} color={meta.color} id={`${uid}-floor`} />
      {has('listening') ? (
        <HaloRings pose={pose} w={rig.w.listening} color={meta.color} center={headCenter} radius={125 * k} reduced={rig.reduced} />
      ) : null}

      <Animated.View style={[styles.abs, canvasPos, { transformOrigin: figureOrigin }, figureStyle]}>
        {/* head-back */}
        <Animated.View style={[styles.fill, { transformOrigin: neckOrigin }, headBackStyle]}>
          <Canvas L={L}>
            <art.TopDefs p={P('hb')} />
            <art.HairBack p={P('hb')} />
          </Canvas>
        </Animated.View>

        {/* body + rest arms */}
        <View style={styles.fill}>
          <Canvas L={L}>
            <art.TopDefs p={P('bd')} />
            <art.Body p={P('bd')} />
            <art.ArmsRest
              p={P('bd')}
              armRight={
                <Variant pose={pose} pick={pickArmRest}>
                  <art.ArmRightRest p={P('bd')} />
                </Variant>
              }
            />
          </Canvas>
        </View>

        {/* head-front */}
        <Animated.View style={[styles.fill, { transformOrigin: neckOrigin }, headFrontStyle]}>
          <Canvas L={L}>
            <art.TopDefs p={P('hf')} />
            <art.Ears p={P('hf')} />
            <art.Head p={P('hf')} />
            <G transform={art.mouthTransform}>
              {mouthKeys.map((m) => (
                <MouthVariant key={m} pose={pose} k={m} p={P('hf')} art={art} />
              ))}
            </G>
            <art.Eyes
              p={P('hf')}
              pupilLeft={<Pupils pose={pose} circles={art.pupils.left} />}
              pupilRight={<Pupils pose={pose} circles={art.pupils.right} />}
            />
            <G transform={art.headTransform}>
              <Variant pose={pose} pick={pickHalf}>
                <art.lids.half p={P('hf')} />
              </Variant>
              <Variant pose={pose} pick={pickClosed}>
                <art.lids.closed p={P('hf')} />
              </Variant>
              {has('happy') || (persona === 'aava' && has('celebrate')) ? (
                <Variant pose={pose} pick={pickHappy}>
                  <art.lids.happy p={P('hf')} />
                </Variant>
              ) : null}
            </G>
            <Brows pose={pose} art={art} />
            <art.HairFront p={P('hf')} />
            {persona === 'sisu' && has('concerned') ? <SweatDrop pose={pose} /> : null}
          </Canvas>
          <Animated.View style={[styles.fill, glassesStyle]}>
            <Canvas L={L}>
              <art.TopDefs p={P('gl')} />
              <art.Glasses p={P('gl')} />
            </Canvas>
          </Animated.View>
        </Animated.View>

        {/* celebrate gesture arm */}
        {has('celebrate') ? (
          <Animated.View style={[styles.fill, { transformOrigin: elbowOrigin }, gestureStyle]}>
            <Canvas L={L}>
              <art.TopDefs p={P('ge')} />
              <art.ArmsGesture
                p={P('ge')}
                sparkle={
                  art.IdeaSparkle ? (
                    <Variant pose={pose} pick={pickSparkle}>
                      <art.IdeaSparkle p={P('ge')} />
                    </Variant>
                  ) : undefined
                }
              />
            </Canvas>
          </Animated.View>
        ) : null}
      </Animated.View>

      {has('thinking') ? <ThinkBubble pose={pose} w={rig.w.thinking} size={size} color={meta.color} /> : null}
      {has('celebrate') ? (
        <Sparkles pose={pose} w={rig.w.celebrate} center={headCenter} k={k} reduced={rig.reduced} />
      ) : null}
    </View>
  );
}

export const HumanCharacter = memo(HumanCharacterImpl);

const styles = StyleSheet.create({
  box: { overflow: 'hidden', pointerEvents: 'none' },
  abs: { position: 'absolute' },
  fill: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0 },
  floor: { position: 'absolute', left: 0 },
});
