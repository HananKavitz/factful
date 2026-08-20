import { useState } from "react";
import {
  useClearStyleMutation,
  useGetSettingsQuery,
  useSaveStyleMutation,
} from "../features/settings/settingsApi";
import type { DeviceExample, StyleProfile } from "../types";

function SectionList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function DeviceList({ title, items }: { title: string; items: DeviceExample[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-1 space-y-2 text-sm text-slate-700">
        {items.map((item) => (
          <li key={`${item.label}-${item.excerpt}`}>
            <span className="font-medium text-slate-900">{item.label}</span>
            {item.count > 0 && <span className="text-slate-500"> ({item.count})</span>}
            {item.excerpt && (
              <p className="mt-0.5 border-l-2 border-slate-200 pl-2 text-slate-600">
                “{item.excerpt}”
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StylePresentation({ style }: { style: StyleProfile }) {
  const { extraction, metrics } = style;
  const confidence = Math.round(style.source_confidence * 100);
  return (
    <div className="space-y-4 rounded-lg border border-slate-200 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-lg font-semibold text-slate-900">{style.name}</span>
        {extraction.voice && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-sm text-slate-700">
            {extraction.voice}
          </span>
        )}
        {extraction.tone && (
          <span className="rounded-full bg-blush/20 px-2.5 py-0.5 text-sm text-slate-700">
            {extraction.tone}
          </span>
        )}
        <span className="ml-auto text-xs text-slate-400">{confidence}% confidence</span>
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-slate-600">
        <span>{metrics.avg_sentence_words} avg words / sentence</span>
        <span>{metrics.avg_paragraph_sentences} avg sentences / paragraph</span>
        <span>{metrics.numeric_density} numeric density</span>
      </div>
      <div className="space-y-3">
        <SectionList title="Hooks" items={extraction.hook_patterns} />
        <SectionList title="Story beats" items={extraction.story_beats} />
        <SectionList title="Transitions" items={extraction.transitions} />
        <DeviceList title="Rhetorical devices" items={extraction.rhetorical_devices} />
        <DeviceList title="Direct address" items={extraction.direct_address} />
        <DeviceList title="Characterization" items={extraction.characterization} />
        <SectionList title="Opinion hedges" items={extraction.opinion_hedges} />
        <SectionList title="Comparatives" items={extraction.comparatives} />
        <SectionList title="Modals" items={extraction.modals} />
        {extraction.numeric_style && (
          <p className="text-sm text-slate-700">
            <span className="font-medium text-slate-900">Numeric style:</span>{" "}
            {extraction.numeric_style}
          </p>
        )}
        {extraction.cta_style && (
          <p className="text-sm text-slate-700">
            <span className="font-medium text-slate-900">CTA style:</span> {extraction.cta_style}
          </p>
        )}
        {extraction.signoff_style && (
          <p className="text-sm text-slate-700">
            <span className="font-medium text-slate-900">Sign-off style:</span>{" "}
            {extraction.signoff_style}
          </p>
        )}
      </div>
    </div>
  );
}

export function Settings() {
  const { data, isLoading } = useGetSettingsQuery();
  const [saveStyle, { isLoading: saving }] = useSaveStyleMutation();
  const [clearStyle, { isLoading: clearing }] = useClearStyleMutation();
  const [samples, setSamples] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [analyzed, setAnalyzed] = useState<StyleProfile | null>(null);

  const style = analyzed ?? data?.style ?? null;

  const handleAnalyze = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await saveStyle({ samples: samples.trim() }).unwrap();
      setAnalyzed(result.style);
      setSamples("");
    } catch {
      setError("Could not analyze your writing style. Please try again.");
    }
  };

  const handleClear = async () => {
    setError(null);
    try {
      await clearStyle().unwrap();
      setAnalyzed(null);
    } catch {
      setError("Could not remove your writing style. Please try again.");
    }
  };

  if (isLoading) {
    return (
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Settings</h1>
        <p className="mt-2 text-sm text-slate-500">Loading…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-slate-900">Settings</h1>

      <section className="mt-6">
        <h2 className="text-base font-semibold text-slate-800">Your writing style</h2>
        {style ? (
          <div className="mt-3 space-y-3">
            <StylePresentation style={style} />
            <button
              type="button"
              onClick={handleClear}
              disabled={clearing}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {clearing ? "Removing…" : "Remove style"}
            </button>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            No writing style set yet. Analyze one of your past articles below to teach factful your
            voice.
          </p>
        )}
      </section>

      {!style && (
        <section className="mt-8">
          <h2 className="text-base font-semibold text-slate-800">Analyze a new style</h2>
          <form onSubmit={handleAnalyze} className="mt-3 space-y-4">
            <label className="block">
              <span className="text-base font-medium text-slate-700">Sample articles</span>
              <textarea
                value={samples}
                onChange={(event) => setSamples(event.target.value)}
                rows={8}
                placeholder="Paste one or more of your published articles here…"
                className="mt-1 w-full rounded-md border border-slate-300 px-4 py-3 text-base"
                required
              />
            </label>
            {error && <p className="text-base text-red-600">{error}</p>}
            <div className="flex justify-end pt-1">
              <button
                type="submit"
                disabled={saving || !samples.trim()}
                className="rounded-md bg-blush px-5 py-2.5 text-base font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
              >
                {saving ? "Analyzing…" : "Analyze & save"}
              </button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}