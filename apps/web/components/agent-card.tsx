'use client';

import type { Agent } from '@/data/agents';
import { cn } from '@/lib/utils';
import Image from 'next/image';

interface AgentCardProps {
  agent: Agent;
  className?: string;
  onClick?: () => void;
  selected?: boolean;
}

export function AgentCard({ agent, className, onClick, selected }: AgentCardProps) {
  const isInteractive = Boolean(onClick);

  return (
    <div
      className={cn(
        'w-[320px] flex-shrink-0 select-none rounded-xl border p-1.5 sm:w-[360px]',
        isInteractive && 'cursor-pointer transition-shadow hover:shadow-md',
        selected && 'ring-2 ring-primary',
        className,
      )}
      style={{ backgroundColor: `${agent.color}15`, borderColor: `${agent.color}30` }}
      onClick={onClick}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter') onClick(); } : undefined}
      role={isInteractive ? 'button' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-lg">
        {agent.image ? (
          <Image src={agent.image} alt={agent.name} fill className="object-cover" />
        ) : (
          <div
            className="flex h-full w-full items-center justify-center text-xs font-medium"
            style={{ backgroundColor: `${agent.color}20`, color: `${agent.color}60` }}
          >
            {agent.name}
          </div>
        )}
      </div>
      <div className="mt-2">
        <h3 className="text-base font-semibold text-foreground">{agent.name}</h3>
        <p className="mt-1 text-sm leading-snug text-foreground">{agent.description}</p>
      </div>
    </div>
  );
}
