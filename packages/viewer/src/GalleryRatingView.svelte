<!-- Teaching Gallery tab: shows each generated teaching strip (a condition swept along one axis)
     with a title + description, and lets you rate its realism. Ratings POST to the atlas backend
     (/data/gallery-rating) and train the realism filter. Standalone SPA route, like CollectionView. -->
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
    mean_faith: number;
    min_ssim: number;
    mean_anchor_cos: number;
    rating: number | null;
  }

  let strips: Strip[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);
  let axisFilter: string = $state("all");

  let axes = $derived(["all", ...Array.from(new Set(strips.map((s) => s.axis)))]);
  let shown = $derived(axisFilter === "all" ? strips : strips.filter((s) => s.axis === axisFilter));
  let ratedCount = $derived(strips.filter((s) => s.rating != null).length);

  const SCALE = [
    { v: 0, l: "❌", t: "unrealistic / off" },
    { v: 1, l: "👎", t: "poor" },
    { v: 2, l: "😐", t: "ok" },
    { v: 3, l: "👍", t: "good" },
    { v: 4, l: "⭐", t: "excellent" },
  ];

  function fmt(x: number) {
    return typeof x === "number" && isFinite(x) ? x.toFixed(2) : "–";
  }

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

  async function rate(strip: Strip, v: number) {
    strip.rating = v;
    strips = strips;
    try {
      await fetch("/data/gallery-rating", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: strip.id, rating: v }),
      });
    } catch (e) {
      /* keep the local rating even if the POST fails */
    }
  }
</script>

<div
  class="fixed left-0 right-0 top-0 bottom-0 overflow-y-auto select-none text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800"
  class:dark={$systemDarkMode}
>
  <div class="max-w-5xl mx-auto flex flex-col gap-5 p-6">
    <div class="flex items-center gap-4">
      <a href="/" class="shrink-0"><img src={skinmapLogo} alt="SkinMap logo" class="w-10 h-10 rounded-lg" /></a>
      <div class="flex-1 flex flex-col gap-0.5">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold tracking-wide text-slate-800 dark:text-slate-100">Teaching Gallery</h1>
          <a href="/" class="text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">&larr; Back to Map</a>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400">
          Each strip shows a condition swept along one attribute (FST / age / gender / origin). Rate how realistic &amp; faithful each is — your ratings train the realism filter.
        </p>
      </div>
      <div class="text-sm tabular-nums text-slate-600 dark:text-slate-300 shrink-0">{ratedCount}/{strips.length} rated</div>
    </div>

    {#if !loading && !error}
      <div class="flex gap-2 flex-wrap">
        {#each axes as ax}
          <button
            class="px-3 py-1 rounded-full text-xs border transition-colors {axisFilter === ax
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'}"
            onclick={() => (axisFilter = ax)}>{ax}</button
          >
        {/each}
      </div>
    {/if}

    {#if loading}
      <div class="text-center p-10 text-slate-500 dark:text-slate-400">Loading gallery…</div>
    {:else if error}
      <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
        Failed to load gallery: {error}
      </div>
    {:else}
      <div class="flex flex-col gap-4">
        {#each shown as s (s.id)}
          <div class="rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-3 flex flex-col gap-2 shadow-sm">
            <div class="flex items-baseline justify-between gap-3">
              <div class="font-medium text-slate-800 dark:text-slate-100">{s.title}</div>
              <div class="text-xs text-slate-400 dark:text-slate-500 shrink-0">
                faith {fmt(s.mean_faith)} · ssim {fmt(s.min_ssim)} · anchor {fmt(s.mean_anchor_cos)}
              </div>
            </div>
            <div class="text-xs text-slate-500 dark:text-slate-400">{s.description}</div>
            <img src={s.image} alt={s.title} loading="lazy" class="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950" />
            <div class="flex items-center gap-2 pt-1">
              <span class="text-xs text-slate-400 dark:text-slate-500 mr-1">realism:</span>
              {#each SCALE as sc}
                <button
                  title={sc.t}
                  class="text-lg leading-none px-2.5 py-1.5 rounded-md border transition-colors {s.rating === sc.v
                    ? 'bg-blue-600 border-blue-600 scale-110'
                    : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'}"
                  onclick={() => rate(s, sc.v)}>{sc.l}</button
                >
              {/each}
              {#if s.rating != null}<span class="text-xs text-emerald-600 dark:text-emerald-400 ml-1">saved</span>{/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
