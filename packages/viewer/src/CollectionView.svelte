<script lang="ts">
  import { onDestroy } from "svelte";
  import Spinner from "./lib/Spinner.svelte";
  import { systemDarkMode } from "./lib/dark_mode_store.js";
  import { imageToDataUrl, setImageAssets } from "./lib/image_utils.js";
  import skinmapLogo from "./assets/atlas.png";

  type Stage = "upload" | "analyzing" | "results" | "submitted";

  interface PriorityInfo {
    score: number;
    n_gap_dims: number;
    gaps_hit: string[];
    cell_count: number;
    explanation: string;
  }

  interface NeighborInfo {
    rowId: number;
    distance: number;
    icd_description?: string;
    icd_code?: string;
    image?: string;
    body_region?: string;
  }

  interface SampleResult {
    id: string;
    filename: string;
    predictions?: Record<string, any>;
    neighbors?: NeighborInfo[];
    priority?: PriorityInfo;
    projection?: { x: number; y: number } | null;
    error?: string;
  }

  const MAX_FILES = 64;

  let stage: Stage = $state("upload");
  let files: File[] = $state([]);
  let previews = $state.raw(new Map<string, string>());
  let samples: SampleResult[] = $state([]);
  let selected = $state.raw(new Set<string>());
  let sortBy: "priority" | "filename" = $state("priority");
  let statusText: string = $state("");
  let errorMessage: string | null = $state(null);
  let contributionId: string | null = $state(null);

  // Drag state
  let dragOver: boolean = $state(false);

  function resetPreviews() {
    previews.forEach((url) => URL.revokeObjectURL(url));
    previews = new Map();
  }

  onDestroy(() => {
    resetPreviews();
    setImageAssets(null);
  });

  setImageAssets({ tokenPrefix: "ea://image/", relativePath: "images" });

  function addFiles(newFiles: File[]) {
    const imageFiles = newFiles
      .filter((f) => f.type.startsWith("image/"))
      .slice(0, MAX_FILES - files.length);
    if (imageFiles.length === 0) return;
    const newPreviews = new Map(previews);
    imageFiles.forEach((f) => {
      newPreviews.set(f.name, URL.createObjectURL(f));
    });
    previews = newPreviews;
    files = [...files, ...imageFiles].slice(0, MAX_FILES);
  }

  function onFileChange(event: Event) {
    const target = event.target as HTMLInputElement;
    const selected = target.files ? Array.from(target.files) : [];
    resetPreviews();
    files = [];
    addFiles(selected);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    dragOver = false;
    const dt = event.dataTransfer;
    if (!dt?.files) return;
    addFiles(Array.from(dt.files));
  }

  function onDragOver(event: DragEvent) {
    event.preventDefault();
    dragOver = true;
  }

  function onDragLeave() {
    dragOver = false;
  }

  function removeFile(name: string) {
    files = files.filter((f) => f.name !== name);
    const url = previews.get(name);
    if (url) URL.revokeObjectURL(url);
    const newPreviews = new Map(previews);
    newPreviews.delete(name);
    previews = newPreviews;
  }

  async function analyze() {
    if (files.length === 0) return;
    stage = "analyzing";
    statusText = `Analyzing ${files.length} image${files.length === 1 ? "" : "s"}...`;
    errorMessage = null;

    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      const resp = await fetch("/data/collection-analyze", {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        throw new Error(`Server error (${resp.status})`);
      }
      const payload = await resp.json();
      samples = Array.isArray(payload?.samples) ? payload.samples : [];

      // Auto-select high-priority samples
      const newSelected = new Set<string>();
      for (const s of samples) {
        if (s.priority && s.priority.score > 0.5) {
          newSelected.add(s.id);
        }
      }
      selected = newSelected;

      stage = "results";
      statusText = "";
    } catch (err: any) {
      errorMessage = err?.message ?? "Analysis failed.";
      stage = "upload";
      statusText = "";
    }
  }

  function toggleSelection(id: string) {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    selected = next;
  }

  function selectAllHighPriority() {
    const next = new Set(selected);
    for (const s of samples) {
      if (s.priority && s.priority.score > 0.5) {
        next.add(s.id);
      }
    }
    selected = next;
  }

  let sortedSamples = $derived(
    [...samples].sort((a, b) => {
      if (sortBy === "priority") {
        const pa = a.priority?.score ?? 0;
        const pb = b.priority?.score ?? 0;
        return pb - pa;
      }
      return (a.filename ?? "").localeCompare(b.filename ?? "");
    }),
  );

  let selectedCount = $derived(selected.size);
  let highPriorityCount = $derived(samples.filter((s) => s.priority && s.priority.score > 0.6).length);

  function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = () => reject(new Error("Failed to read file"));
      reader.readAsDataURL(file);
    });
  }

  async function contribute() {
    if (selectedCount === 0) return;
    statusText = "Submitting contribution...";
    errorMessage = null;

    try {
      const selectedSamples = samples.filter((s) => selected.has(s.id));
      const payload = [];
      for (const s of selectedSamples) {
        const file = files.find((f) => f.name === s.filename);
        let imageData: string | null = null;
        if (file) {
          imageData = await fileToDataUrl(file);
        }
        payload.push({
          filename: s.filename,
          predictions: s.predictions,
          priority: s.priority,
          imageData,
        });
      }

      const resp = await fetch("/data/collection-contribute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ samples: payload }),
      });
      if (!resp.ok) {
        throw new Error(`Server error (${resp.status})`);
      }
      const result = await resp.json();
      contributionId = result?.contributionId ?? null;
      stage = "submitted";
      statusText = "";
    } catch (err: any) {
      errorMessage = err?.message ?? "Contribution failed.";
      statusText = "";
    }
  }

  function reset() {
    resetPreviews();
    files = [];
    samples = [];
    selected = new Set();
    errorMessage = null;
    statusText = "";
    contributionId = null;
    stage = "upload";
  }

  function priorityColor(score: number): string {
    if (score > 0.6) return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
    if (score > 0.3) return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
    return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
  }

  function priorityLabel(score: number): string {
    if (score > 0.6) return "High Priority";
    if (score > 0.3) return "Medium";
    return "Low";
  }
