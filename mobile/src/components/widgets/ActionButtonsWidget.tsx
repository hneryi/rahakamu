/**
 * `action_buttons` widget: the agent proposes, the user disposes.
 * - `prompt`: sends a follow-up question,
 * - `create_goal`: write actions are confirmed by the user, never executed
 *   silently by the model (SPEC §4 tools),
 * - `open_tab`: deep-links into Insights / Goals / Learn.
 */
import { useState } from 'react';
import { View } from 'react-native';
import { router, type Href } from 'expo-router';

import { useCreateGoal } from '@/api/hooks';
import type { ActionButton, ActionButtonsData } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { useT } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { toast } from '@/store/ui';
import { useWidgetHost } from './context';
import { guessKind } from './GoalPlanWidget';

const TABS: Record<string, Href> = { home: '/', insights: '/insights', goals: '/goals', learn: '/learn', settings: '/settings' };

export function ActionButtonsWidget({ data, secondaryOnly = false }: { data: ActionButtonsData; secondaryOnly?: boolean }) {
  const host = useWidgetHost();
  const create = useCreateGoal();
  const { t } = useT();
  const [done, setDone] = useState<Record<number, boolean>>({});

  const run = (b: ActionButton, i: number) => {
    if (b.kind === 'prompt') {
      const text = typeof b.payload === 'string' ? b.payload : (b.payload?.prompt ?? b.payload?.text ?? b.label);
      host.onPrompt(text);
    } else if (b.kind === 'create_goal') {
      const p = b.payload;
      create.mutate(
        { ...p, kind: p.kind ?? guessKind(p.name ?? '') },
        {
          onSuccess: () => {
            setDone((d) => ({ ...d, [i]: true }));
            haptic.success();
            toast(t('w.goalplan.created'), 'good');
            host.onCelebrate();
          },
          onError: (e) => toast(e instanceof Error ? e.message : t('common.error'), 'warn'),
        },
      );
    } else if (b.kind === 'open_tab') {
      const tab = typeof b.payload === 'string' ? b.payload : (b.payload?.tab ?? 'home');
      const href = TABS[tab] ?? TABS.home;
      if (router.canDismiss()) router.dismissAll();
      router.navigate(href);
    }
  };

  return (
    <View style={{ gap: 8 }}>
      {(data.buttons ?? []).map((b, i) => (
        <Button
          key={`${b.label}-${i}`}
          label={done[i] ? t('w.goalplan.created') : b.label}
          variant={i === 0 && !secondaryOnly ? 'primary' : 'secondary'}
          icon={b.kind === 'create_goal' ? (done[i] ? 'check' : 'target') : b.kind === 'open_tab' ? 'chevronRight' : 'sparkle'}
          onPress={() => run(b, i)}
          loading={b.kind === 'create_goal' && create.isPending}
          disabled={!!done[i]}
          full
        />
      ))}
    </View>
  );
}
