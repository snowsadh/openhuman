'use client';

'use client';

import { AgentCard } from '@/components/agent-card';
import { type Agent, fetchTemplates } from '@/data/agents';
import { motion, useAnimationFrame, useMotionValue } from 'framer-motion';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

const SCROLL_SPEED = 40;

interface AgentCarouselProps {
  /** Base URL to navigate to when a card is clicked. Template ID is appended as ?template= */
  linkTo?: string;
}

export function AgentCarousel({ linkTo }: AgentCarouselProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const xMotion = useMotionValue(0);
  const [isDragging, setIsDragging] = useState(false);
  const [halfWidth, setHalfWidth] = useState(0);
  const [agents, setAgents] = useState<Agent[]>([]);

  useEffect(() => {
    fetchTemplates()
      .then(setAgents)
      .catch(() => {});
  }, []);

  const doubledAgents = [...agents, ...agents];

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    const totalWidth = track.scrollWidth;
    setHalfWidth(totalWidth / 2);
  }, [agents]);

  useAnimationFrame((_time, delta) => {
    if (isDragging || halfWidth === 0) return;

    const currentX = xMotion.get();
    let newX = currentX - (SCROLL_SPEED * delta) / 1000;

    if (Math.abs(newX) >= halfWidth) {
      newX = newX + halfWidth;
    }

    xMotion.set(newX);
  });

  const dragConstraints = halfWidth > 0 ? { left: -halfWidth, right: 0 } : false;

  return (
    <section className="w-full overflow-hidden py-20">
      <div className="mx-auto max-w-5xl px-6">
        <h2 className="text-center text-3xl font-semibold tracking-tight text-foreground">
          Specialized for every role
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-center text-muted-foreground">
          Each specialist focuses on one domain, learning from every conversation your team has.
        </p>
      </div>

      <div ref={containerRef} className="relative mt-12 overflow-hidden">
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-background to-transparent" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-background to-transparent" />

        <motion.div
          ref={trackRef}
          className="flex cursor-grab gap-4 px-8 active:cursor-grabbing"
          style={{ x: xMotion }}
          drag="x"
          dragConstraints={dragConstraints}
          dragElastic={0.1}
          onDragStart={() => setIsDragging(true)}
          onDragEnd={() => setIsDragging(false)}
        >
          {doubledAgents.map((agent, index) => (
            <AgentCard
              key={`${agent.id}-${index}`}
              agent={agent}
              onClick={
                linkTo
                  ? () => {
                      if (isDragging) return;
                      router.push(`${linkTo}?template=${agent.id}`);
                    }
                  : undefined
              }
            />
          ))}
        </motion.div>
      </div>
    </section>
  );
}
