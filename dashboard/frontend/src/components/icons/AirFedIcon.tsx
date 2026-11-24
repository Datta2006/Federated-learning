/**
 * AirFed Logo Icon Component
 * Custom icon for AirFed brand identity
 */

import { FC } from 'react';
import { cn } from '@/lib/utils';

interface AirFedIconProps {
  size?: number;
  className?: string;
  variant?: 'primary' | 'secondary' | 'light';
}

export const AirFedIcon: FC<AirFedIconProps> = ({
  size = 24,
  className,
  variant = 'primary',
}) => {
  const colors = {
    primary: 'hsl(var(--airfed-500))',
    secondary: 'hsl(var(--airfed-600))',
    light: 'hsl(var(--airfed-300))',
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={colors[variant]}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn('lucide', className)}
    >
      {/* AirFed stylized A - network/federated theme */}
      <path d="M12 2L4 7l8 5 8-5-8-5Z" />
      <path d="M4 7v12a4 4 0 0 0 4 4h8a4 4 0 0 0 4-4V7" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
};

AirFedIcon.displayName = 'AirFedIcon';