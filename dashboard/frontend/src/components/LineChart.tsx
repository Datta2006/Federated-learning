interface LinePoint {
  x: number;
  y: number | null;
}

interface LineChartProps {
  values: LinePoint[];
  height?: number;
  tone?: string;
  yLabel?: string;
  xLabels?: string[];
}

/**
 * Dependency-free responsive line chart. Written with a viewBox so it scales
 * without measuring the container; null points break the path rather than
 * drawing a misleading interpolation.
 */
export function LineChart({
  values,
  height = 180,
  tone = "#5eead4",
  yLabel,
  xLabels,
}: LineChartProps) {
  const width = 640;
  const pad = { top: 12, right: 10, bottom: 22, left: 44 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const present = values.filter((point) => point.y !== null) as { x: number; y: number }[];

  if (present.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-ink-600 text-[11px] text-mist-500"
        style={{ height }}
      >
        No measured values yet
      </div>
    );
  }

  const xs = values.map((point) => point.x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const ys = present.map((point) => point.y);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const padY = spanY * 0.08;

  const sx = (x: number) => pad.left + ((x - minX) / spanX) * innerW;
  const sy = (y: number) =>
    pad.top + innerH - ((y - (minY - padY)) / (spanY + padY * 2)) * innerH;

  let path = "";
  let drawing = false;
  for (const point of values) {
    if (point.y === null) {
      drawing = false;
      continue;
    }
    const command = drawing ? "L" : "M";
    path += `${command}${sx(point.x).toFixed(1)},${sy(point.y).toFixed(1)} `;
    drawing = true;
  }

  const gridLines = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div className="w-full">
      {yLabel ? <div className="label mb-1">{yLabel}</div> : null}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={yLabel ?? "line chart"}
      >
        {gridLines.map((fraction) => {
          const y = pad.top + innerH * fraction;
          const value = maxY + padY - fraction * (spanY + padY * 2);
          return (
            <g key={fraction}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y}
                y2={y}
                stroke="#243044"
                strokeWidth={1}
              />
              <text x={pad.left - 6} y={y + 3} textAnchor="end" fontSize={9} fill="#64748b">
                {value.toFixed(2)}
              </text>
            </g>
          );
        })}
        <path d={path} fill="none" stroke={tone} strokeWidth={1.8} strokeLinejoin="round" />
        {present.map((point, index) => (
          <circle
            key={index}
            cx={sx(point.x)}
            cy={sy(point.y)}
            r={2.2}
            fill={tone}
          />
        ))}
        {xLabels && xLabels.length > 0
          ? xLabels.map((label, index) => {
              const x =
                xLabels.length === 1
                  ? pad.left + innerW / 2
                  : pad.left + (index / (xLabels.length - 1)) * innerW;
              return (
                <text
                  key={`${label}-${index}`}
                  x={x}
                  y={height - 6}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#64748b"
                >
                  {label}
                </text>
              );
            })
          : null}
      </svg>
    </div>
  );
}
