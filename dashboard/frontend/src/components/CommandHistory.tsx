"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface CommandHistoryProps {
  commands: string[];
  maxEntries?: number;
}

export function CommandHistory({ commands, maxEntries = 10 }: CommandHistoryProps) {
  const recentCommands = commands.slice(-maxEntries).reverse();
  
  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Command History
        </CardTitle>
      </CardHeader>
      <CardContent>
        {recentCommands.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No commands yet
          </p>
        ) : (
          <ul className="space-y-1 font-mono text-xs">
            {recentCommands.map((cmd, idx) => (
              <li
                key={idx}
                className="rounded border border-border bg-muted/30 p-1.5"
              >
                <code className="text-muted-foreground">{cmd}</code>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}