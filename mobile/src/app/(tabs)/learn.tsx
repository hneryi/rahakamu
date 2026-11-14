/**
 * LEARN — the "Money Gym".
 *
 * Two-minute lessons with a one-question quiz, a daily streak and a completion
 * counter (on-device). Lessons are *recommended from the user's own data*: the
 * spender archetype and basket shares pick what is most relevant (a Latte
 * Leaker gets "Small buys, big sums" first). Each lesson links back to chat:
 * "how does this apply to me?" — theory immediately grounded in real numbers.
 */
import { useMemo, useState } from 'react';
import { View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useLessons, useProfile } from '@/api/hooks';
import type { Lesson } from '@/api/types';
import { Character, PERSONAS, type CharacterState } from '@/characters';
import { Markdown } from '@/components/chat/Markdown';
import { Button } from '@/components/ui/Button';
import { DemoBadge } from '@/components/ui/DemoBadge';
import { Divider, GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Screen } from '@/components/ui/Screen';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { QuizBlock, Takeaway } from '@/components/widgets/LessonWidget';
import { useT } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { useLearn } from '@/store/learn';
import { useSession } from '@/store/session';
import { toast } from '@/store/ui';
import { makeStyles, useTheme } from '@/theme';

/** Rank lessons by relevance to the user's profile (archetype tags, leak share). */
function recommend(lessons: Lesson[], archetype: string | undefined, leakShare: number | undefined, done: Record<string, unknown>): Lesson[] {
  const score = (l: Lesson) => {
    let s = 0;
    if (archetype && l.tags?.includes(archetype)) s += 3;
    if (l.tags?.includes('all')) s += 1;
    if ((leakShare ?? 0) > 0.3 && l.basket === 'leak') s += 2;
    if (done[l.id]) s -= 5;
    return s;
  };
  return [...lessons].sort((a, b) => score(b) - score(a)).slice(0, 3);
}

export default function LearnScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { t } = useT();
  const lessons = useLessons();
  const profile = useProfile();
  const completed = useLearn((st) => st.completed);
  const streak = useLearn((st) => st.currentStreak());
  const [open, setOpen] = useState<Lesson | null>(null);

  const list = useMemo(() => lessons.data ?? [], [lessons.data]);
  const recs = useMemo(() => recommend(list, profile.data?.archetype.key, profile.data?.leak_share, completed), [list, profile.data, completed]);
  const doneCount = list.filter((l) => completed[l.id]).length;

  return (
    <Screen testID="learn-screen" title={t('learn.title')} subtitle={t('learn.sub')} right={<DemoBadge />}>
      <GlassCard tint={c.amber} style={s.stats}>
        <View style={s.stat}>
          <Icon name="flame" size={30} color={c.amber} fill={streak > 0 ? `${c.amber}55` : 'none'} />
          <View>
            <Text variant="title" weight="800" money>
              {streak}
            </Text>
            <Text variant="caption" tone="muted">
              {t('learn.streak')}
            </Text>
          </View>
        </View>
        <View style={s.sep} />
        <View style={[s.stat, { flex: 1.3 }]}>
          <View style={{ flex: 1, gap: 6 }}>
            <Text variant="title" weight="800" money>
              {doneCount}/{list.length || '–'}
            </Text>
            <ProgressBar value={list.length ? doneCount / list.length : 0} color={c.primary} />
            <Text variant="caption" tone="muted">
              {t('learn.completed')}
            </Text>
          </View>
        </View>
      </GlassCard>

      {lessons.isLoading ? (
        <View style={{ gap: 12 }}>
          <Skeleton height={90} radius={24} />
          <Skeleton height={90} radius={24} />
        </View>
      ) : lessons.isError ? (
        <ErrorState onRetry={() => lessons.refetch()} />
      ) : (
        <>
          <View>
            <SectionHeader title={t('learn.recommended')} subtitle={profile.data ? t('learn.because', { archetype: `${profile.data.archetype.emoji} ${profile.data.archetype.name}` }) : undefined} />
            <View style={{ gap: 10 }}>
              {recs.map((l, i) => (
                <Animated.View key={l.id} entering={FadeInDown.delay(i * 60).springify().damping(18)}>
                  <LessonCard lesson={l} done={!!completed[l.id]} featured onPress={() => setOpen(l)} />
                </Animated.View>
              ))}
            </View>
          </View>
          <View>
            <SectionHeader title={t('learn.all')} />
            <View style={{ gap: 10 }}>
              {list.map((l) => (
                <LessonCard key={l.id} lesson={l} done={!!completed[l.id]} onPress={() => setOpen(l)} />
              ))}
            </View>
          </View>
        </>
      )}
      <LessonSheet lesson={open} onClose={() => setOpen(null)} />
    </Screen>
  );
}

