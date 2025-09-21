"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */

import { useEffect, useState } from "react";

type Point = {
  iteration: number;
  selected?: number;
  best?: number;
  avg?: number;
};

export function OptimizeLiveChart(props: {
  data: Point[];
  finalBest?: number | null;
}) {
  const { data, finalBest } = props;
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
  } = M;

  const fmt = (value: unknown) =>
    typeof value === "number" ? value.toFixed(3) : String(value ?? "");

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="iteration" />
        <YAxis domain={[0, 1]} />
        <Tooltip
          formatter={fmt as unknown as (...args: unknown[]) => unknown}
        />
        <Line
          type="stepAfter"
          dataKey="best"
          stroke="#16a34a"
          dot={false}
          strokeWidth={2}
          name="best-so-far"
        />
        <Line
          type="monotone"
          dataKey="selected"
          stroke="#2563eb"
          dot
          name="selected"
        />
        <Line
          type="monotone"
          dataKey="avg"
          stroke="#a855f7"
          dot={false}
          name="avg"
          strokeDasharray="4 4"
        />
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
