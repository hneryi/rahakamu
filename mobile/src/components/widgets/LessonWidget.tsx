/**
 * `lesson` widget: a micro-lesson the agent pulls into the conversation at the
 * teachable moment, with an inline quiz. Completing the quiz counts towards the
 * Money Gym streak — learning in chat and in the Learn tab is one progression.
 */
import { useState } from 'react';
import { View } from 'react-native';

import type { LessonData } from '@/api/types';
import { Markdown } from '@/components/chat/Markdown';
import { Divider } from '@/components/ui/GlassCard';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { useLearn } from '@/store/learn';
import { useTheme } from '@/theme';
import { useWidgetHost } from './context';
import { WidgetCard } from './WidgetCard';

export function QuizBlock({ quiz, onAnswered }: { quiz: NonNullable<LessonData['quiz']>; onAnswered?: (correct: boolean) => void }) {
  const { c } = useTheme();
  const { t } = useT();
  const [picked, setPicked] = useState<number | null>(null);
  const correct = picked !== null && picked === quiz.answer_index;
  return (
    <View style={{ gap: 8 }}>
      <Text variant="micro" tone="accent">
        {t('w.lesson.quiz').toUpperCase()}
      </Text>
      <Text variant="callout" weight="700">
        {quiz.question}
      </Text>
      {quiz.options.map((o, i) => {
        const isPicked = picked === i;
        const isAnswer = picked !== null && i === quiz.answer_index;
        const border = isAnswer ? c.good : isPicked ? c.warn : c.border;
        return (
          <PressableScale
            key={i}
            disabled={picked !== null}
            onPress={() => {
              setPicked(i);
              const ok = i === quiz.answer_index;
              if (ok) haptic.success();
              else haptic.warning();
              onAnswered?.(ok);
            }}
            style={{ padding: 12, borderRadius: 14, borderWidth: 1.5, borderColor: border, backgroundColor: isAnswer ? `${c.good}1A` : isPicked ? `${c.warn}14` : c.surface }}
            accessibilityState={{ selected: isPicked }}
          >
            <Text variant="callout" weight={isAnswer ? '700' : '500'}>
              {o}
            </Text>
          </PressableScale>
        );
      })}
      {picked !== null ? (
        <Text variant="callout" weight="700" color={correct ? c.good : c.amber}>
          {correct ? t('w.lesson.correct') : t('w.lesson.wrong')} {quiz.explanation ?? ''}
        </Text>
      ) : null}
    </View>
  );
}

export function Takeaway({ text }: { text: string }) {
  const { c } = useTheme();
  const { t } = useT();
  return (
    <View style={{ gap: 4, padding: 12, borderRadius: 14, backgroundColor: `${c.accent}14`, borderWidth: 1, borderColor: `${c.accent}33` }}>
      <Text variant="micro" weight="800" color={c.accent}>
        {t('w.lesson.takeaway').toUpperCase()}
      </Text>
      <Text variant="callout" weight="600">
        {text}
      </Text>
    </View>
  );
}

export function LessonWidget({ data }: { data: LessonData }) {
  const complete = useLearn((s) => s.completeLesson);
  const host = useWidgetHost();
  return (
    <WidgetCard title={data.title} emoji={data.emoji || '📘'}>
      <Markdown text={data.body ?? ''} size="callout" />
      {data.key_takeaway ? <Takeaway text={data.key_takeaway} /> : null}
      {data.quiz ? (
        <>
          <Divider />
          <QuizBlock
            quiz={data.quiz}
            onAnswered={(ok) => {
              complete(data.id, ok ? 1 : 0);
              if (ok) host.onCelebrate();
            }}
          />
        </>
      ) : null}
    </WidgetCard>
  );
}
