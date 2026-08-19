import Image from "next/image";
import { cn } from "@/lib/utils";

type FlowerDividerProps = {
  className?: string;
  width?: number;
};

export function FlowerDivider({ className, width = 256 }: FlowerDividerProps) {
  return (
    <Image
      src="/flower-border.png"
      alt=""
      width={width}
      height={Math.round(width / 3.78)}
      className={cn("h-auto", className)}
      unoptimized
    />
  );
}
