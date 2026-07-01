import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useFilters } from '@/contexts/FilterContext';
import { clients, channels, users } from '@/data/mockData';
import { AiSearchBar } from '@/components/ui/AiSearchBar';
import { StatusBadge } from '@/components/ui/StatusBadge';
import {Table,TableBody,TableCell,TableHead,TableHeader,TableRow,} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';

export default function VideoExplorer() {
  const { filteredVideos } = useFilters();

  const videoExplorerData = useMemo(() => {
    return filteredVideos.map(v => ({
      id: v.video_id,
      headline: v.headline,
      client: clients.find(c => c.id === v.client_id)?.name || 'Unknown',
      channel: channels.find(c => c.id === v.channel_id)?.name || 'Unknown',
      uploadedBy: users.find(u => u.id === v.user_id)?.name || 'Unknown',
      duration: `${Math.floor(v.duration / 60)}m ${v.duration % 60}s`,
      status: v.published_flag ? 'Published' : 'Not Published',
      platform: v.published_platform || '—',
    }));
  }, [filteredVideos]);

  const exportCSV = () => {
    const headers = ['Video ID', 'Headline', 'Client', 'Channel', 'Uploaded By', 'Language', 'Output Type', 'Upload Date', 'Duration', 'Status', 'Platform'];
    const csvRows = [
      headers.join(','),
      ...videoExplorerData.map(row => [
        row.id,
        `"${(row.headline || '').replace(/"/g, '""')}"`,
        `"${row.client}"`,
        `"${row.channel}"`,
        `"${row.uploadedBy}"`,
        row.language,
        row.outputType,
        row.uploadDate,
        row.duration,
        row.status,
        row.platform
      ].join(','))
    ];
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'videos.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  return (
    <DashboardLayout title="Video Explorer">
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
          <div className="flex-1 w-full">
            <AiSearchBar />
          </div>
          <Button variant="outline" onClick={exportCSV} className="shrink-0">
            <Download className="mr-2 h-4 w-4" />
            Export CSV
          </Button>
        </div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border bg-card card-shadow overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Video ID</TableHead>
                <TableHead>Headline</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Uploaded By</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Platform</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {videoExplorerData.map((video) => (
                <TableRow key={video.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">{video.id}</TableCell>
                  <TableCell className="font-medium">{video.headline}</TableCell>
                  <TableCell>{video.client}</TableCell>
                  <TableCell>{video.channel}</TableCell>
                  <TableCell>{video.uploadedBy}</TableCell>
                  <TableCell className="font-mono text-xs">{video.duration}</TableCell>
                  <TableCell><StatusBadge status={video.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">{video.platform}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </motion.div>
      </div>
    </DashboardLayout>
  );
}
