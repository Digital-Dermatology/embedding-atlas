<!-- Gallery: two tabs. TRANSITIONS = generated attribute-sweep strips rated on sample realism
     (bad start/end) + trajectory realism (is the sweep sensible). SAMPLES = diverse single decoded images
     rated on realism only (cleaner per-sample labels). A rater name is REQUIRED before any rating. -->
<script lang="ts">
  import { onMount } from "svelte";
  import { systemDarkMode } from "./lib/dark_mode_store.js";
  import skinmapLogo from "./assets/atlas.png";

  interface Strip {
    id: string; title: string; description: string; image: string;
    axis: string; condition: string; modality: string; method: string;
    sample_realism: number | null; trajectory_realism: number | null;
  }
  interface Sample {
    id: string; image: string; modality: string; condition: string;
    fitzpatrick: number | null; body_region: string; origin: string; realism: number | null;
  }

  let strips: Strip[] = $state([]);
  let samples: Sample[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);
  let tab = $state("samples");
  let rater = $state((typeof localStorage !== "undefined" && localStorage.getItem("gallery_rater")) || "");
  function setRater(v: string) {
    rater = v;
    try { localStorage.setItem("gallery_rater", v); } catch {}
  }
  let canRate = $derived(rater.trim().length > 0);

  // transitions filters
  let axisF = $state("all"), modF = $state("all"), methF = $state("all");
  let axes = $derived(["all", ...Array.from(new Set(strips.map((s) => s.axis)))]);
  let mods = $derived(["all", ...Array.from(new Set(strips.map((s) => s.modality)))]);
  let meths = $derived(["all", ...Array.from(new Set(strips.map((s) => s.method)))]);
  let shownStrips = $derived(
    strips.filter((s) => (axisF === "all" || s.axis === axisF) && (modF === "all" || s.modality === modF) && (methF === "all" || s.method === methF)),
  );
  // samples filters
  let smodF = $state("all"), sfstF = $state("all");
  let smods = $derived(["all", ...Array.from(new Set(samples.map((s) => s.modality)))]);
  const FSTBANDS = ["all", "I-II", "III-IV", "V-VI"];
  function fstBand(v: number | null): string {
    if (v == null) return "?";
    if (v <= 2) return "I-II";
    if (v <= 4) return "III-IV";
    return "V-VI";
  }
  let shownSamples = $derived(
    samples.filter((s) => (smodF === "all" || s.modality === smodF) && (sfstF === "all" || fstBand(s.fitzpatrick) === sfstF)),
  );

  let doneStrips = $derived(strips.filter((s) => s.sample_realism != null && s.trajectory_realism != null).length);
  let doneSamples = $derived(samples.filter((s) => s.realism != null).length);

  const SCALE = [
    { v: 0, l: "❌", t: "unrealistic / off" },
    { v: 1, l: "👎", t: "poor" },
    { v: 2, l: "😐", t: "ok" },
    { v: 3, l: "👍", t: "good" },
    { v: 4, l: "⭐", t: "excellent" },
  ];

  // Load manifests for the CURRENT rater so the shown ratings are only this person's (independent raters).
  async function loadManifests(r: string) {
    const q = r ? `?rater=${encodeURIComponent(r)}` : "";
    try {
      const res = await fetch(`/data/gallery-manifest${q}`);
      if (res.ok) strips = await res.json();
    } catch (e: any) { error = String(e?.message ?? e); }
    try {
      const res = await fetch(`/data/samples-manifest${q}`);
      if (res.ok) samples = await res.json();
    } catch { /* samples optional */ }
  }

  onMount(async () => {
    await loadManifests(rater);
    loading = false;
  });

  async function rateStrip(strip: Strip, kind: "sample_realism" | "trajectory_realism", v: number) {
    if (!canRate) return;
    strip[kind] = v; strips = strips;
    try {
      await fetch("/data/gallery-rating", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: strip.id, sample_realism: strip.sample_realism, trajectory_realism: strip.trajectory_realism, rater }),
      });
    } catch { /* keep local */ }
  }
  async function rateSample(s: Sample, v: number) {
    if (!canRate) return;
    s.realism = v; samples = samples;
    try {
      await fetch("/data/samples-rating", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: s.id, realism: v, rater }),
      });
    } catch { /* keep local */ }
  }
</script>

<div
  class="fixed left-0 right-0 top-0 bottom-0 overflow-y-auto select-none text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800"
  class:dark={$systemDarkMode}
