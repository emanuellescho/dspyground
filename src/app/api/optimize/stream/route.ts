/* eslint-disable @typescript-eslint/no-explicit-any */
import fssync, { promises as fs } from "fs";
import path from "path";

export const runtime = "nodejs";

function getVersionsDir(): string {
  return path.join(process.cwd(), "data", "versions");
}

function getRunDir(runId: string): string {
  return path.join(getVersionsDir(), runId);
}

function toSSE(data: unknown): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const runId = searchParams.get("runId");
  if (!runId) {
    return new Response(JSON.stringify({ error: "Missing runId" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const runDir = getRunDir(runId);
  const tracePath = path.join(runDir, "trace.jsonl");

  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start: async (controller) => {
      let closed = false;
      const send = (obj: unknown) =>
        controller.enqueue(encoder.encode(toSSE(obj)));

      // initial payload: runId
      send({ type: "hello", runId });

      // send any existing lines
      let offset = 0;
      try {
        const exists = fssync.existsSync(tracePath);
        if (exists) {
          const content = await fs.readFile(tracePath, "utf8");
          offset = Buffer.byteLength(content, "utf8");
          const lines = content.split(/\r?\n/).filter(Boolean);
          for (const line of lines) {
            try {
              send(JSON.parse(line));
            } catch {
              // ignore malformed historic lines
            }
          }
        }
      } catch {}

      // poll for new data
      const interval = setInterval(async () => {
        if (closed) return;
        try {
          const stat = await fs.stat(tracePath).catch(() => null);
          if (!stat) return;
          const size = stat.size;
          if (size > offset) {
            const fd = await fs.open(tracePath, "r");
            try {
              const length = size - offset;
              const buffer = Buffer.alloc(length);
              await fd.read(buffer, 0, length, offset);
              offset = size;
              const chunk = buffer.toString("utf8");
              const lines = chunk.split(/\r?\n/).filter(Boolean);
              for (const line of lines) {
                try {
                  const obj = JSON.parse(line);
                  send(obj);
                  if (
                    obj &&
                    typeof obj === "object" &&
                    (obj as any).type === "final"
                  ) {
                    // allow client to render final marker, then close
                    controller.enqueue(encoder.encode(toSSE({ type: "end" })));
                    // mark closed now to avoid races with abort listener
                    closed = true;
                    // keep stream open a tick to flush, then close safely
                    setTimeout(() => {
                      try {
                        clearInterval(interval);
                        clearInterval(ping);
                        if ((controller as any).desiredSize !== null) {
                          controller.close();
                        }
                      } catch {}
                    }, 50);
                    return;
                  }
                } catch {
                  // ignore malformed
                }
              }
            } finally {
              await fd.close();
            }
          }
        } catch {
          // ignore transient read errors
        }
      }, 500);

      // keep-alive pings
      const ping = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`: ping\n\n`));
        } catch {}
      }, 15000);

      // close on client abort
      const abort = (req as any).signal as AbortSignal | undefined;
      if (abort) {
        abort.addEventListener("abort", () => {
          clearInterval(interval);
          clearInterval(ping);
          if (!closed) controller.close();
          closed = true;
        });
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
