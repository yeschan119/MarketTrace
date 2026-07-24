"use client";

import { Fragment, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import { getGuide, type Chip, type GuideBlock } from "@/lib/guideContent";

const chipTone: Record<Chip["tone"], string> = {
  pos: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-300 bg-amber-50 text-amber-800",
  neg: "border-red-200 bg-red-50 text-red-800",
  acc: "border-indigo-200 bg-indigo-100 text-indigo-700",
  mut: "border-gray-200 bg-gray-100 text-gray-600",
};

// Render inline **bold** spans without pulling in a markdown dependency.
function rich(text: string): ReactNode {
  return text.split("**").map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold text-gray-900">
        {part}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function ChipRow({ label, items }: { label?: string; items: Chip[] }) {
  return (
    <div className="mb-3">
      {label && (
        <p className="mb-1.5 text-sm font-semibold text-gray-700">{label}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {items.map((c, i) => (
          <span
            key={i}
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${chipTone[c.tone]}`}
          >
            {c.text}
          </span>
        ))}
      </div>
    </div>
  );
}

function Block({ block }: { block: GuideBlock }) {
  switch (block.kind) {
    case "p":
      return (
        <p className="mb-3 max-w-[68ch] text-sm leading-relaxed text-gray-600">
          {rich(block.text)}
        </p>
      );
    case "list":
      return (
        <ul className="mb-2 max-w-[68ch] space-y-2">
          {block.items.map((it, i) => (
            <li key={i} className="relative pl-5 text-sm leading-relaxed text-gray-700">
              <span className="absolute left-0 top-2 h-1.5 w-1.5 rounded-full bg-indigo-500" />
              {rich(it)}
            </li>
          ))}
        </ul>
      );
    case "defs":
      return (
        <dl className="max-w-[74ch] divide-y divide-gray-100">
          {block.items.map((d, i) => (
            <div key={i} className="grid gap-1 py-3 sm:grid-cols-[176px_1fr] sm:gap-5">
              <dt className="font-mono text-[13px] font-semibold text-gray-900">
                {d.term}
              </dt>
              <dd className="text-sm leading-relaxed text-gray-600">{rich(d.desc)}</dd>
            </div>
          ))}
        </dl>
      );
    case "chips":
      return <ChipRow label={block.label} items={block.items} />;
    case "note":
      return (
        <div
          className={`my-3 max-w-[70ch] rounded-lg border-l-[3px] px-4 py-3 text-sm leading-relaxed ${
            block.tone === "warn"
              ? "border-amber-400 bg-amber-50 text-amber-900"
              : "border-indigo-400 bg-indigo-50 text-gray-700"
          }`}
        >
          {rich(block.text)}
        </div>
      );
    case "steps":
      return (
        <div className="mb-2">
          {block.title && (
            <p className="mb-2 mt-4 text-[15px] font-semibold text-gray-800">
              {block.title}
            </p>
          )}
          <ol className="max-w-[70ch] space-y-3">
            {block.items.map((it, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed text-gray-700">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-indigo-200 bg-indigo-50 font-mono text-xs font-semibold text-indigo-700">
                  {i + 1}
                </span>
                <span className="pt-0.5">{rich(it)}</span>
              </li>
            ))}
          </ol>
        </div>
      );
  }
}

export default function GuidePage() {
  const { lang } = useI18n();
  const guide = getGuide(lang);

  return (
    <div>
      {/* Hero */}
      <header className="mb-8">
        <p className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-indigo-600">
          {guide.eyebrow}
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
          {guide.title}
        </h1>
        <p className="mt-4 max-w-[60ch] text-base leading-relaxed text-gray-600">
          {rich(guide.lede)}
        </p>
        <div className="mt-6 max-w-[66ch] rounded-r-lg border-l-[3px] border-amber-400 bg-amber-50 px-4 py-3.5 text-sm leading-relaxed text-amber-900">
          {rich(guide.thesis)}
        </div>
      </header>

      <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-12">
        {/* TOC */}
        <nav
          aria-label={guide.tocLabel}
          className="mb-8 hidden lg:sticky lg:top-6 lg:mb-0 lg:block lg:self-start"
        >
          <ul className="space-y-0.5 text-sm">
            {guide.sections.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="block border-l-2 border-gray-200 py-1 pl-3 text-gray-500 transition-colors hover:border-indigo-500 hover:text-gray-900"
                >
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <main className="min-w-0 space-y-2">
          {guide.sections.map((s) => (
            <section key={s.id} id={s.id} className="scroll-mt-6 pt-2">
              {s.band && (
                <p className="mb-1 mt-6 font-mono text-[11px] uppercase tracking-[0.16em] text-indigo-600">
                  {s.band}
                </p>
              )}
              <h2 className="mb-2 text-xl font-bold tracking-tight text-gray-900">
                {s.title}
              </h2>
              {s.role && (
                <p className="mb-4 max-w-[68ch] text-sm leading-relaxed text-gray-600">
                  {rich(s.role)}
                </p>
              )}
              {s.blocks.length > 0 && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  {s.blocks.map((b, i) => (
                    <Block key={i} block={b} />
                  ))}
                </div>
              )}
            </section>
          ))}

          <footer className="mt-10 border-t border-gray-200 pt-6 text-xs leading-relaxed text-gray-400">
            {guide.footer}
          </footer>
        </main>
      </div>
    </div>
  );
}
