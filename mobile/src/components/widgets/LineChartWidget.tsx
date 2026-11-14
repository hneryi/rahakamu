/** `line_chart` widget with optional target line (e.g. a goal amount). */
import type { LineChartData } from '@/api/types';
import { LineChart } from '@/components/charts/LineChart';
import { WidgetCard } from './WidgetCard';

export function LineChartWidget({ data }: { data: LineChartData }) {
  return (
    <WidgetCard title={data.title} emoji="📈">
      <LineChart points={data.points ?? []} target={data.target} unit={data.unit} />
    </WidgetCard>
  );
}
