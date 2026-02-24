<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { SearchResultItem } from "./search.js";

  interface ClinicalFeedbackContext {
    mode: "neighbors" | "upload";
    signature: string;
    query: any;
    queryDisplay: string;
    uploadSummary:
      | {
          previewUrl: string | null;
          filters: any[];
          topK: number;
        }
      | null;
  }

  interface Props {
    route: string | null;
    context: ClinicalFeedbackContext | null;
    searchResult: { label: string; highlight: string; items: SearchResultItem[] } | null;
    selectedSample: SearchResultItem | null;
    onClearSelection?: () => void;
  }

  let { route, context, searchResult, selectedSample = null, onClearSelection }: Props = $props();

  let benefitScore: number = $state(5);
  let noneAreSimilar: boolean = $state(false);
  let wantsComment: boolean = $state(false);
  let comment: string = $state("");
  let submitting: boolean = $state(false);
  let submitSuccess: boolean = $state(false);
  let submitError: string | null = $state(null);

  let lastSignature: string | null = $state(null);
  const dispatch = createEventDispatcher<{ submitted: { signature: string | null } }>();

  function signatureFor(value: ClinicalFeedbackContext | null): string | null {
    return value?.signature ?? null;
  }

  function resetForm() {
    benefitScore = 5;
    noneAreSimilar = false;
    wantsComment = false;
    comment = "";
    submitting = false;
    submitSuccess = false;
    submitError = null;
  }

  $effect(() => {
    const currentSignature = signatureFor(context);
    if (currentSignature !== lastSignature) {
      lastSignature = currentSignature;
      resetForm();
    }
  });

  // When a sample is selected, clear "none are similar"
  $effect(() => {
    if (selectedSample != null) {
      noneAreSimilar = false;
    }
  });

  function handleNoneAreSimilar() {
    noneAreSimilar = !noneAreSimilar;
    if (noneAreSimilar) {
      onClearSelection?.();
    }
  }

  function selectedSampleRank(sample: SearchResultItem | null): number | null {
    if (sample == null || searchResult == null) return null;
    const idx = searchResult.items.findIndex((item) => item.id === sample.id);
    return idx >= 0 ? idx + 1 : null;
  }

  function extractTopResults(items: SearchResultItem[]) {
    return items.slice(0, 10).map((item, index) => ({
      rank: index + 1,
      id: item.id ?? null,
      distance:
        typeof item.distance === "number" && Number.isFinite(item.distance) ? item.distance : null,
      condition: item.fields?.condition ?? null,
      dataset: item.fields?.dataset ?? null,
      text: item.fields?.text_short ?? item.text ?? null,
    }));
  }

  async function handleSubmit(event: Event) {
    event.preventDefault();
    submitError = null;
    submitSuccess = false;

    if (benefitScore < 1 || benefitScore > 10) {
      submitError = "Please rate the benefit between 1 and 10.";
      return;
    }
    if (selectedSample == null && !noneAreSimilar) {
      submitError = "Please select the most similar result, or mark \"None are similar\".";
      return;
    }
    if (wantsComment && comment.trim().length === 0) {
      submitError = "Add a comment or uncheck the comment box.";
      return;
    }
    if (!context || !searchResult || searchResult.items.length === 0) {
      submitError = "Search details are unavailable. Please run the search again.";
      return;
    }

    const trimmedComment = wantsComment ? comment.trim() : "";
    const signature = signatureFor(context);
    const rank = selectedSampleRank(selectedSample);
    const payload = {
      route,
      timestamp: new Date().toISOString(),
      searchSignature: signature,
      answers: {
        benefitScore,
        selectedMostSimilar: selectedSample != null ? {
          id: selectedSample.id ?? null,
          rank: rank,
          distance: typeof selectedSample.distance === "number" && Number.isFinite(selectedSample.distance) ? selectedSample.distance : null,
          condition: selectedSample.fields?.condition ?? null,
        } : null,
        noneAreSimilar,
        wantsComment,
        comment: trimmedComment,
      },
      search: {
        query: context.query,
        queryDisplay: context.queryDisplay,
        mode: context.mode,
        label: searchResult.label,
        highlight: searchResult.highlight,
        totalResults: searchResult.items.length,
        topResults: extractTopResults(searchResult.items),
        uploadSummary: context.uploadSummary ?? undefined,
      },
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      location: typeof window !== "undefined" ? window.location.href : null,
    };

    submitting = true;
    try {
      const response = await fetch("/data/clinical-feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let message: string;
        try {
          const data = await response.json();
          message = data?.error ?? `Request failed (${response.status})`;
        } catch {
          message = `Request failed (${response.status})`;
        }
        throw new Error(message);
      }
      submitSuccess = true;
      dispatch("submitted", { signature });
    } catch (error: any) {
      submitError = error?.message ?? "Failed to send feedback.";
    } finally {
      submitting = false;
    }
  }

  const submitButtonLabel = $derived(
    submitSuccess ? "Feedback submitted" : submitting ? "Submitting..." : "Submit feedback",
  );
  const submitButtonDisabled = $derived(submitting || submitSuccess);

  let selectedRank = $derived(selectedSampleRank(selectedSample));
  let selectedCondition = $derived(selectedSample?.fields?.condition ?? null);
  let selectedDistance = $derived(
    typeof selectedSample?.distance === "number" && Number.isFinite(selectedSample.distance)
      ? selectedSample.distance
      : null,
  );
