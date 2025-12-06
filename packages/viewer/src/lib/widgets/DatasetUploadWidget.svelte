<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";

  import { nanoid } from "nanoid";

  import type { UploadedSamplePoint } from "../UploadedSamplesOverlay.svelte";

  import Button from "./Button.svelte";
  import Spinner from "../Spinner.svelte";

  interface $$Props {
    endpoint?: string;
    disabled?: boolean;
    uploadBlocked?: boolean;
    uploadBlockedMessage?: string | null;
  }

  interface $$Events {
    result: {
      points: UploadedSamplePoint[];
      errors: { label: string; message: string }[];
      truncated?: boolean;
    };
    select: { point: UploadedSamplePoint };
    clear: {};
  }

  const dispatch = createEventDispatcher<$$Events>();

  let {
    endpoint = "/data/upload-embeddings",
    disabled = false,
    uploadBlocked = false,
    uploadBlockedMessage = null,
  }: $$Props = $props();

  const defaultBlockedMessage =
    uploadBlockedMessage ?? "Complete the clinical survey before uploading another case.";
  const MAX_FILES = 64;

  let files: File[] = $state([]);
  let previews = $state.raw(new Map<string, string>());
  let status: string = $state("");
  let errorMessage: string | null = $state(null);
  let uploading: boolean = $state(false);
  let results: UploadedSamplePoint[] = $state([]);
  let errors: { label: string; message: string }[] = $state([]);
  let truncated = $state(false);

  function resetPreviews() {
    previews.forEach((url) => URL.revokeObjectURL(url));
    previews.clear();
  }

  onDestroy(() => {
    resetPreviews();
  });

  function onFileChange(event: Event) {
    if (uploadBlocked) {
      event.preventDefault();
      event.stopPropagation();
      errorMessage = defaultBlockedMessage;
      return;
    }
    const target = event.target as HTMLInputElement;
    const selected = target.files ? Array.from(target.files).slice(0, MAX_FILES) : [];
    resetPreviews();
    selected.forEach((file) => {
      previews.set(file.name, URL.createObjectURL(file));
    });
    files = selected;
    results = [];
    errors = [];
    truncated = false;
    status = "";
    errorMessage = null;
  }

  function normalizedPoints(rawPoints: any[]): UploadedSamplePoint[] {
    const normalized: UploadedSamplePoint[] = [];
    rawPoints.forEach((point, idx) => {
      const label =
        typeof point?.label === "string" && point.label.trim() !== ""
          ? point.label
          : `sample-${idx + 1}`;
      const id =
        typeof point?.id === "string" && point.id.trim() !== ""
          ? point.id
          : `${label}-${nanoid(6)}`;
      const x = Number(point?.x);
      const y = Number(point?.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        return;
      }
      const previewUrl = previews.get(label) ?? null;
      normalized.push({ id, label, x, y, previewUrl });
    });
    return normalized;
  }

  function normalizedErrors(rawErrors: any[]): { label: string; message: string }[] {
    return rawErrors
      .map((err, idx) => {
        const label =
          typeof err?.label === "string" && err.label.trim() !== ""
            ? err.label
            : typeof err?.file === "string" && err.file.trim() !== ""
              ? err.file
              : `sample-${idx + 1}`;
        const message = typeof err?.message === "string" ? err.message : "Failed to embed sample.";
        return { label, message };
      })
      .filter((err) => err.message.trim() !== "");
  }

  async function submit() {
    if (disabled || uploading) {
      return;
    }
    if (uploadBlocked) {
      errorMessage = defaultBlockedMessage;
      return;
    }
    if (files.length === 0) {
      errorMessage = "Select one or more image files first.";
      return;
    }
    uploading = true;
    errorMessage = null;
    status = "Embedding samples...";
    truncated = false;
    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      const resp = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const reason = resp.status === 404 ? "Batch embedding is not available on this server." : `Server error (${resp.status})`;
        throw new Error(reason);
      }
      const payload = await resp.json();
      const points = normalizedPoints(Array.isArray(payload?.points) ? payload.points : []);
      const parsedErrors = normalizedErrors(Array.isArray(payload?.errors) ? payload.errors : []);
      results = points;
      errors = parsedErrors;
      truncated = Boolean(payload?.truncated);
      status = points.length > 0 ? `Embedded ${points.length} sample${points.length === 1 ? "" : "s"}.` : "";
      dispatch("result", { points, errors: parsedErrors, truncated });
    } catch (err: any) {
      console.error("Batch upload failed", err);
      errorMessage = err?.message ?? "Failed to upload dataset.";
      status = "";
    } finally {
      uploading = false;
    }
  }

  function selectPoint(point: UploadedSamplePoint) {
    dispatch("select", { point });
  }

  function clearResults() {
    results = [];
    errors = [];
    truncated = false;
    status = "";
    dispatch("clear", {});
  }