</script>

<div class="fixed left-0 right-0 top-0 bottom-0 overflow-y-auto select-none text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800" class:dark={$systemDarkMode}>
  <div class="max-w-4xl mx-auto flex flex-col gap-6 p-6">
    <!-- Header with branding -->
    <div class="flex items-center gap-4">
      <a href="/" class="shrink-0">
        <img src={skinmapLogo} alt="SkinMap logo" class="w-10 h-10 rounded-lg" />
      </a>
      <div class="flex-1 flex flex-col gap-0.5">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold tracking-wide text-slate-800 dark:text-slate-100">Data Collection</h1>
          <a href="/" class="text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">&larr; Back to Atlas</a>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400">
          Upload dermatology images to identify dataset gaps. High-priority images fill underrepresented combinations of skin type, age, and body region.
        </p>
      </div>
    </div>

    {#if errorMessage}
      <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
        {errorMessage}
      </div>
    {/if}

    <!-- UPLOAD STAGE -->
    {#if stage === "upload"}
      <div
        class="rounded-xl border-2 border-dashed transition-colors p-8 flex flex-col items-center gap-4
          {dragOver
            ? 'border-blue-400 bg-blue-50 dark:border-blue-500 dark:bg-blue-950/30'
            : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900'}"
        role="region"
        aria-label="File upload area"
        ondrop={onDrop}
        ondragover={onDragOver}
        ondragleave={onDragLeave}
      >
        <svg class="w-12 h-12 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <div class="text-center">
          <p class="text-base font-medium text-slate-700 dark:text-slate-200">
            Drop images here or click to browse
          </p>
          <p class="text-xs text-slate-400 dark:text-slate-500 mt-1">Up to {MAX_FILES} images per upload</p>
        </div>
        <label class="cursor-pointer rounded-md px-4 py-2 border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors">
          Choose files
          <input
            type="file"
            multiple
            accept="image/*"
            class="hidden"
            onchange={onFileChange}
          />
        </label>
      </div>

      <!-- File preview thumbnails -->
      {#if files.length > 0}
        <div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-4 flex flex-col gap-3">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-slate-700 dark:text-slate-200">
              {files.length} file{files.length === 1 ? "" : "s"} selected
            </span>
            <button
              class="text-xs text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
              onclick={reset}
            >
              Clear all
            </button>
          </div>
          <div class="grid grid-cols-6 sm:grid-cols-8 md:grid-cols-10 gap-2">
            {#each files as file (file.name)}
              <div class="relative group">
                <img
                  src={previews.get(file.name)}
                  alt={file.name}
                  class="w-full aspect-square object-cover rounded border border-slate-200 dark:border-slate-700"
                />
                <button
                  class="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-xs leading-none flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  onclick={() => removeFile(file.name)}
                  title="Remove"
                >&times;</button>
              </div>
            {/each}
          </div>
          <button
            class="self-end rounded-md px-4 py-2 bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
            onclick={analyze}
          >
            Analyze {files.length} image{files.length === 1 ? "" : "s"}
          </button>
        </div>
      {/if}
    {/if}

    <!-- ANALYZING STAGE -->
    {#if stage === "analyzing"}
      <div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-8 flex flex-col items-center gap-4">
        <Spinner status={statusText} />
      </div>
    {/if}

    <!-- RESULTS STAGE -->
    {#if stage === "results"}
      <!-- Summary bar -->
      <div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-4 flex flex-wrap items-center gap-4">
        <div class="flex-1 flex flex-col gap-1">
          <span class="text-sm font-medium text-slate-700 dark:text-slate-200">
            {samples.length} sample{samples.length === 1 ? "" : "s"} analyzed
          </span>
          {#if highPriorityCount > 0}
            <span class="text-xs text-red-600 dark:text-red-400">
              {highPriorityCount} high priority
            </span>
          {/if}
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-slate-400">Sort:</span>
          <button
            class="text-xs px-2 py-1 rounded border transition-colors {sortBy === 'priority' ? 'border-blue-400 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/30 dark:text-blue-300' : 'border-slate-300 dark:border-slate-600 text-slate-500'}"
            onclick={() => (sortBy = "priority")}
          >Priority</button>
          <button
            class="text-xs px-2 py-1 rounded border transition-colors {sortBy === 'filename' ? 'border-blue-400 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/30 dark:text-blue-300' : 'border-slate-300 dark:border-slate-600 text-slate-500'}"
            onclick={() => (sortBy = "filename")}
          >Filename</button>
        </div>
      </div>

      <!-- Actions bar -->
      <div class="flex items-center gap-3">
        <button
          class="text-xs px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          onclick={selectAllHighPriority}
        >Select All High Priority</button>
        <div class="flex-1"></div>
        <button
          class="text-xs px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
          onclick={reset}
        >Start Over</button>
        <button
          class="rounded-md px-4 py-2 bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
          disabled={selectedCount === 0}
          onclick={contribute}
        >
          Contribute Selected ({selectedCount})
        </button>
      </div>

      {#if statusText}
        <div class="flex items-center gap-2 text-sm text-slate-500"><Spinner status={statusText} /></div>
      {/if}

      <!-- Sample cards -->
      <div class="flex flex-col gap-3">
        {#each sortedSamples as sample (sample.id)}
          {#if sample.error}
            <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 p-3 text-sm">
              <span class="font-medium text-red-700 dark:text-red-300">{sample.filename}</span>:
              <span class="text-red-600 dark:text-red-400">{sample.error}</span>
            </div>
          {:else}
            <div
              class="rounded-md border bg-white dark:bg-slate-900 p-4 flex gap-4 transition-colors
                {selected.has(sample.id)
                  ? 'border-blue-400 dark:border-blue-500 ring-1 ring-blue-200 dark:ring-blue-800'
                  : 'border-slate-300 dark:border-slate-600'}"
            >
              <!-- Checkbox + thumbnail -->
              <div class="flex flex-col items-center gap-2 shrink-0">
                <input
                  type="checkbox"
                  checked={selected.has(sample.id)}
                  onchange={() => toggleSelection(sample.id)}
                  class="h-4 w-4 rounded border-slate-300 dark:border-slate-600 accent-blue-600"
                />
                <img
                  src={previews.get(sample.filename)}
                  alt={sample.filename}
                  class="w-20 h-20 object-cover rounded border border-slate-200 dark:border-slate-700"
                />
              </div>

              <!-- Info -->
              <div class="flex-1 flex flex-col gap-2 min-w-0">
                <div class="flex items-start justify-between gap-2">
                  <span class="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{sample.filename}</span>
                  {#if sample.priority}
                    <span class="shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full {priorityColor(sample.priority.score)}">
                      {priorityLabel(sample.priority.score)} ({(sample.priority.score * 100).toFixed(0)}%)
                    </span>
                  {/if}
                </div>

                <!-- Predicted metadata -->
                {#if sample.predictions}
                  <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                    {#if sample.predictions.modality}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">Modality:</span> {sample.predictions.modality}</span>
                    {/if}
                    {#if sample.predictions.icd_description}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">Possible condition:</span> {sample.predictions.icd_description}</span>
                    {:else if sample.predictions.icd_code}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">ICD:</span> {sample.predictions.icd_code}</span>
                    {/if}
                    {#if sample.predictions.body_region}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">Region:</span> {sample.predictions.body_region}</span>
                    {/if}
                    {#if sample.predictions.fitzpatrick}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">FST:</span> {sample.predictions.fitzpatrick}</span>
                    {/if}
                    {#if sample.predictions.age != null}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">Age:</span> {typeof sample.predictions.age === "number" ? Math.round(sample.predictions.age) : sample.predictions.age}</span>
                    {/if}
                    {#if sample.predictions.gender}
                      <span><span class="font-medium text-slate-600 dark:text-slate-300">Gender:</span> {sample.predictions.gender}</span>
                    {/if}
                  </div>
                {/if}

                <!-- Gap tags -->
                {#if sample.priority && sample.priority.gaps_hit.length > 0}
                  <div class="flex flex-wrap gap-1">
                    {#each sample.priority.gaps_hit as gap}
                      <span class="text-xs px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800">
                        {gap}
                      </span>
                    {/each}
                  </div>
                {/if}

                <!-- Explanation -->
                {#if sample.priority}
                  <p class="text-xs text-slate-400 dark:text-slate-500">{sample.priority.explanation}</p>
                {/if}

                <!-- Neighbors -->
                {#if sample.neighbors && sample.neighbors.length > 0}
                  <div class="flex flex-col gap-1 mt-1">
                    <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Nearest neighbors:</span>
                    <div class="flex gap-2">
                      {#each sample.neighbors as nb, i}
                        <div class="flex flex-col items-center gap-0.5 w-16">
                          {#if nb.image}
                            <img
                              src={imageToDataUrl(nb.image) ?? nb.image}
                              alt="neighbor {i + 1}"
                              class="w-14 h-14 object-cover rounded border border-slate-200 dark:border-slate-700"
                            />
                          {:else}
                            <div class="w-14 h-14 rounded border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-xs text-slate-400">?</div>
                          {/if}
                          <span class="text-[10px] text-slate-400 dark:text-slate-500 text-center truncate w-full" title={nb.icd_description ?? nb.icd_code ?? ""}>
                            {nb.icd_description ?? nb.icd_code ?? `#${nb.rowId}`}
                          </span>
                        </div>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}

    <!-- SUBMITTED STAGE -->
    {#if stage === "submitted"}
      <div class="rounded-xl border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/30 p-8 flex flex-col items-center gap-4">
        <svg class="w-12 h-12 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="text-center">
          <p class="text-lg font-semibold text-green-800 dark:text-green-200">Contribution submitted</p>
          {#if contributionId}
            <p class="text-sm text-green-600 dark:text-green-400 mt-1">ID: {contributionId}</p>
          {/if}
        </div>
        <button
          class="rounded-md px-4 py-2 border border-green-400 dark:border-green-600 text-green-700 dark:text-green-300 text-sm font-medium hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors"
          onclick={reset}
        >
          Upload More
        </button>
      </div>
    {/if}
  </div>
</div>
