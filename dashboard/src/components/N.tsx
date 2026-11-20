import type { ReactNode } from "react";
import type { Show } from "./ui";

/** A number that opens the accounts behind it. */
export default function N({ ids, title, show, step, children }: { ids: string[]; title: string; show: Show; step?: string; children: ReactNode }) {
  return ids.length ? (
    <button type="button" className="text-brand underline underline-offset-[3px]" onClick={() => show(title, ids, step)}>
      {children}
    </button>
  ) : (
    <>{children}</>
  );
}
