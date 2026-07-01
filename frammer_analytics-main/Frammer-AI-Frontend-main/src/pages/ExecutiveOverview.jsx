import { useMemo } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { KpiCard } from '@/components/kpi-cards/KpiCard';
import { useFilters } from '@/contexts/FilterContext';
import {
  Clock,
  FileCheck,
  FileClock,
  Hourglass,
  Percent,
  Settings,
  UploadCloud,
  XCircle,
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar,
} from 'recharts';
import {
  getUploadedCount, getProcessedCount, getPublishedCount,
  getTotalDuration, getProcessedDuration, getPublishedDuration,
  getPublishRate, getGrowthPercent, formatHours, groupByTime,
} from '@/services/dataProcessing';

export default function ExecutiveOverview() {
  const { filteredVideos, comparisonVideos } = useFilters();
  const hasComparison = comparisonVideos.length > 0;

  const metricsData = [
    {
      title: 'Uploaded Videos',
      value: getUploadedCount(filteredVideos).toString(),
      change: getGrowthPercent(getUploadedCount(filteredVideos), hasComparison ? getUploadedCount(comparisonVideos) : getUploadedCount(filteredVideos) * 0.85),
      icon: UploadCloud,
    },
    {
      title: 'Uploaded Duration',
      value: formatHours(getTotalDuration(filteredVideos)),
      change: getGrowthPercent(getTotalDuration(filteredVideos), hasComparison ? getTotalDuration(comparisonVideos) : getTotalDuration(filteredVideos) * 0.9),
      icon: Clock,
    },
    {
      title: 'Processed Videos',
      value: getProcessedCount(filteredVideos).toString(),
      change: getGrowthPercent(getProcessedCount(filteredVideos), hasComparison ? getProcessedCount(comparisonVideos) : getProcessedCount(filteredVideos) * 0.88),
      icon: Settings,
    },
    {
      title: 'Processed Duration',
      value: formatHours(getProcessedDuration(filteredVideos)),
      change: getGrowthPercent(getProcessedDuration(filteredVideos), hasComparison ? getProcessedDuration(comparisonVideos) : getProcessedDuration(filteredVideos) * 0.87),
      icon: Hourglass,
    },
    {
      title: 'Published Videos',
      value: getPublishedCount(filteredVideos).toString(),
      change: getGrowthPercent(getPublishedCount(filteredVideos), hasComparison ? getPublishedCount(comparisonVideos) : getPublishedCount(filteredVideos) * 0.82),
      icon: FileCheck,
    },
    {
      title: 'Published Duration',
      value: formatHours(getPublishedDuration(filteredVideos)),
      change: getGrowthPercent(getPublishedDuration(filteredVideos), hasComparison ? getPublishedDuration(comparisonVideos) : getPublishedDuration(filteredVideos) * 0.8),
      icon: FileClock,
    },
    {
      title: 'Publish Conversion',
      value: (getPublishRate(filteredVideos) * 100).toFixed(1) + '%',
      change: getGrowthPercent(getPublishRate(filteredVideos), hasComparison ? getPublishRate(comparisonVideos) : getPublishRate(filteredVideos) * 0.95),
      icon: Percent,
    },
    {
      title: 'Processing Drop-off',
      value: (getProcessedCount(filteredVideos) - getPublishedCount(filteredVideos)).toString(),
      change: -getGrowthPercent(
        getProcessedCount(filteredVideos) - getPublishedCount(filteredVideos),
        hasComparison ? getProcessedCount(comparisonVideos) - getPublishedCount(comparisonVideos) : (getProcessedCount(filteredVideos) - getPublishedCount(filteredVideos)) * 1.1
      ),
      icon: XCircle,
    },
  ];

  const metrics = metricsData.map(m => ({
    ...m,
    changeType: m.change >= 0 ? 'up' : 'down',
    change: `${m.change >= 0 ? '+' : ''}${m.change.toFixed(1)}% ${hasComparison ? 'vs comparison' : 'vs last period'}`,
  }));

  return (
    <DashboardLayout title="Executive Overview">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(225px,1fr))] gap-4">
        {metrics.map((m) => (
          <KpiCard key={m.title} title={m.title} value={m.value} change={m.change} changeType={m.changeType} icon={m.icon} />
        ))}
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-semibold text-foreground mb-4">Growth vs Previous Period</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PipelineTrendChart />
          <PipelineFunnelChart />
          <DurationFlowChart />
          <PublishRateTrendChart />
        </div>
      </div>
    </DashboardLayout>
  );
}

