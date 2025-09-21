"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */

import { useEffect, useState } from "react";

type Point = {
  iteration: number;
  selected?: number;
  best?: number;
  avg?: number;
  prompt?: string;
};

export function OptimizeLiveChart(props: {
  data: Point[];
  finalBest?: number | null;
  onSelectPointAction?: (p: Point) => void;
  selectedIteration?: number | null;
}) {
  const { data, finalBest, onSelectPointAction, selectedIteration } = props;
  const [mod, setMod] = useState<unknown>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const m = await import("recharts");
        if (active) setMod(m);
      } catch {
        // ignore load error
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (!mod) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-500">
        Loading chart…
      </div>
    );
  }

  const M = mod as any;
  const {
    LineChart,
    Line,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    ReferenceDot,
    Label,
  } = M;

  const fmt = (value: unknown) =>
    typeof value === "number" ? value.toFixed(3) : String(value ?? "");

  const ClickDot = (props: any) => {
    const { cx, cy, payload } = props || {};
    if (typeof cx !== "number" || typeof cy !== "number") return null;
    const handleClick = (e: React.MouseEvent<SVGGElement>) => {
      e.stopPropagation();
      if (onSelectPointAction && payload) {
        onSelectPointAction(payload as Point);
      }
    };
    return (
      <g onClick={handleClick} style={{ cursor: "pointer" }}>
        <circle cx={cx} cy={cy} r={3} fill="#16a34a" />
      </g>
    );
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart
        data={data}
        margin={{ top: 12, right: 20, bottom: 36, left: 48 }}
        onClick={(state: unknown) => {
          const s = state as { activePayload?: Array<{ payload?: Point }> };
          const p = s?.activePayload && s.activePayload[0]?.payload;
          if (p && onSelectPointAction) onSelectPointAction(p);
        }}
      >
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="iteration"
          type="number"
          domain={[0, "dataMax"]}
          allowDecimals={false}
          tickMargin={8}
        >
          <Label value="Rollouts" position="bottom" offset={10} />
        </XAxis>
        <YAxis domain={[0, 1]} tickMargin={8}>
          <Label value="Score" angle={-90} position="left" offset={14} />
        </YAxis>
        <Tooltip
          formatter={fmt as unknown as (...args: unknown[]) => unknown}
        />
        <Line
          type="stepAfter"
          dataKey="best"
          stroke="#16a34a"
          dot={<ClickDot />}
          activeDot={{ r: 5 }}
          strokeWidth={2}
          name="best-so-far"
        />
        {typeof selectedIteration === "number"
          ? (() => {
              const sp = data.find((d) => d.iteration === selectedIteration);
              return sp && typeof sp.best === "number" ? (
                <ReferenceDot
                  x={sp.iteration}
                  y={sp.best}
                  r={5}
                  fill="#ef4444"
                  stroke="none"
                />
              ) : null;
            })()
          : null}
        {typeof finalBest === "number" && data.length > 0 ? (
          <ReferenceDot
            x={data[data.length - 1].iteration}
            y={finalBest}
            r={5}
            fill="#ef4444"
            stroke="none"
          />
        ) : null}
      </LineChart>
    </ResponsiveContainer>
  );
}
