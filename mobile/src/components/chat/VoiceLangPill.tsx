/**
 * Compact FI / EN / SV pill next to the mic: which language the user is about
 * to *speak*. Defaults to the UI language, one tap cycles, and the choice is
 * remembered (session store), so a Swedish speaker can talk to a Finnish UI.
 */
import { useSession } from '@/store/session';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { nextVoiceLang } from '@/lib/speechLang';
import { toast } from '@/store/ui';
import { makeStyles, useTheme } from '@/theme';

export function useVoiceLang() {
  const { locale } = useT();
  return useSession((s) => s.voiceLang) ?? locale;
}

export function VoiceLangPill({ height = 32 }: { height?: number }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t } = useT();
  const lang = useVoiceLang();
  const label = t('voice.lang', { lang: t(`voice.lang.${lang}` as TKey) });
  return (
    <PressableScale
      scaleTo={0.9}
      onPress={() => {
        const next = nextVoiceLang(lang);
        useSession.getState().setVoiceLang(next);
        toast(t('voice.lang', { lang: t(`voice.lang.${next}` as TKey) }));
      }}
      style={[s.pill, { height, borderRadius: height / 2 }]}
      accessibilityLabel={label}
      accessibilityHint="FI / EN / SV"
      testID="voice-lang-pill"
    >
      <Text variant="micro" weight="800" color={c.text} style={s.label}>
        {lang.toUpperCase()}
      </Text>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  pill: { minWidth: 44, paddingHorizontal: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border },
  label: { letterSpacing: 0.6 },
}));
