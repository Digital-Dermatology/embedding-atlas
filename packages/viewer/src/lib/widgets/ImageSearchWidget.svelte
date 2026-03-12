<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import Cropper from "cropperjs";
  import "cropperjs/dist/cropper.css";

  import Button from "./Button.svelte";
  import SearchFilters from "./SearchFilters.svelte";

import type { ColumnDesc } from "../database_utils.js";
import type { Coordinator } from "@uwdata/mosaic-core";

interface Neighbor {
  id: any;
  distance: number;
  rowIndex?: number;
}

interface AuditFinding {
  [category: string]: {
    [key: string]: boolean | string | string[];
  };
}

interface AuditFailure {
  audit_failed: true;
  audit_issues: string[];
  audit_findings: AuditFinding;
}

type SerializedFilter =
  | { column: string; type: "string"; values: string[] }
  | { column: string; type: "string[]"; values: string[] }
  | { column: string; type: "number"; min: number | null; max: number | null };

interface $$Props {
  disabled?: boolean;
  endpoint?: string;
  coordinator: Coordinator;
  table: string;
  columns?: ColumnDesc[];
  uploadBlocked?: boolean;
  uploadBlockedMessage?: string | null;
  maxHeightClass?: string;
  scrollable?: boolean;
}

interface $$Events {
  result: {
    neighbors: Neighbor[];
    previewUrl: string | null;
    filters: SerializedFilter[];
    setStatus: (value: string) => void;
    refetch: (options?: { maxK?: number }) => Promise<boolean>;
    queryPoint: { x: number; y: number } | null;
    topK: number;
  };
}

interface $$Slots {}

const dispatch = createEventDispatcher<$$Events>();

let {
  disabled = false,
  endpoint = "/data/upload-neighbors",
  coordinator,
  table,
  columns = [] as ColumnDesc[],
  uploadBlocked = false,
  uploadBlockedMessage = null,
  maxHeightClass = "max-h-[80vh]",
  scrollable = true,
} = $props();

const MAX_AUTO_REFETCH_K = 5000;

let file: File | null = $state(null);
let previewUrl: string | null = $state(null);
let status: string = $state("");
let errorMessage: string | null = $state(null);
let uploading: boolean = $state(false);
let topK: number = $state(50);
let auditFailure: AuditFailure | null = $state(null);

let activeFilters: SerializedFilter[] = $state.raw([]);
let hasExecutedSearch = false;
let currentNeighbors: Neighbor[] = [];
let lastRequestK: number | null = null;
let refetchInProgress = false;
let lastQueryPoint: { x: number; y: number } | null = null;
let previewImageEl: HTMLImageElement | null = $state(null);
let cropper: Cropper | null = $state(null);
let cropperReady = $state(false);
let useCropSelection = $state(false);

