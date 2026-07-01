import { useState, useMemo } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useFilters } from '@/contexts/FilterContext';
import { groupByTime } from '@/services/dataProcessing';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, CartesianGrid, ErrorBar } from 'recharts';
import { Button } from '@/components/ui/button';
import { ArrowUp, ArrowDown, GitCompare, Calendar } from 'lucide-react';
import {
  format, startOfDay, startOfWeek, startOfMonth, parseISO,
  subMonths, subWeeks, endOfMonth, endOfWeek, isWithinInterval, addDays, differenceInDays
} from 'date-fns';

const COMPARISON_MODES = {
  PREVIOUS_PERIOD: 'Previous Period',
  PREVIOUS_MONTH: 'Previous Month',
  CUSTOM: 'Custom Range',
  MONTH_VS_MONTH: 'Month vs Month',
  WEEK_VS_WEEK: 'Week vs Week',
};

const mergeForComparison = (current, previous) => {
  if (!previous || previous.length === 0) {
    return current.map(item => ({ ...item, current: item.count, previous: null, previousDate: null }));
  }
  return current.map((item, i) => ({
    ...item,
    current: item.count,
    previous: previous[i] ? previous[i].count : null,
    previousDate: previous[i] ? previous[i].date : null,
  }));
};

const getGrowth = (current, previous) => {
  if (!previous || previous.length === 0) return null;
  const currSum = current.reduce((acc, val) => acc + val.count, 0);
  const prevSum = previous.reduce((acc, val) => acc + val.count, 0);
  if (prevSum === 0) return currSum > 0 ? 100 : 0;
  return ((currSum - prevSum) / prevSum) * 100;
};

