import { useState, useMemo } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useFilters } from '@/contexts/FilterContext';
import { channels, dimensions } from '@/data/mockData';
import { getPublishRate } from '@/services/dataProcessing';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Lightbulb } from 'lucide-react';

const dimensionOptions = [
  { value: 'channel_id', label: 'Channel' },
  { value: 'language', label: 'Language' },
  { value: 'input_type', label: 'Input Type' },
  { value: 'output_type', label: 'Output Type' },
  { value: 'team_name', label: 'Team' },
  { value: 'published_platform', label: 'Platform' },
];

function getDimLabel(dimValue, dim) {
  if (dim === 'channel_id') return channels.find(c => c.id === dimValue)?.name || dimValue;
  return dimValue || 'N/A';
}

export default function MultiDimensionalAnalysis() {
  const { filteredVideos } = useFilters();
  const [dim1, setDim1] = useState('channel_id');
  const [dim2, setDim2] = useState('output_type');

  const pivotData = useMemo(() => {
    const map = {};
    const dim2Values = new Set();
    filteredVideos.forEach(v => {
      const k1 = getDimLabel(v[dim1] || 'N/A', dim1);
      const k2 = v[dim2] || 'N/A';
      dim2Values.add(k2);
      if (!map[k1]) map[k1] = {};
      map[k1][k2] = (map[k1][k2] || 0) + 1;
    });
    const d2Arr = Array.from(dim2Values);
    return {
      data: Object.entries(map).map(([name, vals]) => ({ name, ...vals })).sort((a, b) => {
        const sumA = d2Arr.reduce((s, k) => s + (a[k] || 0), 0);
        const sumB = d2Arr.reduce((s, k) => s + (b[k] || 0), 0);
        return sumB - sumA;
      }).slice(0, 12),
      dim2Values: d2Arr,
    };
  }, [filteredVideos, dim1, dim2]);

  const colors = ['hsl(200,70%,50%)', 'hsl(145,63%,49%)', 'hsl(350,60%,25%)', 'hsl(36,100%,50%)', 'hsl(280,60%,50%)'];
  const tickStyle = { fontSize: 10, fill: 'hsl(220,5%,63%)' };
  const tooltipStyle = { background: 'hsl(225,10%,9%)', border: '1px solid hsl(228,8%,18%)', borderRadius: 8, fontSize: 12 };

  const insights = useMemo(() => {
    const result = [];
    const chRates = channels.map(ch => {
      const vids = filteredVideos.filter(v => v.channel_id === ch.id);
      return { name: ch.name, rate: getPublishRate(vids), count: vids.length };
    }).filter(c => c.count > 2).sort((a, b) => b.rate - a.rate);
    if (chRates[0]) result.push(`${chRates[0].name} has the highest publish rate at ${(chRates[0].rate * 100).toFixed(0)}%.`);

    const langCounts = {};
    filteredVideos.forEach(v => { langCounts[v.language] = (langCounts[v.language] || 0) + 1; });
    const topLang = Object.entries(langCounts).sort(([, a], [, b]) => b - a)[0];
    if (topLang) result.push(`${topLang[0]} is the most common language with ${topLang[1]} videos.`);

    const outCounts = {};
    filteredVideos.forEach(v => { outCounts[v.output_type] = (outCounts[v.output_type] || 0) + 1; });
    const topOut = Object.entries(outCounts).sort(([, a], [, b]) => b - a)[0];
    if (topOut) result.push(`"${topOut[0]}" is the most produced output type (${topOut[1]} videos).`);

    result.push('Channels with low publish rates may need editorial review.');
    return result;
  }, [filteredVideos]);

  return (
    <DashboardLayout title="Multi-Dimensional Analysis">
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Dimension 1</label>
          <Select value={dim1} onValueChange={setDim1}>
            <SelectTrigger className="w-40 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {dimensionOptions.map(d => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <span className="text-muted-foreground text-sm pb-1">×</span>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Dimension 2</label>
          <Select value={dim2} onValueChange={setDim2}>
            <SelectTrigger className="w-40 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {dimensionOptions.map(d => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">Stacked Distribution</h3>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={pivotData.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(228,8%,18%)" />
              <XAxis dataKey="name" tick={tickStyle} angle={-15} textAnchor="end" height={60} />
              <YAxis tick={tickStyle} />
              <Tooltip contentStyle={tooltipStyle} />
              {pivotData.dim2Values.map((val, i) => (
                <Bar key={val} dataKey={val} stackId="a" fill={colors[i % colors.length]} name={val} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Lightbulb className="h-4 w-4 text-warning" />
            <h3 className="text-sm font-medium text-foreground">AI Insights</h3>
          </div>
          <div className="space-y-3">
            {insights.map((insight, i) => (
              <p key={i} className="text-xs text-muted-foreground leading-relaxed">
                💡 {insight}
              </p>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-border bg-card p-4 overflow-auto">
        <h3 className="mb-3 text-sm font-medium text-foreground">Pivot Table</h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left p-2 text-muted-foreground">
                {dimensionOptions.find(d => d.value === dim1)?.label}
              </th>
              {pivotData.dim2Values.map(v => (
                <th key={v} className="text-right p-2 text-muted-foreground">{v}</th>
              ))}
              <th className="text-right p-2 text-muted-foreground font-bold">Total</th>
            </tr>
          </thead>
          <tbody>
            {pivotData.data.map(row => {
              const total = pivotData.dim2Values.reduce((s, k) => s + (row[k] || 0), 0);
              return (
                <tr key={row.name} className="border-b border-border/50 hover:bg-secondary/30">
                  <td className="p-2 text-foreground">{row.name}</td>
                  {pivotData.dim2Values.map(v => (
                    <td key={v} className="text-right p-2 text-foreground">{row[v] || 0}</td>
                  ))}
                  <td className="text-right p-2 text-foreground font-medium">{total}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </DashboardLayout>
  );
}
