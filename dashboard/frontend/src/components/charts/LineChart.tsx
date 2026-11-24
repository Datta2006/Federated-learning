export interface Series {
  name: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
}

export function LineChart({
  series,
  labels,
  height = 180,
  caption,
}: {
  series: Series[];
  labels: string[];
  height?: number;
  caption?: string;
}) {
  const width = 600;
  const padY = 10;
  const all = series.flatMap((item) => item.values).filter((value): value is number => typeof value === "number");
  const count = Math.max(...series.map((item) => item.values.length), 0);

  if (all.length === 0 || count === 0) {
    return (
      <div className="empty" style={{ padding: "28px 12px" }}>
        <div className="empty-title">No plotted values</div>
        <p className="empty-hint">The source reports no numeric series for this view.</p>
      </div>
    );
  }

  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || Math.abs(max) || 1;
  const x = (index: number) => (count === 1 ? width / 2 : (index / (count - 1)) * width);
  const y = (value: number) => height - padY - ((value - min) / span) * (height - padY * 2);

  const pathFor = (values: (number | null)[]) => {
    const parts: string[] = [];
    let open = false;
    values.forEach((value, index) => {
      if (value === null || value === undefined || Number.isNaN(value)) {
        open = false;
        return;
      }
      const command = open ? "L" : "M";
      parts.push(`${command}${x(index).toFixed(2)},${y(value).toFixed(2)}`);
      open = true;
    });
    return parts.join(" ");
  };

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={caption ?? "Line chart"}>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <line
            key={ratio}
            x1={0}
            x2={width}
            y1={padY + ratio * (height - padY * 2)}
            y2={padY + ratio * (height - padY * 2)}
            stroke="var(--line)"
            strokeWidth={1}
          />
        ))}
        {series.map((item) => (
          <path
            key={item.name}
            d={pathFor(item.values)}
            fill="none"
            stroke={item.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={item.dashed ? "5 4" : undefined}
          />
        ))}
      </svg>
      <div className="chart-caption" style={{ marginTop: 4 }}>
        <span>{labels[0] ?? "start"}</span>
        <span>
          min {Number(min.toFixed(2))} · max {Number(max.toFixed(2))}
        </span>
        <span>{labels[labels.length - 1] ?? "end"}</span>
      </div>
    </div>
  );
}

export function ChartLegend({ series }: { series: Series[] }) {
  return (
    <div className="chart-legend">
      {series.map((item) => (
        <span key={item.name} style={{ color: "var(--muted)" }}>
          <span className="legend-swatch" style={{ background: item.color }} />
          {item.name}
        </span>
      ))}
    </div>
  );
}
