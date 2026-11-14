/**
 * ONBOARDING — two quick steps: pick a demo customer, pick a coach.
 *
 * Step 1 frames the product promise and the privacy principle up front.
 * Step 2 lets users choose *how* they want to be taught (Sisu's tough-love
 * training vs Aava's calm explanations) — personalising pedagogy, not just
 * the colour scheme. Both choices persist (AsyncStorage) and can be changed in
 * Settings. In S-mobiili, step 1 disappears (the customer is the logged-in user).
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, FadeInRight, FadeOutLeft } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useDemoCustomers } from '@/api/hooks';
import type { PersonaId } from '@/api/types';
import { Character, PERSONA_LIST, PERSONAS } from '@/characters';
import { Background } from '@/components/ui/Background';
import { Button } from '@/components/ui/Button';
import { GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { Segmented } from '@/components/ui/Segmented';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { LOCALES, useT, type TKey } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { useChat } from '@/store/chat';
import { useSession } from '@/store/session';
import { layout, makeStyles, useTheme } from '@/theme';

export default function Onboarding() {
  const s = useStyles();
  const { c } = useTheme();
  const { t, locale } = useT();
  const insets = useSafeAreaInsets();
  const session = useSession();
  const customers = useDemoCustomers();
  const [step, setStep] = useState<0 | 1>(0);
  const [customer, setCustomer] = useState<{ id: string; name: string } | null>(session.customerId ? { id: session.customerId, name: session.customerName ?? '' } : null);
  const [persona, setPersona] = useState<PersonaId>(session.persona);

  const finish = () => {
    if (!customer) return;
    haptic.success();
    session.setCustomer(customer.id, customer.name);
    session.setPersona(persona);
    session.completeOnboarding();
    useChat.getState().ensureCustomer(customer.id);
    router.replace('/');
  };

  return (
    <View style={s.root} testID="onboarding-screen">
      <Background />
      <ScrollView contentContainerStyle={[s.content, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 24 }]} showsVerticalScrollIndicator={false}>
        <View style={s.topRow}>
          <View style={s.brand}>
            <View style={s.logo}>
              <Text variant="callout" weight="800" color={c.primaryText}>
                S
              </Text>
            </View>
            <Text variant="callout" weight="800">
              Rahakamu
            </Text>
          </View>
          <View style={{ width: 156 }}>
            <Segmented
              options={LOCALES.map((l) => ({ value: l, label: l.toUpperCase() }))}
              value={locale}
              onChange={(v) => session.setLocale(v)}
              testIDPrefix="onboarding-locale"
            />
          </View>
        </View>

        {step === 0 ? (
          <Animated.View key="s0" entering={FadeIn.duration(300)} exiting={FadeOutLeft.duration(180)} style={s.step}>
            <View style={s.heroChars}>
              <Character persona="sisu" state="happy" size={104} locale={locale} />
              <Character persona="aava" state="idle" size={104} locale={locale} />
            </View>
            <Text variant="hero" align="center">
              {t('onb.welcome')}
            </Text>
            <Text variant="callout" tone="muted" align="center">
              {t('onb.welcomeSub')}
            </Text>
            <View style={s.privacy}>
              <Icon name="shield" size={18} color={c.accent} />
              <Text variant="caption" tone="muted" style={{ flex: 1 }}>
                {t('onb.privacy')}
              </Text>
            </View>

            <View style={{ gap: 4, marginTop: 8 }}>
              <Text variant="title">{t('onb.pickCustomer')}</Text>
              <Text variant="caption" tone="muted">
                {t('onb.pickCustomerSub')}
              </Text>
            </View>
            {customers.isLoading ? (
              <View style={{ gap: 10 }}>
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} height={76} radius={24} />
                ))}
              </View>
            ) : customers.isError ? (
              <ErrorState onRetry={() => customers.refetch()} />
            ) : (
              <View style={{ gap: 10 }}>
                {(customers.data ?? []).map((cu, i) => {
                  const selected = customer?.id === cu.customer_id;
                  return (
                    <Animated.View key={cu.customer_id} entering={FadeInDown.delay(i * 60).springify().damping(18)}>
                      <GlassCard
                        testID={`customer-option-${cu.customer_id}`}
                        onPress={() => setCustomer({ id: cu.customer_id, name: cu.name })}
                        style={[s.customer, selected && { borderColor: c.primary, backgroundColor: `${c.primary}1A` }]}
                        accessibilityLabel={`${cu.name}, ${cu.age}. ${cu.tagline}`}
                      >
                        <View style={s.avatar}>
                          <Text variant="title">{cu.avatar_emoji}</Text>
                        </View>
                        <View style={{ flex: 1, gap: 2 }}>
                          <Text variant="body" weight="700">
                            {cu.name}, {t('onb.age', { age: cu.age })}
                          </Text>
                          <Text variant="caption" tone="muted" numberOfLines={2}>
                            {cu.tagline}
                          </Text>
                        </View>
                        <View style={[s.radio, selected && { borderColor: c.primary, backgroundColor: c.primary }]}>{selected ? <Icon name="check" size={14} color={c.primaryText} strokeWidth={3} /> : null}</View>
                      </GlassCard>
                    </Animated.View>
                  );
                })}
              </View>
            )}
            <Button testID="onboarding-continue" label={t('common.continue')} icon="chevronRight" disabled={!customer} onPress={() => setStep(1)} full />
          </Animated.View>
        ) : (
          <Animated.View key="s1" entering={FadeInRight.springify().damping(18)} style={s.step}>
            <View style={{ gap: 4 }}>
              <Text variant="hero">{t('onb.pickCoach')}</Text>
              <Text variant="callout" tone="muted">
                {t('onb.pickCoachSub')}
              </Text>
            </View>
            <View style={s.coaches}>
              {PERSONA_LIST.map((p) => {
                const selected = persona === p.id;
                return (
                  <GlassCard
                    key={p.id}
                    testID={`persona-option-${p.id}`}
                    tint={selected ? p.color : undefined}
                    onPress={() => {
                      haptic.light();
                      setPersona(p.id);
                    }}
                    style={[s.coach, selected && { borderColor: p.color, borderWidth: 2 }]}
                    accessibilityLabel={`${p.name}, ${p.title[locale]}`}
                  >
                    <Character persona={p.id} state={selected ? 'happy' : 'idle'} size={112} locale={locale} />
                    <Text variant="title" weight="800" color={selected ? p.color : c.text}>
                      {p.name}
                    </Text>
                    <Text variant="micro" weight="800" tone="muted" align="center">
                      {p.title[locale].toUpperCase()}
                    </Text>
                    <Text variant="caption" tone="muted" align="center">
                      {t(`persona.${p.id}.desc` as TKey)}
                    </Text>
                  </GlassCard>
                );
              })}
            </View>
            <GlassCard tint={PERSONAS[persona].color} style={{ gap: 6 }}>
              <Text variant="callout" weight="700">
                {PERSONAS[persona].emoji} “{PERSONAS[persona].tagline[locale]}”
              </Text>
              <Text variant="caption" tone="muted">
                {t(`persona.${persona}.tags` as TKey)}
              </Text>
            </GlassCard>
            <Button testID="onboarding-continue" label={t('onb.start', { name: PERSONAS[persona].name })} color={PERSONAS[persona].color} icon="sparkle" onPress={finish} full />
            <Button label={t('common.back')} variant="ghost" onPress={() => setStep(0)} full />
          </Animated.View>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  root: { flex: 1, backgroundColor: t.c.bgSolid, overflow: 'hidden' },
  content: { paddingHorizontal: layout.gutter, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', gap: 16 },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  logo: { width: 30, height: 30, borderRadius: 10, backgroundColor: t.c.primary, alignItems: 'center', justifyContent: 'center' },
  step: { gap: 16 },
  heroChars: { flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 8 },
  privacy: { flexDirection: 'row', gap: 10, alignItems: 'center', padding: 12, borderRadius: 16, backgroundColor: `${t.c.accent}12`, borderWidth: 1, borderColor: `${t.c.accent}30` },
  customer: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  avatar: { width: 48, height: 48, borderRadius: 16, backgroundColor: t.c.surfaceStrong, alignItems: 'center', justifyContent: 'center' },
  radio: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, borderColor: t.c.border, alignItems: 'center', justifyContent: 'center' },
  coaches: { flexDirection: 'row', gap: 12 },
  coach: { flex: 1, alignItems: 'center', gap: 6, paddingVertical: 18, paddingHorizontal: 10 },
}));
