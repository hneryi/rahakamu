/** `transaction_list` widget — the evidence behind an answer ("show me those taxi rides"). */
import { View } from 'react-native';

import type { TransactionListData } from '@/api/types';
import { TxRow } from '@/components/home/TxRow';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { WidgetCard } from './WidgetCard';

export function TransactionListWidget({ data }: { data: TransactionListData }) {
  const { t, money } = useT();
  const items = data.items ?? [];
  return (
    <WidgetCard title={data.title} emoji="🧾">
      <View>
        {items.slice(0, 12).map((tx) => (
          <TxRow key={tx.id} tx={tx} compact />
        ))}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text variant="callout" weight="700">
          {t('w.tx.total')}
        </Text>
        <Text variant="callout" weight="800" money>
          {money(data.total)}
        </Text>
      </View>
    </WidgetCard>
  );
}
