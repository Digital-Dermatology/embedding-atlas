<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";

  import Button from "./Button.svelte";

  interface Neighbor {
    id: any;
    distance: number;
    rowIndex?: number;
  }

  const dispatch = createEventDispatcher<{ result: { neighbors: Neighbor[]; previewUrl: string | null } }>();

  export let disabled = false;
  export let endpoint = "/data/upload-neighbors";

  let file: File | null = null;
  let previewUrl: string | null = null;
  let status: string = "";
  let errorMessage: string | null = null;
  let uploading = false;
  let topK = 16;

  function resetPreview() {
    if (previewUrl != null) {
      URL.revokeObjectURL(previewUrl);
    }
    previewUrl = null;
  }

  function onFileChange(event: Event) {
    const target = event.target as HTMLInputElement;
    if (!target.files || target.files.length === 0) {
      file = null;
      resetPreview();
      return;
    }
    file = target.files[0];
    resetPreview();
    previewUrl = URL.createObjectURL(file);
    status = "";
    errorMessage = null;
  }

  onDestroy(() => {
    resetPreview();
  });

  async function submit() {
    if (disabled || file == null || uploading) {
      return;
    }
    errorMessage = null;
    status = "Embedding image...";
    uploading = true;
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch(`${endpoint}?k=${encodeURIComponent(topK)}`, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const message = resp.status === 404 ? "Upload search is not available on this server." : `Server error (${resp.status})`;
        throw new Error(message);
      }
      const payload = await resp.json();
      const neighbors: Neighbor[] = Array.isArray(payload?.neighbors) ? payload.neighbors : [];
      status = neighbors.length > 0 ? `Found ${neighbors.length} neighbor${neighbors.length === 1 ? "" : "s"}.` : "No neighbors found.";
      dispatch("result", { neighbors, previewUrl });
    } catch (err: any) {
      console.error("Upload search failed", err);
      errorMessage = err?.message ?? "Failed to query nearest neighbors.";
      status = "";
    } finally {
      uploading = false;
    }
  }

  function updateTopK(value: string) {
    const parsed = parseInt(value, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      topK = Math.min(parsed, 200);
    }
  }
</script>

<div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3">
  <div class="flex flex-col gap-1">
    <span class="text-base font-semibold text-slate-700 dark:text-slate-200">Image Neighbor Search</span>
    <span class="text-slate-500 dark:text-slate-400">Upload an image to find visually similar samples in SkinMap.</span>
  </div>

  <label class="flex flex-col gap-2 text-slate-600 dark:text-slate-300">
    <span class="font-medium">Image File</span>
    <input
      class="block text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-100 file:text-slate-700 dark:file:bg-slate-800 dark:file:text-slate-200 dark:file:border-slate-600"
      type="file"
      accept="image/*"
      onchange={onFileChange}
      disabled={disabled || uploading}
    />
  </label>

  {#if previewUrl}
    <div class="flex flex-col gap-2">
      <span class="text-slate-500 dark:text-slate-400 font-medium">Preview</span>
      <img src={previewUrl} alt="Uploaded preview" class="rounded-md border border-slate-200 dark:border-slate-700 max-h-48 object-contain bg-slate-100 dark:bg-slate-800" />
    </div>
  {/if}

  <div class="flex items-center gap-3">
    <div class="flex items-center gap-2">
      <span class="text-slate-500 dark:text-slate-400">Top K</span>
      <input
        class="w-20 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1"
        type="number"
        min="1"
        max="200"
        step="1"
        value={topK}
        disabled={disabled || uploading}
        oninput={(event) => updateTopK((event.target as HTMLInputElement).value)}
      />
    </div>
    <Button
      class="ml-auto"
      disabled={disabled || uploading || file == null}
      onClick={submit}
      label={uploading ? "Searching..." : "Find Neighbors"}
    />
  </div>

  {#if status}
    <div class="text-slate-500 dark:text-slate-400">{status}</div>
  {/if}
  {#if errorMessage}
    <div class="text-red-600 dark:text-red-400">{errorMessage}</div>
  {/if}
  {#if file == null}
    <div class="text-slate-400 dark:text-slate-500">Select a JPG or PNG file to enable the search button.</div>
  {/if}
</div>
