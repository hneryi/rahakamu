/** `basket_breakdown` widget: the three baskets for a month with explanations and top items. */
import type { BasketBreakdownData } from '@/api/types';
import { BasketMeter } from '@/components/home/BasketMeter';
import { useT } from '@/i18n';
import { WidgetCard } from './WidgetCard';

export function BasketBreakdownWidget({ data }: { data: BasketBreakdownData }) {
  const { t, monthLong } = useT();
  return (
    <WidgetCard title={t('w.basket.title', { month: data.month ? monthLong(data.month) : '' })} emoji="🧺">
      <BasketMeter values={{ fixed: data.fixed, irregular: data.irregular, leak: data.leak }} explanations={data.explanations} top={data.top} initiallyOpen="leak" />
    </WidgetCard>
  );
}
