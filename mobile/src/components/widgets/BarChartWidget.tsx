/** `bar_chart` widget — renders any grouped query result the agent chooses to visualise. */
import type { BarChartData } from '@/api/types';
import { BarChart } from '@/components/charts/BarChart';
import { useT } from '@/i18n';
import { WidgetCard } from './WidgetCard';

export function BarChartWidget({ data }: { data: BarChartData }) {
  const { month } = useT();
  const fmt = (l: string) => (/^\d{4}-\d{2}$/.test(l) ? month(l) : l);
  return (
    <WidgetCard title={data.title} emoji="📊">
      <BarChart bars={data.bars ?? []} unit={data.unit} formatLabel={fmt} />
    </WidgetCard>
  );
}
