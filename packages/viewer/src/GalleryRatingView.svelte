<!-- Teaching Gallery tab: rate each generated teaching strip on TWO axes — sample realism (are the
     generated images realistic lesions? catches bad start/end) and trajectory realism (is the transition
     across the axis sensible?). Both POST to /data/gallery-rating → train two classifiers. Standalone SPA route. -->
<script lang="ts">
  import { onMount } from "svelte";
  import { systemDarkMode } from "./lib/dark_mode_store.js";
  import skinmapLogo from "./assets/atlas.png";

  interface Strip {
    id: string;
    title: string;
    description: string;
    image: string;
    axis: string;
    condition: string;
    modality: string;
    method: string;
    sample_realism: number | null;
    trajectory_realism: number | null;
  }

  let strips: Strip[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);
  let axisF = $state("all");
  let modF = $state("all");
  let methF = $state("all");

  let axes = $derived(["all", ...Array.from(new Set(strips.map((s) => s.axis)))]);
  let mods = $derived(["all", ...Array.from(new Set(strips.map((s) => s.modality)))]);
  let meths = $derived(["all", ...Array.from(new Set(strips.map((s) => s.method)))]);
  let shown = $derived(
    strips.filter((s) => (axisF === "all" || s.axis === axisF) && (modF === "all" || s.modality === modF) && (methF === "all" || s.method === methF)),
  );
  let doneCount = $derived(strips.filter((s) => s.sample_realism != null && s.trajectory_realism != null).length);

  const SCALE = [
    { v: 0, l: "❌", t: "unrealistic / off" },
    { v: 1, l: "👎", t: "poor" },
    { v: 2, l: "😐", t: "ok" },
    { v: 3, l: "👍", t: "good" },
    { v: 4, l: "⭐", t: "excellent" },
  ];

  onMount(async () => {
    try {
      const r = await fetch("/data/gallery-manifest");
      if (!r.ok) throw new Error(`manifest HTTP ${r.status}`);
      strips = await r.json();
    } catch (e: any) {
      error = String(e?.message ?? e);
    }
    loading = false;
  });

  async function rate(strip: Strip, kind: "sample_realism" | "trajectory_realism", v: number) {
    strip[kind] = v;
    strips = strips;
    try {
      await fetch("/data/gallery-rating", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: strip.id, sample_realism: strip.sample_realism, trajectory_realism: strip.trajectory_realism }),
      });
    } catch (e) {
      /* keep local */
    }
  }

  function chips(sel: string, opts: string[], set: (v: string) => void) {
    return { sel, opts, set };
  }
</script>

<div
  class="fixed left-0 right-0 top-0 bottom-0 overflow-y-auto select-none text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800"
  class:dark={$systemDarkMode}
>
  <div class="max-w-5xl mx-auto flex flex-col gap-4 p-6">
    <div class="flex items-center gap-4">
      <a href="/" class="shrink-0"><img src={skinmapLogo} alt="SkinMap logo" class="w-10 h-10 rounded-lg" /></a>
      <div class="flex-1 flex flex-col gap-0.5">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold tracking-wide text-slate-800 dark:text-slate-100">Teaching Gallery</h1>
          <a href="/" class="text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">&larr; Back to Map</a>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400">
          Rate each strip twice — <b>sample realism</b> (are the images realistic? bad start/end = low) and <b>trajectory realism</b> (is the sweep sensible?). Trains two filters.
        </p>
      </div>
      <div class="text-sm tabular-nums text-slate-600 dark:text-slate-300 shrink-0">{doneCount}/{strips.length} done</div>
    </div>

    {#if !loading && !error}
      <div class="flex flex-col gap-1.5">
        {#each [["axis", axes, axisF, (v) => (axisF = v)], ["modality", mods, modF, (v) => (modF = v)], ["method", meths, methF, (v) => (methF = v)]] as [label, opts, sel, set]}
          <div class="flex gap-2 flex-wrap items-center">
            <span class="text-xs text-slate-400 w-16">{label}</span>
            {#each opts as o}
              <button
                class="px-2.5 py-0.5 rounded-full text-xs border transition-colors {sel === o
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                onclick={() => set(o)}>{o}</button
              >
            {/each}
          </div>
        {/each}
      </div>
    {/if}

    {#if loading}
      <div class="text-center p-10 text-slate-500 dark:text-slate-400">Loading gallery…</div>
    {:else if error}
      <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">Failed to load gallery: {error}</div>
    {:else}
      <div class="flex flex-col gap-4">
        {#each shown as s (s.id)}
          <div class="rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-3 flex flex-col gap-2 shadow-sm">
            <div class="flex items-baseline justify-between gap-3">
              <div class="font-medium text-slate-800 dark:text-slate-100">{s.title}</div>
            </div>
            <div class="text-xs text-slate-500 dark:text-slate-400">{s.description}</div>
            <img src={s.image} alt={s.title} loading="lazy" class="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950" />
            <div class="flex flex-col gap-1.5 pt-1">
              {#each [["sample_realism", "sample realism (images)"], ["trajectory_realism", "trajectory realism (transition)"]] as [kind, lab]}
                <div class="flex items-center gap-2">
                  <span class="text-xs text-slate-400 dark:text-slate-500 w-52">{lab}</span>
                  {#each SCALE as sc}
                    <button
                      title={sc.t}
                      class="text-lg leading-none px-2.5 py-1.5 rounded-md border transition-colors {s[kind] === sc.v
                        ? 'bg-blue-600 border-blue-600 scale-110'
                        : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'}"
                      onclick={() => rate(s, kind, sc.v)}>{sc.l}</button
                    >
                  {/each}
                  {#if s[kind] != null}<span class="text-xs text-emerald-600 dark:text-emerald-400 ml-1">✓</span>{/if}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
