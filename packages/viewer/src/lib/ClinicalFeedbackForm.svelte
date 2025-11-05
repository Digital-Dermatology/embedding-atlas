<script lang="ts">
  import type { SearchResultItem } from "./search.js";

  interface Props {
    route: string | null;
    searchArgs: { query: any; mode: "full-text" | "vector" | "neighbors" } | null;
    searchResult: { label: string; highlight: string; items: SearchResultItem[] } | null;
  }

  let { route, searchArgs, searchResult }: Props = $props();

  let benefitScore: number = $state(5);
  let differentialCorrect: "yes" | "no" | "" = $state("");
  let wantsComment: boolean = $state(false);
  let comment: string = $state("");
  let submitting: boolean = $state(false);
  let submitSuccess: boolean = $state(false);
  let submitError: string | null = $state(null);

  let lastSignature: string | null = $state(null);

  function signatureFor(args: Props["searchArgs"]): string | null {
    if (!args) {
      return null;
    }
    return `${args.mode}:${String(args.query ?? "")}`;
  }

  function resetForm() {
    benefitScore = 5;
    differentialCorrect = "";
    wantsComment = false;
    comment = "";
    submitting = false;
    submitSuccess = false;
    submitError = null;
  }

  $effect(() => {
    const currentSignature = signatureFor(searchArgs);
    if (currentSignature !== lastSignature) {
      lastSignature = currentSignature;
      resetForm();
    }
  });

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
    if (differentialCorrect === "") {
      submitError = "Please tell us if the differential diagnosis was correct.";
      return;
    }
    if (wantsComment && comment.trim().length === 0) {
      submitError = "Add a comment or uncheck the comment box.";
      return;
    }
    if (!searchArgs || searchArgs.mode !== "neighbors" || !searchResult || searchResult.items.length === 0) {
      submitError = "Search details are unavailable. Please run the search again.";
      return;
    }

    const trimmedComment = wantsComment ? comment.trim() : "";
    const signature = signatureFor(searchArgs);
    const payload = {
      route,
      timestamp: new Date().toISOString(),
      searchSignature: signature,
      answers: {
        benefitScore,
        differentialDiagnosisInTop10: differentialCorrect === "yes",
        wantsComment,
        comment: trimmedComment,
      },
      search: {
        query: searchArgs.query,
        queryDisplay: String(searchArgs.query ?? ""),
        mode: searchArgs.mode,
        label: searchResult.label,
        highlight: searchResult.highlight,
        totalResults: searchResult.items.length,
        topResults: extractTopResults(searchResult.items),
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
</script>

<div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3">
  <div class="text-sm font-semibold text-slate-600 dark:text-slate-300 select-none">Search Feedback</div>
  <form class="flex flex-col gap-4" onsubmit={handleSubmit}>
    <div class="flex flex-col gap-2">
      <span class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        1. Benefit of this search
      </span>
      <div class="flex items-center gap-3">
        <input
          type="range"
          min="1"
          max="10"
          step="1"
          bind:value={benefitScore}
          class="flex-1 accent-slate-600 dark:accent-slate-300"
          aria-label="Benefit of this search (1 to 10)"
        />
        <span class="w-8 text-center text-sm font-semibold text-slate-600 dark:text-slate-200">
          {benefitScore}
        </span>
      </div>
      <div class="text-xs text-slate-400 dark:text-slate-500">1 = not helpful, 10 = extremely helpful</div>
    </div>
    <div class="flex flex-col gap-2">
      <span class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        2. Differential diagnosis in the top 10?
      </span>
      <div class="flex items-center gap-4">
        <label class="inline-flex items-center gap-2 text-slate-600 dark:text-slate-300">
          <input
            type="radio"
            name="clinical-feedback-dx"
            value="yes"
            bind:group={differentialCorrect}
            class="h-4 w-4 accent-slate-600 dark:accent-slate-300"
          />
          <span>Yes</span>
        </label>
        <label class="inline-flex items-center gap-2 text-slate-600 dark:text-slate-300">
          <input
            type="radio"
            name="clinical-feedback-dx"
            value="no"
            bind:group={differentialCorrect}
            class="h-4 w-4 accent-slate-600 dark:accent-slate-300"
          />
          <span>No</span>
        </label>
      </div>
    </div>
    <div class="flex flex-col gap-2">
      <label class="inline-flex items-center gap-2 text-slate-600 dark:text-slate-300">
        <input
          type="checkbox"
          bind:checked={wantsComment}
          class="h-4 w-4 rounded border-slate-300 dark:border-slate-600 accent-slate-600 dark:accent-slate-300"
        />
        <span>I want to say something about the search</span>
      </label>
      {#if wantsComment}
        <textarea
          rows="3"
          bind:value={comment}
          class="w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-600 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="Share your thoughts..."
        ></textarea>
      {/if}
    </div>
    {#if submitError}
      <div class="text-xs text-red-500 dark:text-red-400">{submitError}</div>
    {/if}
    {#if submitSuccess}
      <div class="text-xs text-emerald-600 dark:text-emerald-400">Thanks for your feedback!</div>
    {/if}
    <div class="flex justify-end">
      <button
        type="submit"
        class="px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed"
        disabled={submitButtonDisabled}
      >
        {submitButtonLabel}
      </button>
    </div>
  </form>
</div>