function LessonCard({ lesson, done, featured, onPress }: { lesson: Lesson; done: boolean; featured?: boolean; onPress: () => void }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t } = useT();
  const basketColor = lesson.basket ? c.basket[lesson.basket] : c.accent;
  return (
    <GlassCard onPress={onPress} tint={featured ? basketColor : undefined} style={s.lesson} accessibilityLabel={lesson.title}>
      <View style={[s.lessonIcon, { backgroundColor: `${basketColor}22` }]}>
        <Text variant="title">{lesson.emoji}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text variant="callout" weight="700" numberOfLines={2}>
          {lesson.title}
        </Text>
        {lesson.summary ? (
          <Text variant="caption" tone="muted" numberOfLines={2}>
            {lesson.summary}
          </Text>
        ) : null}
        <Text variant="micro" tone="faint">
          {[lesson.minutes ? t('learn.min', { n: lesson.minutes }) : '', lesson.quiz ? t('w.lesson.quiz') : ''].filter(Boolean).join(' · ')}
        </Text>
      </View>
      {done ? (
        <View style={[s.done, { backgroundColor: `${c.good}22` }]}>
          <Icon name="check" size={14} color={c.good} strokeWidth={3} />
        </View>
      ) : (
        <Icon name="chevronRight" size={18} color={c.textFaint} />
      )}
    </GlassCard>
  );
}

function LessonSheet({ lesson, onClose }: { lesson: Lesson | null; onClose: () => void }) {
  const { t, locale } = useT();
  const persona = useSession((st) => st.persona);
  const complete = useLearn((st) => st.completeLesson);
  const [state, setState] = useState<CharacterState>('talking');
  const [answered, setAnswered] = useState<string | null>(null);

  const finish = (ok: boolean) => {
    if (!lesson) return;
    const res = complete(lesson.id, ok ? 1 : 0);
    setAnswered(lesson.id);
    setState(ok ? 'celebrate' : 'concerned');
    if (ok) toast(`${t('learn.done')} ${t('learn.doneSub', { n: res.streak })}`, 'good');
  };

  return (
    <Sheet
      visible={!!lesson}
      onClose={() => {
        setState('talking');
        setAnswered(null);
        onClose();
      }}
      title={lesson ? `${lesson.emoji} ${lesson.title}` : ''}
      footer={
        lesson ? (
          <Button
            label={t('learn.askCoach', { name: PERSONAS[persona].name })}
            variant="secondary"
            icon="sparkle"
            color={PERSONAS[persona].color}
            onPress={() => {
              onClose();
              openChat(t('learn.ask', { title: lesson.title }));
            }}
            full
          />
        ) : null
      }
    >
      {lesson ? (
        <>
          <View style={{ alignItems: 'center' }}>
            <Character persona={persona} state={answered === lesson.id ? state : 'talking'} size={92} locale={locale} haptics />
          </View>
          <Markdown text={lesson.body} />
          {lesson.key_takeaway ? <Takeaway text={lesson.key_takeaway} /> : null}
          {lesson.quiz ? (
            <>
              <Divider />
              <QuizBlock key={lesson.id} quiz={lesson.quiz} onAnswered={finish} />
            </>
          ) : (
            <Button label={t('learn.finish')} icon="check" onPress={() => finish(true)} full />
          )}
        </>
      ) : null}
    </Sheet>
  );
}

const useStyles = makeStyles((t) => ({
  stats: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  stat: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 },
  sep: { width: 1, alignSelf: 'stretch', backgroundColor: t.c.border },
  lesson: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  lessonIcon: { width: 52, height: 52, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  done: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
}));