</script>

<div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3">
  <div class="flex flex-col gap-1">
    <span class="text-base font-semibold text-slate-700 dark:text-slate-200">Batch Embedding</span>
    <span class="text-slate-500 dark:text-slate-400">Upload a small set of images to project them onto the map.</span>
  </div>

  <label class="flex flex-col gap-2 text-slate-600 dark:text-slate-300">
    <span class="font-medium">Image Files</span>
    <input
      class="block text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-100 file:text-slate-700 dark:file:bg-slate-800 dark:file:text-slate-200 dark:file:border-slate-600"
      type="file"
      multiple
      accept="image/*"
      onchange={onFileChange}
      disabled={disabled || uploading}
    />
    <span class="text-xs text-slate-400 dark:text-slate-500">Up to {MAX_FILES} images per upload.</span>
  </label>

  {#if files.length > 0}
    <div class="flex flex-col gap-1 text-xs text-slate-500 dark:text-slate-400">
      <span class="font-medium text-slate-600 dark:text-slate-300">{files.length} file{files.length === 1 ? "" : "s"} selected</span>
      <div class="max-h-24 overflow-y-auto rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-2 flex flex-col gap-1">
        {#each files as file (file.name)}
          <div class="flex items-center gap-2">
            <span class="truncate flex-1" title={file.name}>{file.name}</span>
            <span class="text-slate-400 dark:text-slate-500 whitespace-nowrap">{(file.size / 1024).toFixed(0)} KB</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="flex items-center gap-3">
    <Button
      class="ml-auto"
      disabled={disabled || uploading || files.length === 0}
      onClick={submit}
      label={uploading ? "Embedding..." : "Embed samples"}
    />
    {#if results.length > 0 || errors.length > 0}
      <Button class="!bg-slate-200 dark:!bg-slate-800 !text-slate-700 dark:!text-slate-200" label="Clear" onClick={clearResults} />
    {/if}
  </div>

  {#if status}
    <div class="text-slate-500 dark:text-slate-400">{status}{truncated ? " (truncated to limit)" : ""}</div>
  {/if}
  {#if errorMessage}
    <div class="text-red-600 dark:text-red-400">{errorMessage}</div>
  {/if}

  {#if uploading}
    <div class="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm">
      <Spinner status="Processing uploads..." />
    </div>
  {/if}

  {#if results.length > 0}
    <div class="flex flex-col gap-2">
      <div class="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">Embedded samples</div>
      <div class="flex flex-col gap-1 max-h-40 overflow-y-auto pr-1">
        {#each results as point (point.id)}
          <button
            class="flex items-center gap-2 text-left rounded-md border border-transparent hover:border-sky-200 dark:hover:border-sky-700 px-2 py-1 transition-colors"
            onclick={() => selectPoint(point)}
          >
            <div class="w-2.5 h-2.5 rounded-full bg-sky-500 border border-sky-700"></div>
            <span class="flex-1 truncate text-slate-700 dark:text-slate-200">{point.label ?? point.id}</span>
            <span class="text-xs text-slate-400 dark:text-slate-500">{point.x.toFixed(2)}, {point.y.toFixed(2)}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  {#if errors.length > 0}
    <div class="flex flex-col gap-1">
      <div class="text-xs text-red-500 dark:text-red-400 uppercase tracking-wide">Errors</div>
      <div class="flex flex-col gap-1 max-h-32 overflow-y-auto pr-1">
        {#each errors as issue, idx (issue.label + idx)}
          <div class="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded px-2 py-1">
            <span class="font-medium">{issue.label}</span>: {issue.message}
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>