const sumDurationByTime = (data, dateKey, granularity) => {
  const groups = {};
  data.forEach(item => {
    if (!item[dateKey]) return;
    const date = item[dateKey] instanceof Date ? item[dateKey] : parseISO(item[dateKey]);
    if (isNaN(date.getTime())) return;

    let key;
    if (granularity === 'day') key = format(startOfDay(date), 'yyyy-MM-dd');
    else if (granularity === 'week') key = format(startOfWeek(date), 'yyyy-MM-dd');
    else if (granularity === 'month') key = format(startOfMonth(date), 'yyyy-MM-dd');

    if (!groups[key]) groups[key] = 0;
    groups[key] += (item.duration || 0);
  });

  return Object.entries(groups)
    .map(([date, totalSeconds]) => ({
      date,
      count: Number((totalSeconds / 3600).toFixed(1)) // Convert to hours
    }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
};

export default function UsageTrends() {
  const { filteredVideos, comparisonVideos, allVideos = [] } = useFilters();
  const [granularity, setGranularity] = useState('day');
  const [showComparison, setShowComparison] = useState(true);
  
  // Advanced Comparison State
  const [comparisonMode, setComparisonMode] = useState(COMPARISON_MODES.PREVIOUS_PERIOD);
  const [customRange, setCustomRange] = useState({ start: '', end: '' });
  const [compareMonth, setCompareMonth] = useState({ current: '', target: '' });
  const [compareWeek, setCompareWeek] = useState({ current: '', target: '' });

  // Helper to filter raw videos by date range
  const filterByRange = (videos, start, end) => {
    if (!start || !end) return [];
    const s = new Date(start);
    const e = new Date(end);
    return videos.filter(v => {
      const d = new Date(v.uploaded_at);
      return d >= s && d <= e;
    });
  };

  // Compute active datasets based on mode
  const { currentVideos, activeComparisonVideos } = useMemo(() => {
    let current = filteredVideos;
    let comparison = comparisonVideos;

    if (comparisonMode === COMPARISON_MODES.PREVIOUS_PERIOD) {
      // Default behavior from context
      return { currentVideos: filteredVideos, activeComparisonVideos: comparisonVideos };
    }

    // For other modes, we need to derive data from allVideos (or filteredVideos if strictly subset)
    // Using allVideos allows picking ranges outside the global filter
    const source = allVideos.length > 0 ? allVideos : filteredVideos;

    if (comparisonMode === COMPARISON_MODES.PREVIOUS_MONTH) {
      // Infer current range from filteredVideos extent
      if (filteredVideos.length > 0) {
        const sorted = [...filteredVideos].sort((a, b) => new Date(a.uploaded_at) - new Date(b.uploaded_at));
        const start = new Date(sorted[0].uploaded_at);
        const end = new Date(sorted[sorted.length - 1].uploaded_at);
        const prevStart = subMonths(start, 1);
        const prevEnd = subMonths(end, 1);
        comparison = filterByRange(source, prevStart, prevEnd);
      }
    } else if (comparisonMode === COMPARISON_MODES.CUSTOM) {
      if (customRange.start && customRange.end) {
        comparison = filterByRange(source, customRange.start, customRange.end);
      }
    } else if (comparisonMode === COMPARISON_MODES.MONTH_VS_MONTH) {
      if (compareMonth.current) {
        const start = startOfMonth(new Date(compareMonth.current));
        const end = endOfMonth(new Date(compareMonth.current));
        current = filterByRange(source, start, end);
      }
      if (compareMonth.target) {
        const start = startOfMonth(new Date(compareMonth.target));
        const end = endOfMonth(new Date(compareMonth.target));
        comparison = filterByRange(source, start, end);
      }
    } else if (comparisonMode === COMPARISON_MODES.WEEK_VS_WEEK) {
      if (compareWeek.current) {
        const [y, w] = compareWeek.current.split('-W');
        // Simple week parsing approximation or use library helper if available. 
        // Using native input type="week" gives "2023-W01".
        // For simplicity, we just rely on the input's date value if possible, 
        // but date input type='week' returns string. 
        // Let's assume standard ISO week handling is needed or simple mock:
        // We will assume the user selects a date in that week for simplicity if week input is tricky 
        // but <input type="week"> is supported in modern browsers.
        // To filter by ISO week string is complex without a helper, 
        // so we'll treat the selection as a Date object if using standard date picker, 
        // OR implementing a basic parser:
        const date = new Date(compareWeek.current); // This often defaults to Monday of week
        if (!isNaN(date)) {
           const start = startOfWeek(date, { weekStartsOn: 1 });
           const end = endOfWeek(date, { weekStartsOn: 1 });
           current = filterByRange(source, start, end);
        }
      }
      if (compareWeek.target) {
        const date = new Date(compareWeek.target);
        if (!isNaN(date)) {
           const start = startOfWeek(date, { weekStartsOn: 1 });
           const end = endOfWeek(date, { weekStartsOn: 1 });
           comparison = filterByRange(source, start, end);
        }
      }
    }

    return { currentVideos: current, activeComparisonVideos: comparison };
  }, [comparisonMode, filteredVideos, comparisonVideos, allVideos, customRange, compareMonth, compareWeek]);

  const hasComparisonData = activeComparisonVideos.length > 0;
  const enableComparison = hasComparisonData && showComparison;

  // 1. Uploads
  const uploads = useMemo(() => groupByTime(currentVideos, 'uploaded_at', granularity), [currentVideos, granularity]);
  const compUploads = useMemo(() => hasComparisonData ? groupByTime(activeComparisonVideos, 'uploaded_at', granularity) : [], [activeComparisonVideos, granularity, hasComparisonData]);
  const uploadData = useMemo(() => mergeForComparison(uploads, compUploads), [uploads, compUploads]);

  // 2. Processed
  const processed = useMemo(() => groupByTime(currentVideos.filter(v => v.processed_at), 'processed_at', granularity), [currentVideos, granularity]);
  const compProcessed = useMemo(() => hasComparisonData ? groupByTime(activeComparisonVideos.filter(v => v.processed_at), 'processed_at', granularity) : [], [activeComparisonVideos, granularity, hasComparisonData]);
  const processedData = useMemo(() => mergeForComparison(processed, compProcessed), [processed, compProcessed]);

  // 3. Published
  const published = useMemo(() => groupByTime(currentVideos.filter(v => v.published_at), 'published_at', granularity), [currentVideos, granularity]);
  const compPublished = useMemo(() => hasComparisonData ? groupByTime(activeComparisonVideos.filter(v => v.published_at), 'published_at', granularity) : [], [activeComparisonVideos, granularity, hasComparisonData]);
  const publishedData = useMemo(() => mergeForComparison(published, compPublished), [published, compPublished]);

  // 4. Processing Hours (New)
  const processingHours = useMemo(() => sumDurationByTime(currentVideos.filter(v => v.processed_at), 'processed_at', granularity), [currentVideos, granularity]);
  const compProcessingHours = useMemo(() => hasComparisonData ? sumDurationByTime(activeComparisonVideos.filter(v => v.processed_at), 'processed_at', granularity) : [], [activeComparisonVideos, granularity, hasComparisonData]);
  const processingHoursData = useMemo(() => mergeForComparison(processingHours, compProcessingHours), [processingHours, compProcessingHours]);

  const durationBuckets = useMemo(() => {
    const buckets = [
      { label: '0-1m', min: 0, max: 60 },
      { label: '1-5m', min: 60, max: 300 },
      { label: '5-15m', min: 300, max: 900 },
      { label: '15-30m', min: 900, max: 1800 },
      { label: '30-60m', min: 1800, max: 3600 },
      { label: '60m+', min: 3600, max: Infinity },
    ];
    return buckets.map(b => ({
      label: b.label,
      count: currentVideos.filter(v => v.duration >= b.min && v.duration < b.max).length,
    }));
  }, [currentVideos]);

  const durationStats = useMemo(() => {
    const groups = {};
    currentVideos.forEach(v => {
      const type = v.output_type || 'Unknown';
      if (!groups[type]) groups[type] = [];
      groups[type].push(v.duration);
    });
    return Object.keys(groups).map(type => {
      const vals = groups[type];
      const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      const min = Math.min(...vals);
      const max = Math.max(...vals);
      return {
        type,
        avg: Math.round(avg),
        min,
        max,
        error: [Math.round(avg - min), Math.round(max - avg)]
      };
    }).sort((a, b) => b.avg - a.avg);
  }, [currentVideos]);

  const chartStyle = { fontSize: 10, fill: 'hsl(var(--muted-foreground))' };

  return (
    <DashboardLayout title="Usage & Trends">
      <div className="mb-4 flex gap-2 items-center justify-between">
        <div className="flex items-center gap-2 bg-card p-1 rounded-lg border">
          {['day', 'week', 'month'].map(g => (
            <Button
              key={g}
              size="sm"
              variant={granularity === g ? 'default' : 'ghost'}
              onClick={() => setGranularity(g)}
              className="capitalize h-7 text-xs"
            >
              {g}
            </Button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <select 
              className="h-8 rounded-md border border-input bg-transparent px-3 py-1 text-xs shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={comparisonMode}
              onChange={(e) => setComparisonMode(e.target.value)}
            >
              {Object.values(COMPARISON_MODES).map(mode => (
                <option key={mode} value={mode} className="bg-card text-foreground">{mode}</option>
              ))}
            </select>

            {comparisonMode === COMPARISON_MODES.CUSTOM && (
              <div className="flex items-center gap-2">
                <input type="date" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  value={customRange.start} onChange={e => setCustomRange(p => ({...p, start: e.target.value}))} />
                <span className="text-muted-foreground">-</span>
                <input type="date" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  value={customRange.end} onChange={e => setCustomRange(p => ({...p, end: e.target.value}))} />
              </div>
            )}

            {comparisonMode === COMPARISON_MODES.MONTH_VS_MONTH && (
              <div className="flex items-center gap-2">
                <input type="month" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  value={compareMonth.current} onChange={e => setCompareMonth(p => ({...p, current: e.target.value}))} />
                <span className="text-muted-foreground">vs</span>
                <input type="month" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  value={compareMonth.target} onChange={e => setCompareMonth(p => ({...p, target: e.target.value}))} />
              </div>
            )}

            {comparisonMode === COMPARISON_MODES.WEEK_VS_WEEK && (
              <div className="flex items-center gap-2">
                <input type="date" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  aria-label="Week A"
                  value={compareWeek.current} onChange={e => setCompareWeek(p => ({...p, current: e.target.value}))} />
                <span className="text-muted-foreground">vs</span>
                <input type="date" className="h-8 rounded-md border border-input bg-transparent px-2 text-xs" 
                  aria-label="Week B"
                  value={compareWeek.target} onChange={e => setCompareWeek(p => ({...p, target: e.target.value}))} />
              </div>
            )}
          </div>

          {hasComparisonData && (
            <Button
              variant={showComparison ? 'secondary' : 'outline'}
              size="sm"
              onClick={() => setShowComparison(!showComparison)}
              className="gap-2 h-8"
            >
              <GitCompare className="h-3.5 w-3.5" />
              Compare
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Daily Video Uploads" growth={enableComparison ? getGrowth(uploads, compUploads) : null}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={uploadData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} minTickGap={30} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="current" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              {enableComparison && <Line type="monotone" dataKey="previous" stroke="hsl(var(--muted-foreground))" strokeWidth={2} strokeDasharray="4 4" dot={false} strokeOpacity={0.6} />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Daily Processed Videos" growth={enableComparison ? getGrowth(processed, compProcessed) : null}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={processedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} minTickGap={30} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="current" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              {enableComparison && <Line type="monotone" dataKey="previous" stroke="hsl(var(--muted-foreground))" strokeWidth={2} strokeDasharray="4 4" dot={false} strokeOpacity={0.6} />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Daily Published Videos" growth={enableComparison ? getGrowth(published, compPublished) : null}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={publishedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} minTickGap={30} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="current" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              {enableComparison && <Line type="monotone" dataKey="previous" stroke="hsl(var(--muted-foreground))" strokeWidth={2} strokeDasharray="4 4" dot={false} strokeOpacity={0.6} />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Daily Processing Hours" growth={enableComparison ? getGrowth(processingHours, compProcessingHours) : null}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={processingHoursData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="date" tick={chartStyle} axisLine={false} tickLine={false} dy={10} minTickGap={30} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
              <Tooltip content={<CustomTooltip unit="h" />} />
              <Line type="monotone" dataKey="current" stroke="hsl(var(--chart-4))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              {enableComparison && <Line type="monotone" dataKey="previous" stroke="hsl(var(--muted-foreground))" strokeWidth={2} strokeDasharray="4 4" dot={false} strokeOpacity={0.6} />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Video Duration Histogram">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={durationBuckets}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="label" tick={chartStyle} axisLine={false} tickLine={false} dy={10} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} dx={-10} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" fill="hsl(var(--chart-5))" radius={[4, 4, 0, 0]} name="Videos" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Duration by Output Type (Avg & Range)">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={durationStats} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
              <XAxis type="number" tick={chartStyle} unit="s" axisLine={false} tickLine={false} />
              <YAxis dataKey="type" type="category" tick={chartStyle} width={80} axisLine={false} tickLine={false} />
              <Tooltip cursor={{fill: 'hsl(var(--muted)/0.2)'}} content={<CustomTooltip unit="s" />} />
              <Bar dataKey="avg" fill="hsl(var(--chart-1))" radius={[0, 4, 4, 0]} name="Avg Duration" barSize={24}>
                <ErrorBar dataKey="error" width={4} strokeWidth={2} stroke="hsl(var(--foreground))" direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </DashboardLayout>
  );
}

function ChartCard({ title, children, growth }) {
  return (
    <div className="rounded-xl border bg-card p-6 card-shadow">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
        {growth != null && <GrowthBadge growth={growth} />}
      </div>
      {children}
    </div>
  );
}

function GrowthBadge({ growth }) {
  const isPositive = growth >= 0;
  const Icon = isPositive ? ArrowUp : ArrowDown;
  return (
    <div className={`flex items-center text-xs font-medium px-2 py-1 rounded-full ${
      isPositive ? 'text-green-500 bg-green-500/10' : 'text-red-500 bg-red-500/10'
    }`}>
      <Icon className="mr-1 h-3 w-3" />
      {Math.abs(growth).toFixed(1)}%
    </div>
  );
}

function CustomTooltip({ active, payload, label, unit = '' }) {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border bg-popover p-2 shadow-sm text-xs">
        <div className="font-medium text-foreground mb-1">{label}</div>
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center gap-2 text-muted-foreground">
            <div className="h-1.5 w-1.5 rounded-full" style={{ background: entry.stroke || entry.fill }} />
            <span className="capitalize">{entry.name === 'current' ? 'Current' : entry.name === 'previous' ? 'Previous' : entry.name}:</span>
            <span className="font-medium text-foreground">
              {entry.value} {unit} {entry.name === 'previous' && entry.payload.previousDate ? `(${entry.payload.previousDate})` : ''}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
}