const resolvedUploadBlockedMessage = $derived(
  uploadBlockedMessage ?? "Complete the clinical survey before uploading another case.",
);

  function resetPreview() {
    if (previewUrl != null) {
      URL.revokeObjectURL(previewUrl);
    }
    previewUrl = null;
    previewImageEl = null;
    destroyCropper();
  }

  function onFileClick(event: MouseEvent) {
    if (!uploadBlocked) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    errorMessage = resolvedUploadBlockedMessage;
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
    auditFailure = null;
  }

  function onPreviewLoad(event: Event) {
    previewImageEl = event.currentTarget as HTMLImageElement;
    initCropper();
  }

  function destroyCropper() {
    cropper?.destroy();
    cropper = null;
    cropperReady = false;
    useCropSelection = false;
  }

  function initCropper() {
    if (!previewImageEl) {
      return;
    }
    destroyCropper();
    cropper = new Cropper(previewImageEl, {
      viewMode: 1,
      dragMode: "crop",
      autoCrop: true,
      autoCropArea: 1,
      responsive: true,
      background: false,
      guides: true,
      center: true,
      movable: false,
      scalable: false,
      zoomable: false,
      ready: () => {
        cropperReady = true;
        useCropSelection = true;
      },
    });
  }

  function toggleUseCropSelection(checked: boolean) {
    useCropSelection = checked;
    if (!cropper) {
      return;
    }
    if (checked) {
      cropper.crop();
    } else {
      cropper.clear();
    }
  }

  function clearSelection() {
    useCropSelection = false;
    cropper?.clear();
  }

  onDestroy(() => {
    resetPreview();
  });

  function handleFiltersChange(event: { filters: SerializedFilter[] }) {
    activeFilters = event?.filters ?? [];
    if (!hasExecutedSearch) {
      return;
    }
    emitResult(currentNeighbors, previewUrl);
  }

  async function requestNeighbors(
    kValue: number,
  ): Promise<{ neighbors: Neighbor[]; queryPoint: { x: number; y: number } | null }>
  {
    if (!file) {
      throw new Error("No image selected.");
    }
    const uploadFile = await resolveUploadFile();
    const formData = new FormData();
    formData.append("file", uploadFile);
    const resp = await fetch(`${endpoint}?k=${encodeURIComponent(kValue)}`, {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const message = resp.status === 404 ? "Upload search is not available on this server." : `Server error (${resp.status})`;
      throw new Error(message);
    }
    const payload = await resp.json();

    // Check for anonymization audit failure
    if (payload?.audit_failed) {
      throw {
        isAuditFailure: true,
        audit_issues: payload.audit_issues ?? [],
        audit_findings: payload.audit_findings ?? {},
      };
    }

    const neighbors: Neighbor[] = Array.isArray(payload?.neighbors) ? payload.neighbors : [];
    let queryPoint: { x: number; y: number } | null = null;
    if (payload?.query != null) {
      const maybeX = Number(payload.query.x);
      const maybeY = Number(payload.query.y);
      if (Number.isFinite(maybeX) && Number.isFinite(maybeY)) {
        queryPoint = { x: maybeX, y: maybeY };
      }
    }
    return { neighbors, queryPoint };
  }

  async function resolveUploadFile(): Promise<File> {
    const activeFile = file;
    if (!activeFile || !useCropSelection || !cropper || !cropperReady) {
      return activeFile!;
    }
    let canvas: HTMLCanvasElement | null = null;
    try {
      canvas = cropper.getCroppedCanvas({
        imageSmoothingEnabled: true,
        imageSmoothingQuality: "high",
      });
    } catch {
      canvas = null;
    }
    if (!canvas || canvas.width <= 1 || canvas.height <= 1) {
      return activeFile;
    }
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, activeFile.type || "image/png"),
    );
    if (!blob) {
      return activeFile;
    }
    return new File([blob], activeFile.name, { type: blob.type || activeFile.type });
  }

  async function performAutoRefetch(options?: { maxK?: number }): Promise<boolean> {
    const { maxK = MAX_AUTO_REFETCH_K } = options ?? {};
    if (!file || uploading || refetchInProgress) {
      return false;
    }
    const currentK = lastRequestK ?? topK;
    if (currentK >= maxK) {
      return false;
    }
    const nextK = Math.min(maxK, Math.max(currentK, topK) * 2);
    if (nextK <= currentK) {
      return false;
    }
    refetchInProgress = true;
    uploading = true;
    errorMessage = null;
    status = "Searching...";
    try {
      const { neighbors, queryPoint } = await requestNeighbors(nextK);
      lastRequestK = nextK;
      emitResult(neighbors, previewUrl, { skipStatusReset: false, queryPoint });
      return true;
    } catch (err: any) {
      console.error("Upload search failed", err);
      errorMessage = err?.message ?? "Failed to query nearest neighbors.";
      status = "";
      return false;
    } finally {
      uploading = false;
      refetchInProgress = false;
    }
  }

  function emitResult(
    neighbors: Neighbor[],
    preview: string | null,
    options?: { skipStatusReset?: boolean; queryPoint?: { x: number; y: number } | null },
  ) {
    currentNeighbors = neighbors;
    hasExecutedSearch = true;
    if (!options?.skipStatusReset) {
      status = activeFilters.length > 0 ? "Filtering..." : "";
    }
    if (options && Object.prototype.hasOwnProperty.call(options, "queryPoint")) {
      lastQueryPoint = options.queryPoint ?? null;
    }
    const detail: $$Events["result"] = {
      neighbors,
      previewUrl: preview,
      filters: activeFilters,
      setStatus: (value: string) => {
        status = value;
      },
      refetch: performAutoRefetch,
      queryPoint: lastQueryPoint,
      topK,
    };
    dispatch("result", detail);
  }

  async function submit() {
    if (disabled || file == null || uploading) {
      return;
    }
    if (uploadBlocked) {
      errorMessage = resolvedUploadBlockedMessage;
      return;
    }
    errorMessage = null;
    auditFailure = null;
    status = "Embedding image...";
    uploading = true;
    try {
      const { neighbors, queryPoint } = await requestNeighbors(topK);
      lastRequestK = topK;
      emitResult(neighbors, previewUrl, { skipStatusReset: false, queryPoint });
    } catch (err: any) {
      if (err?.isAuditFailure) {
        auditFailure = {
          audit_failed: true,
          audit_issues: err.audit_issues,
          audit_findings: err.audit_findings,
        };
        status = "";
      } else {
        console.error("Upload search failed", err);
        errorMessage = err?.message ?? "Failed to query nearest neighbors.";
        status = "";
      }
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

<div
  class={`rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3 ${
    scrollable ? `${maxHeightClass} overflow-y-auto` : ""
  }`}
>
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
      onclick={onFileClick}
      disabled={disabled || uploading}
    />
  </label>

  {#if previewUrl}
    <div class="flex flex-col gap-2">
      <span class="text-slate-500 dark:text-slate-400 font-medium">Preview</span>
      <div class="flex flex-col gap-2">
        <div class="relative max-w-full">
          <img
            bind:this={previewImageEl}
            src={previewUrl}
            alt="Uploaded preview"
            class="block rounded-md border border-slate-200 dark:border-slate-700 max-h-56 w-full bg-slate-100 dark:bg-slate-800"
            onload={onPreviewLoad}
          />
        </div>
        <div class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span>Drag the handles to adjust the crop area.</span>
          <label class="ml-auto flex items-center gap-2">
            <input
              type="checkbox"
              class="accent-blue-500"
              checked={useCropSelection}
              onchange={(event) => toggleUseCropSelection((event.target as HTMLInputElement).checked)}
              disabled={disabled || uploading || !cropperReady}
            />
            <span>Use crop</span>
          </label>
          <Button label="Clear" onClick={clearSelection} disabled={disabled || uploading || !cropperReady} />
        </div>
      </div>
    </div>
  {/if}

  <SearchFilters
    disabled={disabled}
    coordinator={coordinator}
    table={table}
    columns={columns}
    on:change={handleFiltersChange}
  />

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
  {#if auditFailure}
    <div class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 p-4 flex flex-col gap-3">
      <div class="flex items-center gap-2">
        <svg class="w-5 h-5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
        <span class="font-semibold text-red-700 dark:text-red-300">Anonymization Audit Failed</span>
      </div>
      <p class="text-sm text-red-600 dark:text-red-400">This image was blocked because potential re-identification risks were detected:</p>
      <ul class="list-disc list-inside text-sm text-red-600 dark:text-red-400 space-y-1">
        {#each auditFailure.audit_issues as issue}
          <li>{issue}</li>
        {/each}
      </ul>
      {#if auditFailure.audit_findings && Object.keys(auditFailure.audit_findings).length > 0}
        <details class="text-xs text-slate-600 dark:text-slate-400">
          <summary class="cursor-pointer font-medium hover:text-slate-800 dark:hover:text-slate-200">Full audit details</summary>
          <div class="mt-2 space-y-2">
            {#each Object.entries(auditFailure.audit_findings) as [category, fields]}
              <div>
                <span class="font-semibold text-slate-700 dark:text-slate-300">{category}</span>
                <div class="ml-3 mt-0.5 space-y-0.5">
                  {#each Object.entries(fields) as [key, value]}
                    <div class="flex gap-2">
                      <span class="text-slate-500 dark:text-slate-400">{key}:</span>
                      <span class="{typeof value === 'boolean' && value ? 'text-red-600 dark:text-red-400 font-medium' : ''}">
                        {#if typeof value === 'boolean'}
                          {value ? 'Yes' : 'No'}
                        {:else if Array.isArray(value)}
                          {value.length > 0 ? value.join(', ') : '—'}
                        {:else}
                          {value || '—'}
                        {/if}
                      </span>
                    </div>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        </details>
      {/if}
    </div>
  {/if}
  {#if file == null}
    <div class="text-slate-400 dark:text-slate-500">Select a JPG or PNG file to enable the search button.</div>
  {/if}
</div>
