import { cn } from '@/lib/utils';

type ArrowRightProps = {
  size?: 12 | 14 | 16;
  className?: string;
};

export const ArrowRight = ({ size = 14, className }: ArrowRightProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 14 14"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    className={cn(
      'transition-transform group-hover:translate-x-0.5 group-hover/button:translate-x-0.5',
      className,
    )}
  >
    <path
      d="M1 7H13"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M8 2L13 7L8 12"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

type ArrowDiagonalProps = {
  className?: string;
};

export const ArrowDiagonal = ({ className }: ArrowDiagonalProps) => (
  <svg
    width={12}
    height={12}
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    className={cn(
      'transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover/button:translate-x-0.5 group-hover/button:-translate-y-0.5',
      className,
    )}
  >
    <path
      d="M2 2H10V10"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M10 2L2 10"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