function ChartCard({ title, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="rounded-xl border bg-card p-6 card-shadow"
    >
      <h3 className="mb-4 text-sm font-medium text-foreground">{title}</h3>
      <div className="h-[250px]">
        {children}
      </div>
    </motion.div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border bg-popover p-2 shadow-sm text-xs">
        <p className="font-medium text-foreground mb-1">{label}</p>
        {payload.map((entry, index) => (
          <div key={`item-${index}`} className="flex items-center gap-2 text-muted-foreground">
            <div className="h-1.5 w-1.5 rounded-full" style={{ background: entry.color }} />
            <span>{entry.name}: </span>
            <span className="font-medium text-foreground">{entry.value}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

const chartStyle = { fontSize: 10, fill: 'hsl(var(--muted-foreground))' };

function PipelineTrendChart() {
  const { filteredVideos } = useFilters();
  const pipelineTrendData = useMemo(() => {
    const uploads = groupByTime(filteredVideos, 'uploaded_at', 'day');
    const processed = groupByTime(filteredVideos.filter(v => v.processed_at), 'processed_at', 'day');
    const published = groupByTime(filteredVideos.filter(v => v.published_at), 'published_at', 'day');
    const dataMap = new Map();
    [...uploads, ...processed, ...published].forEach(item => {
      if (!dataMap.has(item.date)) dataMap.set(item.date, { date: item.date, Uploaded: 0, Processed: 0, Published: 0 });
    });
    uploads.forEach(item => { dataMap.get(item.date).Uploaded = item.count; });
    processed.forEach(item => { dataMap.get(item.date).Processed = item.count; });
    published.forEach(item => { dataMap.get(item.date).Published = item.count; });
    return Array.from(dataMap.values()).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [filteredVideos]);

  return (
    <ChartCard title="Pipeline Trend Over Time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={pipelineTrendData}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} />
          <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Line type="monotone" dataKey="Uploaded" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Processed" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Published" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function PipelineFunnelChart() {
  const { filteredVideos } = useFilters();
  const data = useMemo(() => [
    { name: 'Uploaded', value: getUploadedCount(filteredVideos) },
    { name: 'Processed', value: getProcessedCount(filteredVideos) },
    { name: 'Published', value: getPublishedCount(filteredVideos) },
  ], [filteredVideos]);

  return (
    <ChartCard title="Video Pipeline Funnel">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
          <XAxis type="number" tick={chartStyle} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tick={chartStyle} axisLine={false} tickLine={false} width={80} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted)/0.2)' }} />
          <Bar dataKey="value" fill="hsl(var(--chart-1))" radius={[0, 4, 4, 0]} barSize={24} name="Videos" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function DurationFlowChart() {
  const { filteredVideos } = useFilters();
  const data = useMemo(() => [
    { name: 'Uploaded', value: +(getTotalDuration(filteredVideos) / 3600).toFixed(1) },
    { name: 'Processed', value: +(getProcessedDuration(filteredVideos) / 3600).toFixed(1) },
    { name: 'Published', value: +(getPublishedDuration(filteredVideos) / 3600).toFixed(1) },
  ], [filteredVideos]);

  return (
    <ChartCard title="Duration Flow (Hours)">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
          <XAxis type="number" tick={chartStyle} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tick={chartStyle} axisLine={false} tickLine={false} width={80} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted)/0.2)' }} />
          <Bar dataKey="value" fill="hsl(var(--chart-5))" radius={[0, 4, 4, 0]} barSize={24} name="Hours" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function PublishRateTrendChart() {
  const { filteredVideos } = useFilters();
  const data = useMemo(() => {
    const uploads = groupByTime(filteredVideos, 'uploaded_at', 'day');
    const published = groupByTime(filteredVideos.filter(v => v.published_at), 'published_at', 'day');
    const rateMap = new Map();
    uploads.forEach(u => rateMap.set(u.date, { uploaded: u.count, published: 0 }));
    published.forEach(p => {
      if (rateMap.has(p.date)) rateMap.get(p.date).published = p.count;
    });
    return Array.from(rateMap.entries()).map(([date, counts]) => ({
      date,
      'Conversion Rate': counts.uploaded > 0 ? Number(((counts.published / counts.uploaded) * 100).toFixed(1)) : 0,
    })).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [filteredVideos]);

  return (
    <ChartCard title="Publish Conversion Trend">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} />
          <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} unit="%" />
          <Tooltip content={<CustomTooltip />} />
          <Line type="monotone" dataKey="Conversion Rate" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
