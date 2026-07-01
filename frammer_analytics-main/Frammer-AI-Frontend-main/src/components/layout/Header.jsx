import { SidebarTrigger } from '@/components/ui/sidebar';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { GlobalFilterPanel } from '@/components/filters/GlobalFilterPanel';

export function Header({ title }) {
  return (
    <header className="sticky top-0 z-10 bg-background">
      <div className="flex h-14 items-center gap-4 px-4">
        <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
        <h1 className="text-lg font-semibold text-foreground">{title}</h1>

        <div className="ml-auto flex items-center gap-3">
          <Button variant="ghost" size="icon" className="relative text-muted-foreground">
            <Bell className="h-4 w-4" />
            <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-primary" />
          </Button>
          <Avatar className="h-8 w-8 cursor-pointer">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs font-medium">JD</AvatarFallback>
          </Avatar>
        </div>
      </div>
      <GlobalFilterPanel />
    </header>
  );
}