>
  <div class="max-w-5xl mx-auto flex flex-col gap-3 p-6">
    <!-- header -->
    <div class="flex items-center gap-4">
      <a href="/" class="shrink-0"><img src={skinmapLogo} alt="SkinMap logo" class="w-10 h-10 rounded-lg" /></a>
      <div class="flex-1 flex flex-col gap-0.5">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold tracking-wide text-slate-800 dark:text-slate-100">Gallery</h1>
          <a href="/" class="text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">&larr; Back to Map</a>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400">
          Rate generated dermatology imagery. <b>Transitions</b> = attribute sweeps (sample + trajectory realism); <b>Samples</b> = single images (realism). Trains the realism filters.
        </p>
      </div>
    </div>

    <!-- RATER (required) -->
    <div class="flex items-center gap-3 rounded-lg border {canRate ? 'border-slate-300 dark:border-slate-600' : 'border-amber-400 dark:border-amber-600 bg-amber-50 dark:bg-amber-950/30'} px-3 py-2">
      <span class="text-sm font-medium text-slate-700 dark:text-slate-200">Your name</span>
      <input
        value={rater}
        oninput={(e) => setRater(e.currentTarget.value)}
        onchange={() => loadManifests(rater)}
        placeholder="required to rate"
        class="flex-1 max-w-xs px-2.5 py-1 rounded-md text-sm border bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100"
      />
      {#if !canRate}
        <span class="text-xs text-amber-700 dark:text-amber-400">Enter your name to start rating.</span>
      {:else}
        <span class="text-xs text-slate-400 dark:text-slate-500">rating as <b>{rater}</b></span>
      {/if}
    </div>

    <!-- tabs -->
    <div class="flex items-center gap-2 border-b border-slate-300 dark:border-slate-600">
      {#each [["samples", `Samples (${doneSamples}/${samples.length})`], ["transitions", `Transitions (${doneStrips}/${strips.length})`]] as [id, label]}
        <button
          class="px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors {tab === id
            ? 'border-blue-600 text-blue-700 dark:text-blue-400'
            : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
          onclick={() => (tab = id)}>{label}</button>
      {/each}
    </div>

    {#if loading}
      <div class="text-center p-10 text-slate-500 dark:text-slate-400">Loading…</div>
    {:else if error}
      <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">Failed to load: {error}</div>
    {:else if tab === "transitions"}
      <!-- transition filters -->
      <div class="flex flex-col gap-1.5">
        {#each [["axis", axes, axisF, (v) => (axisF = v)], ["modality", mods, modF, (v) => (modF = v)], ["method", meths, methF, (v) => (methF = v)]] as [label, opts, sel, set]}
          <div class="flex gap-2 flex-wrap items-center">
            <span class="text-xs text-slate-400 w-16">{label}</span>
            {#each opts as o}
              <button class="px-2.5 py-0.5 rounded-full text-xs border transition-colors {sel === o ? 'bg-blue-600 text-white border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'}" onclick={() => set(o)}>{o}</button>
            {/each}
          </div>
        {/each}
      </div>
      <div class="flex flex-col gap-4">
        {#each shownStrips as s (s.id)}
          <div class="rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-3 flex flex-col gap-2 shadow-sm">
            <div class="font-medium text-slate-800 dark:text-slate-100">{s.title}</div>
            <div class="text-xs text-slate-500 dark:text-slate-400">{s.description}</div>
            <img src={s.image} alt={s.title} loading="lazy" class="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950" />
            {#if canRate}
              <div class="flex flex-col gap-1.5 pt-1">
                {#each [["sample_realism", "sample realism (images)"], ["trajectory_realism", "trajectory realism (transition)"]] as [kind, lab]}
                  <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400 dark:text-slate-500 w-52">{lab}</span>
                    {#each SCALE as sc}
                      <button title={sc.t}
                        class="text-lg leading-none px-2.5 py-1.5 rounded-md border transition-colors {s[kind] === sc.v ? 'bg-blue-600 border-blue-600 scale-110' : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'}"
                        onclick={() => rateStrip(s, kind, sc.v)}>{sc.l}</button>
                    {/each}
                    {#if s[kind] != null}<span class="text-xs text-emerald-600 dark:text-emerald-400 ml-1">✓</span>{/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {:else}
      <!-- samples filters -->
      <div class="flex flex-col gap-1.5">
        {#each [["modality", smods, smodF, (v) => (smodF = v)], ["fitzpatrick", FSTBANDS, sfstF, (v) => (sfstF = v)]] as [label, opts, sel, set]}
          <div class="flex gap-2 flex-wrap items-center">
            <span class="text-xs text-slate-400 w-16">{label}</span>
            {#each opts as o}
              <button class="px-2.5 py-0.5 rounded-full text-xs border transition-colors {sel === o ? 'bg-blue-600 text-white border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'}" onclick={() => set(o)}>{o}</button>
            {/each}
          </div>
        {/each}
      </div>
      <!-- samples grid -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {#each shownSamples as s (s.id)}
          <div class="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-1.5 flex flex-col gap-1 shadow-sm">
            <img src={s.image} alt={s.condition} loading="lazy" class="w-full aspect-square object-cover rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950" />
            <div class="text-[10px] text-slate-400 dark:text-slate-500 truncate" title="{s.modality} · {s.condition} · FST {s.fitzpatrick ?? '?'} · {s.body_region} · {s.origin}">{s.modality} · {s.condition || "—"}</div>
            {#if canRate}
              <div class="flex items-center justify-between">
                {#each SCALE as sc}
                  <button title={sc.t}
                    class="text-base leading-none px-1 py-0.5 rounded transition-colors {s.realism === sc.v ? 'bg-blue-600 scale-110' : 'hover:bg-slate-100 dark:hover:bg-slate-700'}"
                    onclick={() => rateSample(s, sc.v)}>{sc.l}</button>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
