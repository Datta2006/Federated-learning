"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface SliderProps {
  value?: number[];
  onValueChange?: (value: number[]) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}

const Slider = React.forwardRef<HTMLDivElement, SliderProps>(
  ({ className, value = [0], onValueChange, min = 0, max = 100, step = 1, disabled }, ref) => {
    const [currentValue, setCurrentValue] = React.useState<number[]>([
      value[0] ?? min ?? 0,
    ]);
    
    const handleSlide = (clientX: number) => {
      const slider = (ref as React.RefObject<HTMLDivElement>)?.current;
      if (!slider) return;
      
      const slideRect = slider.getBoundingClientRect();
      const clickX = clientX - slideRect.left;
      const slidePercent = clickX / slideRect.width;
      const newValue = Math.round(slidePercent * (max - min) / step) * step + min;
      const clampedValue = Math.min(max, Math.max(min, newValue));
      const newValueArray = [clampedValue];
      
      setCurrentValue(newValueArray);
      onValueChange?.(newValueArray);
    };

    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
      handleSlide(e.clientX);
    };

    const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
      const touch = e.touches[0];
      if (touch) {
        handleSlide(touch.clientX);
      }
    };

    return (
      <div
        ref={ref}
        className={cn(
          "relative flex w-full touch-none items-center select-none px-5 py-3 disabled:cursor-not-allowed disabled:opacity-50",
          disabled && "cursor-not-allowed opacity-50",
          className
        )}
      >
        <div className="relative w-full bg-muted rounded-full h-2">
          <div
            className="absolute h-2 bg-primary rounded-full"
            style={{
              left: 0,
              width: `${((currentValue[0] ?? min) - min) / (max - min) * 100}%`,
            }}
          />
        </div>
        <div
          className="absolute h-5 w-5 rounded-full border-2 border-background bg-primary shadow-sm transition-colors cursor-pointer"
          style={{
            left: `${((currentValue[0] ?? min) - min) / (max - min) * 100}%`,
            transform: "translateX(-50%)",
          }}
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
        />
      </div>
    );
  }
);

Slider.displayName = "Slider";

export { Slider };