</script>

<div class="rounded-xl border border-emerald-700/80 bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-800 text-sm text-emerald-50 flex flex-col gap-4 p-4 shadow-xl shadow-emerald-900/40">
  <div class="flex flex-col gap-1">
    <div class="text-lg font-semibold text-emerald-50">Search Feedback</div>
    <p class="text-xs text-emerald-200/80">Required before you can upload the next case.</p>
  </div>
  <form class="flex flex-col gap-4" onsubmit={handleSubmit}>
    <div class="flex flex-col gap-2">
      <span class="text-xs font-medium uppercase tracking-wide text-emerald-200/80">
        1. Benefit of this search
      </span>
      <div class="flex items-center gap-3">
        <input
          type="range"
          min="1"
          max="10"
          step="1"
          bind:value={benefitScore}
          class="flex-1 accent-emerald-400"
          aria-label="Benefit of this search (1 to 10)"
        />
        <span class="w-10 text-center text-base font-semibold text-emerald-50">
          {benefitScore}
        </span>
      </div>
      <div class="text-xs text-emerald-200/70">1 = not helpful, 10 = extremely helpful</div>
    </div>
    <div class="flex flex-col gap-2">
      <span class="text-xs font-medium uppercase tracking-wide text-emerald-200/80">
        2. Select the most similar result
      </span>
      {#if selectedSample != null}
        <div class="rounded-md border border-emerald-500/60 bg-emerald-950/60 px-3 py-2 flex flex-col gap-1">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-emerald-300">Rank #{selectedRank ?? "?"}</span>
            {#if selectedDistance != null}
              <span class="text-xs text-emerald-200/70">dist: {selectedDistance.toFixed(5)}</span>
            {/if}
          </div>
          {#if selectedCondition}
            <div class="text-xs text-emerald-100 truncate">{selectedCondition}</div>
          {/if}
          <button
            type="button"
            class="mt-1 text-xs text-emerald-300/80 hover:text-emerald-200 underline self-start"
            onclick={() => { onClearSelection?.(); }}
          >
            Clear selection
          </button>
        </div>
      {:else if noneAreSimilar}
        <div class="text-xs text-emerald-200/70 italic">Marked as: none of the results are similar.</div>
      {:else}
        <div class="text-xs text-emerald-200/70">Click a "Select" button on a result in the right panel.</div>
      {/if}
      <button
        type="button"
        class="self-start text-xs px-2 py-1 rounded border transition {noneAreSimilar ? 'border-emerald-400 bg-emerald-400 text-emerald-950 font-semibold' : 'border-emerald-600 text-emerald-200/80 hover:border-emerald-400 hover:text-emerald-100'}"
        onclick={handleNoneAreSimilar}
      >
        {noneAreSimilar ? "None are similar (selected)" : "None are similar"}
      </button>
    </div>
    <div class="flex flex-col gap-2 text-emerald-50">
      <label class="inline-flex items-center gap-2">
        <input
          type="checkbox"
          bind:checked={wantsComment}
          class="h-4 w-4 rounded border border-emerald-500/60 bg-transparent accent-emerald-400"
        />
        <span>I want to say something about the search</span>
      </label>
      {#if wantsComment}
        <textarea
          rows="3"
          bind:value={comment}
          class="w-full rounded-md border border-emerald-600 bg-emerald-950/60 text-sm text-emerald-50 placeholder:text-emerald-200/70 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-emerald-400"
          placeholder="Share your thoughts..."
        ></textarea>
      {/if}
    </div>
    {#if submitError}
      <div class="text-xs text-rose-200">{submitError}</div>
    {/if}
    {#if submitSuccess}
      <div class="text-xs text-emerald-200">Thanks for your feedback!</div>
    {/if}
    <div class="flex justify-end">
      <button
        type="submit"
        class="px-4 py-2 rounded-md border border-emerald-500 bg-emerald-400 text-sm font-semibold text-emerald-950 hover:bg-emerald-300 transition disabled:opacity-60 disabled:cursor-not-allowed"
        disabled={submitButtonDisabled}
      >
        {submitButtonLabel}
      </button>
    </div>
  </form>
</div>
