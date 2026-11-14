/**
 * SETTINGS — language, voice, appearance, coach, demo customer, and a plain-
 * language privacy explainer ("the AI only sees aggregates of your own data").
 * The About block shows whether the live backend and live LLM are connected,
 * which makes demo conditions transparent to judges and testers.
 */
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { ScrollView, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { API_BASE, MOCK } from '@/api/client';
import { useDemoCustomers, useHealth } from '@/api/hooks';
import { Character, PERSONA_LIST } from '@/characters';
import { Background } from '@/components/ui/Background';
import { Button } from '@/components/ui/Button';
import { GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { Segmented } from '@/components/ui/Segmented';
import { Text } from '@/components/ui/Text';
import { LOCALES, LOCALE_NAMES, useT, type TKey } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { useChat } from '@/store/chat';
import { useLearn } from '@/store/learn';
import { useSession, type ThemePref } from '@/store/session';
import { toast, useUi } from '@/store/ui';
import { layout, makeStyles, useTheme } from '@/theme';

export default function SettingsScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { t, locale, date } = useT();
  const insets = useSafeAreaInsets();
  const session = useSession();
  const customers = useDemoCustomers();
  const health = useHealth();
  const demo = useUi((st) => st.demoData);
  const resetLearn = useLearn((st) => st.reset);

  const live = !MOCK && !demo && health.data?.status === 'ok';

  return (
    <View style={s.root} testID="settings-screen">
      <Background />
      <ScrollView contentContainerStyle={[s.content, { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 32 }]} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <PressableScale testID="settings-back" onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} style={s.back} accessibilityLabel={t('common.back')}>
            <Icon name="chevronLeft" size={22} color={c.text} />
          </PressableScale>
          <Text variant="title" weight="800">
            {t('set.title')}
          </Text>
        </View>

        <Section title={t('set.language')} icon="globe">
          <Segmented
            options={LOCALES.map((l) => ({ value: l, label: LOCALE_NAMES[l] }))}
            value={session.locale}
            onChange={session.setLocale}
            testIDPrefix="settings-locale"
          />
        </Section>

        <Section title={t('set.theme')} icon="sparkle">
          <Segmented<ThemePref>
            options={(['dark', 'light', 'system'] as ThemePref[]).map((v) => ({ value: v, label: t(`set.theme.${v}` as TKey) }))}
            value={session.themePref}
            onChange={session.setThemePref}
          />
        </Section>

        <GlassCard style={s.row}>
          <Icon name="speaker" size={20} color={c.accent} />
          <View style={{ flex: 1 }}>
            <Text variant="callout" weight="700">
              {t('set.voice')}
            </Text>
            <Text variant="caption" tone="muted">
              {t('set.voiceSub')}
            </Text>
          </View>
          <Switch value={session.voice} onValueChange={(v) => { haptic.tap(); session.setVoice(v); }} trackColor={{ true: c.primary, false: c.surfaceStrong }} thumbColor="#FFFFFF" />
        </GlassCard>

        <Section title={t('set.coach')} icon="user">
          <View style={{ flexDirection: 'row', gap: 12 }}>
            {PERSONA_LIST.map((p) => {
              const sel = session.persona === p.id;
              return (
                <GlassCard key={p.id} testID={`settings-persona-${p.id}`} tint={sel ? p.color : undefined} onPress={() => { haptic.light(); session.setPersona(p.id); }} style={[s.coach, sel && { borderColor: p.color, borderWidth: 2 }]} accessibilityLabel={p.name}>
                  <Character persona={p.id} state={sel ? 'happy' : 'idle'} size={72} locale={locale} />
                  <Text variant="callout" weight="800" color={sel ? p.color : c.text}>
                    {p.name}
                  </Text>
                  <Text variant="micro" tone="muted">
                    {p.title[locale]}
                  </Text>
                </GlassCard>
              );
            })}
          </View>
        </Section>

        <Section title={t('set.customer')} icon="user">
          <GlassCard style={{ paddingVertical: 6 }}>
            {(customers.data ?? []).map((cu) => {
              const sel = session.customerId === cu.customer_id;
              return (
                <PressableScale
                  key={cu.customer_id}
                  scaleTo={0.98}
                  onPress={() => {
                    if (sel) return;
                    session.setCustomer(cu.customer_id, cu.name);
                    useChat.getState().ensureCustomer(cu.customer_id);
                    haptic.success();
                    toast(`${cu.avatar_emoji} ${cu.name}`, 'good');
                  }}
                  style={s.customer}
                  accessibilityState={{ selected: sel }}
                >
                  <Text variant="title">{cu.avatar_emoji}</Text>
                  <View style={{ flex: 1 }}>
                    <Text variant="callout" weight="700">
                      {cu.name}, {t('onb.age', { age: cu.age })}
                    </Text>
                    <Text variant="caption" tone="muted" numberOfLines={1}>
                      {cu.tagline}
                    </Text>
                  </View>
                  {sel ? <Icon name="check" size={18} color={c.primary} strokeWidth={3} /> : null}
                </PressableScale>
              );
            })}
          </GlassCard>
        </Section>

        <Section title={t('set.privacyTitle')} icon="shield">
          <GlassCard tint={c.accent} style={{ gap: 12 }}>
            {(['set.privacy1', 'set.privacy2', 'set.privacy3', 'set.privacy4'] as TKey[]).map((k) => (
              <View key={k} style={{ flexDirection: 'row', gap: 10 }}>
                <Icon name="check" size={16} color={c.accent} strokeWidth={3} />
                <Text variant="caption" style={{ flex: 1 }}>
                  {t(k)}
                </Text>
              </View>
            ))}
          </GlassCard>
        </Section>

        <Section title={t('set.about')} icon="info">
          <GlassCard style={{ gap: 10 }}>
            <KV k={t('set.api')} v={live ? `${t('set.apiOk')} ✓` : t('set.apiDemo')} color={live ? c.good : c.amber} />
            <KV k={t('set.ai')} v={live && health.data?.llm?.primary ? t('set.aiLive') : t('set.aiFallback')} />
            <KV k={t('set.dataAsOf')} v={date(health.data?.as_of ?? '2026-09-18', true)} />
            <KV k="API" v={API_BASE} />
            <KV k={t('set.version')} v={Constants.expoConfig?.version ?? '1.0.0'} />
            <Text testID="disclaimer" variant="caption" tone="muted">
              {t('set.disclaimer')}
            </Text>
          </GlassCard>
        </Section>

        <Button
          label={t('set.restart')}
          variant="secondary"
          icon="refresh"
          onPress={() => {
            session.resetOnboarding();
            router.replace('/onboarding');
          }}
          full
        />
        <Button
          label={t('set.resetLearn')}
          variant="ghost"
          onPress={() => {
            resetLearn();
            toast(t('goals.saved_ok'));
          }}
          full
        />
      </ScrollView>
    </View>
  );
}

function Section({ title, icon, children }: { title: string; icon: 'globe' | 'sparkle' | 'user' | 'shield' | 'info'; children: React.ReactNode }) {
  const { c } = useTheme();
  return (
    <View style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Icon name={icon} size={16} color={c.textMuted} />
        <Text variant="caption" weight="800" tone="muted">
          {title.toUpperCase()}
        </Text>
      </View>
      {children}
    </View>
  );
}

function KV({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
      <Text variant="caption" tone="muted">
        {k}
      </Text>
      <Text variant="caption" weight="700" color={color} numberOfLines={1} style={{ flexShrink: 1, textAlign: 'right' }}>
        {v}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  root: { flex: 1, backgroundColor: t.c.bgSolid, overflow: 'hidden' },
  content: { paddingHorizontal: layout.gutter, gap: 20, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  coach: { flex: 1, alignItems: 'center', gap: 4 },
  customer: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
}));
