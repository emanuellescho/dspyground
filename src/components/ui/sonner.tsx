"use client";

import { useEffect } from "react";
import { Toaster as Sonner, toast } from "sonner";

export { toast };

export function Toaster() {
  // No-op wrapper to keep consistent placement in our UI folder
  useEffect(() => {
    // Ensure component is client-only
  }, []);
  return <Sonner richColors position="top-right" />;
}
