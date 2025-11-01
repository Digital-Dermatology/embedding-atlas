<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import Mark from "mark.js";

  import TooltipContent from "./TooltipContent.svelte";

  import { IconClose } from "./icons.js";
  import type { ColumnStyle } from "./renderers/index.js";
  import type { SearchResultItem } from "./search.js";

  interface Props {
    items: SearchResultItem[];
    label: string;
    highlight: string;
    visibleCount?: number;
    hasMore?: boolean;
    loadingMore?: boolean;
    columnStyles?: Record<string, ColumnStyle>;
    onClick?: (item: SearchResultItem) => void;
    onClose?: () => void;
    onLoadMore?: () => void;
  }

  let {
    items,
    label,
    highlight,
    visibleCount = 100,
    hasMore = false,
    loadingMore = false,
    columnStyles,
    onClick,
    onClose,
    onLoadMore,
  }: Props = $props();

  function markHighlight(element: HTMLElement, highlight: string) {
    let m = new Mark(element);
    m.mark(highlight);
  }

  let safeVisibleCount = $derived(visibleCount < 0 ? 0 : visibleCount);
  let visibleItems = $derived(items.slice(0, safeVisibleCount));
  let displayedCount = $derived(visibleItems.length);
  let totalCount = $derived(items.length);

  let resultCountText = $derived(
    totalCount === 0
      ? "No result found."
      : totalCount === 1 && displayedCount === totalCount && !hasMore
        ? `${totalCount.toLocaleString()} result.`
        : displayedCount < totalCount || hasMore
          ? `Showing ${displayedCount.toLocaleString()} of ${totalCount.toLocaleString()} results.`
          : `${totalCount.toLocaleString()} results.`,
  );
</script>

<div class="flex flex-col w-full h-full">
  <div class="ml-3 mr-2 my-1 flex items-center text-slate-400 dark:text-slate-500 items-start">
    <div class="flex-1">
      <div>{label}</div>
      <div>{resultCountText}</div>
    </div>
    <div class="flex-none mt-1">
      <button
        class="block hover:text-slate-500 dark:hover:text-slate-400"
        onclick={() => {
          onClose?.();
        }}
      >
        <IconClose />
      </button>
    </div>
  </div>
  <hr class="border-slate-300 dark:border-slate-600" />
  <div class="flex flex-col overflow-x-hidden overflow-y-scroll">
    {#each visibleItems as item (item)}
      <button
        class="m-1 p-2 text-left rounded-md hover:outline outline-slate-500"
        onclick={() => {
          onClick?.(item);
        }}
      >
        {#if item.distance != null}
          <div class="flex pb-1 text-sm">
            <span class="px-2 flex gap-2 bg-slate-200 text-slate-500 dark:bg-slate-600 dark:text-slate-300 rounded-md">
              <div class="text-slate-400 dark:text-slate-400 font-medium">Distance</div>
              <div class="text-ellipsis whitespace-nowrap overflow-hidden max-w-72">
                {item.distance.toFixed(5)}
              </div>
            </span>
          </div>
        {/if}
        <div class="overflow-hidden text-ellipsis line-clamp-4 leading-5" use:markHighlight={highlight}>
          <TooltipContent values={item.fields} columnStyles={columnStyles ?? {}} />
        </div>
      </button>
      <hr class="border-slate-300 dark:border-slate-600" />
    {/each}
    {#if hasMore}
      <button
        class="m-3 mt-4 px-4 py-2 rounded-md border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-60 disabled:cursor-not-allowed"
        disabled={loadingMore}
        onclick={() => {
          onLoadMore?.();
        }}
      >
        {loadingMore ? "Loading more..." : "Load more results"}
      </button>
    {/if}
  </div>
</div>
