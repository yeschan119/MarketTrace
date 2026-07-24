"use client";

import { useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  /** Explanation shown on hover/focus. Newlines (\n) render as line breaks. */
  text: string;
  /** Custom trigger. Defaults to a small "?" info marker. */
  children?: ReactNode;
  className?: string;
}

/**
 * Lightweight hover/focus tooltip. The bubble is portaled to <body> and
 * fixed-positioned so it never gets clipped by scroll/overflow ancestors
 * (event list, ranking/macro tables) — a plain absolutely-positioned tooltip
 * would be cut off inside those containers.
 */
export function InfoTip({ text, children, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const show = () => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Clamp the centre so a wide bubble stays on-screen near the edges.
    const x = Math.min(Math.max(r.left + r.width / 2, 160), window.innerWidth - 160);
    setPos({ x, y: r.top });
  };
  const hide = () => setPos(null);

  return (
    <span
      ref={ref}
      className={`inline-flex cursor-help items-center align-middle ${className ?? ""}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      tabIndex={0}
      role="note"
    >
      {children ?? (
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-gray-300 text-[10px] font-semibold leading-none text-gray-400 transition-colors hover:border-indigo-400 hover:text-indigo-500">
          ?
        </span>
      )}
      {pos &&
        createPortal(
          <span
            className="pointer-events-none fixed z-[100] -translate-x-1/2 -translate-y-full whitespace-pre-line rounded-md bg-gray-900 px-3 py-2 text-xs font-normal leading-relaxed text-white shadow-lg"
            style={{ left: pos.x, top: pos.y - 8, maxWidth: 300, width: "max-content" }}
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}
