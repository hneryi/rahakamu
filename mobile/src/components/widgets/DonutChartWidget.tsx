/** `donut_chart` widget — share-of-total views (categories, baskets). */
import type { DonutChartData } from '@/api/types';
import { DonutChart } from '@/components/charts/DonutChart';
import { WidgetCard } from './WidgetCard';

export function DonutChartWidget({ data }: { data: DonutChartData }) {
  return (
    <WidgetCard title={data.title} emoji="🍩">
      <DonutChart slices={data.slices ?? []} unit={data.unit} />
    </WidgetCard>
  );
}
