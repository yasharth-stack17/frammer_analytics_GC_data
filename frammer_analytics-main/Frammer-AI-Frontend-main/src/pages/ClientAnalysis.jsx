import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useFilters } from '@/contexts/FilterContext';
import { clients, channels, users } from '@/data/mockData';
import { getProcessedCount, getPublishedCount, getPublishRate } from '@/services/dataProcessing';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { AlertTriangle } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function ClientAnalysis() {
  const { filteredVideos } = useFilters();

  const clientData = useMemo(() => clients.map(c => {
    const vids = filteredVideos.filter(v => v.client_id === c.id);
    return {
      name: c.name,
      uploaded: vids.length,
      processed: getProcessedCount(vids),
      published: getPublishedCount(vids),
      hours: +(vids.reduce((s, v) => s + v.duration, 0) / 3600).toFixed(1),
    };
  }).sort((a, b) => b.uploaded - a.uploaded), [filteredVideos]);

  const channelData = useMemo(() => channels.map(ch => {
    const vids = filteredVideos.filter(v => v.channel_id === ch.id);
    return {
      name: ch.name,
      processed: getProcessedCount(vids),
      published: getPublishedCount(vids),
      publishRate: +(getPublishRate(vids) * 100).toFixed(1),
    };
  }).sort((a, b) => b.processed - a.processed), [filteredVideos]);

  const userData = useMemo(() => users.map(u => {
    const vids = filteredVideos.filter(v => v.user_id === u.id);
    return {
      name: u.name,
      uploaded: vids.length,
      processed: getProcessedCount(vids),
      published: getPublishedCount(vids),
    };
  }).sort((a, b) => b.uploaded - a.uploaded).slice(0, 10), [filteredVideos]);

  const topChannels = useMemo(() => {
    return [...channelData].sort((a, b) => b.processed - a.processed).slice(0, 10);
  }, [channelData]);

  const maxProcessed = Math.max(...topChannels.map(c => c.processed), 1);

  const underperformers = channelData.filter(ch => ch.processed > 3 && ch.publishRate < 50);

  const tooltipStyle = { background: 'hsl(225,10%,9%)', border: '1px solid hsl(228,8%,18%)', borderRadius: 8, fontSize: 12 };
  const tickStyle = { fontSize: 10, fill: 'hsl(220,5%,63%)' };

  return (
    <DashboardLayout title="Client / Channel / User Analysis">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">Videos by Client</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={clientData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(228,8%,18%)" />
              <XAxis type="number" tick={tickStyle} />
              <YAxis dataKey="name" type="category" tick={tickStyle} width={120} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="uploaded" fill="hsl(200,70%,50%)" name="Uploaded" radius={[0, 4, 4, 0]} />
              <Bar dataKey="processed" fill="hsl(145,63%,49%)" name="Processed" radius={[0, 4, 4, 0]} />
              <Bar dataKey="published" fill="hsl(350,60%,25%)" name="Published" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">Channels: Processed vs Published</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={channelData.slice(0, 8)}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(228,8%,18%)" />
              <XAxis dataKey="name" tick={tickStyle} angle={-20} textAnchor="end" height={50} />
              <YAxis tick={tickStyle} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="processed" fill="hsl(200,70%,50%)" name="Processed" stackId="a" radius={[0, 0, 0, 0]} />
              <Bar dataKey="published" fill="hsl(145,63%,49%)" name="Published" stackId="b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">Top 10 Users</h3>
          <div className="space-y-2">
            {userData.map((u, i) => (
              <div key={u.name} className="flex items-center gap-3">
                <span className="w-5 text-xs text-muted-foreground text-right">{i + 1}</span>
                <span className="flex-1 text-sm text-foreground truncate">{u.name}</span>
                <div className="w-32 h-2 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${(u.uploaded / (userData[0]?.uploaded || 1)) * 100}%` }} />
                </div>
                <span className="text-xs text-muted-foreground w-8 text-right">{u.uploaded}</span>
              </div>
            ))}
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-lg border border-border bg-card p-4"
        >
          <h3 className="mb-3 text-sm font-medium text-foreground">Top Channels by Usage</h3>
          <div className="overflow-hidden rounded-md border border-border/50">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-8">Channel Name</TableHead>
                  <TableHead className="h-8 text-right">Processed</TableHead>
                  <TableHead className="h-8 text-right">Published</TableHead>
                  <TableHead className="h-8 text-right">Rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topChannels.map((channel) => (
                  <TableRow key={channel.name} className="hover:bg-muted/50">
                    <TableCell className="py-2 font-medium text-xs">{channel.name}</TableCell>
                    <TableCell className="py-2 text-right text-xs">
                      <div className="flex flex-col items-end gap-1">
                        <span>{channel.processed.toLocaleString()}</span>
                        <div className="h-1 w-16 bg-secondary rounded-full overflow-hidden">
                          <div className="h-full bg-primary/50" style={{ width: `${(channel.processed / maxProcessed) * 100}%` }} />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="py-2 text-right text-xs">{channel.published.toLocaleString()}</TableCell>
                    <TableCell className={`py-2 text-right text-xs font-medium ${channel.publishRate > 70 ? 'text-success' : channel.publishRate < 40 ? 'text-warning' : ''}`}>
                      {channel.publishRate}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </motion.div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">⚠️ Underperformance Alerts</h3>
          {underperformers.length === 0 ? (
            <p className="text-sm text-muted-foreground">All channels performing well.</p>
          ) : (
            <div className="space-y-2">
              {underperformers.map(ch => (
                <div key={ch.name} className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
                  <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
                  <div>
                    <p className="text-sm text-foreground">{ch.name}</p>
                    <p className="text-xs text-muted-foreground">{ch.processed} processed, only {ch.published} published ({ch.publishRate}%)</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
