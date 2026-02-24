<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import Mark from "mark.js";
  import { tick } from "svelte";

  import TooltipContent from "./TooltipContent.svelte";

  import { IconClose } from "./icons.js";
  import type { ColumnStyle } from "./renderers/index.js";
  import type { SearchResultItem } from "./search.js";

  interface NeighborGroupEntry {
    key: string;
    label: string;
    representative: SearchResultItem;
    items: SearchResultItem[];
    count: number;
    distance: number;
  }

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
    groupMode?: boolean;
    groups?: NeighborGroupEntry[] | null;
    groupColors?: Record<string, string> | null;
    activeGroupKey?: string | null;
    activeGroupLabel?: string | null;
    onGroupSelect?: (key: string) => void;
    onGroupBack?: () => void;
    selectionMode?: boolean;
    selectedItemId?: any;
    onSelectItem?: (item: SearchResultItem) => void;
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
    groupMode = false,
    groups = null,
    groupColors = null,
    activeGroupKey = null,
    activeGroupLabel = null,
    onGroupSelect,
    onGroupBack,
    selectionMode = false,
    selectedItemId = null,
    onSelectItem,
  }: Props = $props();

  function markHighlight(element: HTMLElement, highlight: string) {
    let marker = new Mark(element);
    let current = highlight;
    const apply = (value: string) => {
      marker.unmark({
        done: () => {
          if (value && value.trim() !== "") {
            marker.mark(value);
          }
        },
      });
    };
    apply(current);
    return {
      update(value: string) {
        if (value === current) {
          return;
        }
        current = value;
        apply(current);
      },
      destroy() {
        marker.unmark();
      },
    };
  }

  let listContainer: HTMLElement | null = null;

  async function handleLoadMore(event: MouseEvent) {
    const button = event.currentTarget as HTMLButtonElement | null;
    const container = listContainer;
    const previousScrollTop = container?.scrollTop ?? null;
    button?.blur();
    try {
      await onLoadMore?.();
    } finally {
      await tick();
      if (container != null && previousScrollTop != null) {
        container.scrollTop = previousScrollTop;
      }
    }
  }

  let safeVisibleCount = $derived(visibleCount < 0 ? 0 : visibleCount);
  let visibleItems = $derived(items.slice(0, safeVisibleCount));
  let displayedCount = $derived(visibleItems.length);
  let totalCount = $derived(items.length);
  let safeGroups = $derived(groups ?? []);
  let showGroupSummary = $derived(groupMode && activeGroupKey == null && safeGroups.length > 0);
  let groupVisibleCount = $derived(
    showGroupSummary ? Math.min(safeVisibleCount === 0 ? safeGroups.length : safeVisibleCount, safeGroups.length) : 0,
  );
  let visibleGroups = $derived(showGroupSummary ? safeGroups.slice(0, groupVisibleCount) : []);
  let totalGroupCount = $derived(showGroupSummary ? safeGroups.length : 0);

  let resultCountText = $derived(
    showGroupSummary
      ? totalGroupCount === 0
        ? "No matching conditions."
        : groupVisibleCount < totalGroupCount || hasMore
          ? `Showing ${groupVisibleCount.toLocaleString()} of ${totalGroupCount.toLocaleString()} condition groups.`
          : `${totalGroupCount.toLocaleString()} condition group${totalGroupCount === 1 ? "" : "s"}.`
      : totalCount === 0
        ? groupMode && activeGroupKey != null
          ? "No samples in this condition."
          : "No result found."
        : displayedCount < totalCount || hasMore
          ? `Showing ${displayedCount.toLocaleString()} of ${totalCount.toLocaleString()} results${groupMode && activeGroupKey != null ? ` for ${activeGroupLabel ?? activeGroupKey}.` : "."}`
          : `${totalCount.toLocaleString()} result${totalCount === 1 ? "" : "s"}${groupMode && activeGroupKey != null ? ` for ${activeGroupLabel ?? activeGroupKey}.` : "."}`,
  );
</script>

<div class="flex flex-col w-full h-full">
  <div class="ml-3 mr-2 my-1 flex items-start text-slate-400 dark:text-slate-500">
    <div class="flex-1 pr-2">
      <div>{label}</div>
      <div class="flex items-center gap-2">
        <span>{resultCountText}</span>
        {#if groupMode && activeGroupKey != null && typeof onGroupBack === "function"}
          <button
            class="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 font-medium"
            onclick={() => {
              onGroupBack?.();
            }}
          >
            Back to groups
          </button>
        {/if}
      </div>
    </div>
    <div class="flex-none mt-0.5">
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
  <div class="flex flex-col overflow-x-hidden overflow-y-scroll pb-4 pr-1" bind:this={listContainer}>
    {#if showGroupSummary}
      {#if visibleGroups.length === 0}
        <div class="px-3 py-4 text-slate-400 dark:text-slate-500 text-sm select-none">No conditions available.</div>
      {:else}
        {#each visibleGroups as group (group.key)}
          <button
            class="m-1 p-2 text-left rounded-md hover:outline outline-slate-500"
            onclick={() => {
              onGroupSelect?.(group.key);
            }}
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex items-center gap-2">
                {#if groupColors?.[group.key]}
                  <span
                    class="h-2.5 w-2.5 rounded-full border border-slate-200 dark:border-slate-700"
                    style={`background:${groupColors[group.key]};`}
                  ></span>
                {/if}
                <span class="font-medium text-slate-700 dark:text-slate-200">{group.label}</span>
              </div>
              <span class="text-xs text-slate-400 dark:text-slate-500">
                {group.count.toLocaleString()} sample{group.count === 1 ? "" : "s"}
              </span>
            </div>
            {#if Number.isFinite(group.distance)}
              <div class="mt-1 text-xs text-slate-400 dark:text-slate-500">
                Nearest distance: {group.distance.toFixed(5)}
              </div>
            {/if}
          </button>
          <hr class="border-slate-300 dark:border-slate-600" />
        {/each}
      {/if}
    {:else}
      {#each visibleItems as item, index (item.id)}
        {@const isSelected = selectionMode && selectedItemId != null && item.id === selectedItemId}
        <button
          class="m-1 p-2 text-left rounded-md hover:outline outline-slate-500{isSelected ? ' ring-2 ring-emerald-500 bg-emerald-50 dark:bg-emerald-900/30' : ''}"
          onclick={() => {
            onClick?.(item);
          }}
        >
          <div class="flex items-center gap-2 pb-1">
            {#if item.distance != null && Number.isFinite(item.distance)}
              <span class="px-2 flex gap-2 bg-slate-200 text-slate-500 dark:bg-slate-600 dark:text-slate-300 rounded-md text-sm">
                <div class="text-slate-400 dark:text-slate-400 font-medium">Distance</div>
                <div class="text-ellipsis whitespace-nowrap overflow-hidden max-w-72">
                  {item.distance.toFixed(5)}
                </div>
              </span>
            {/if}
            {#if selectionMode}
              <span
                role="button"
                tabindex="0"
                class="ml-auto flex-none px-2 py-0.5 rounded text-xs font-medium transition cursor-pointer select-none {isSelected ? 'bg-emerald-500 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-300 hover:bg-emerald-200 dark:hover:bg-emerald-800 hover:text-emerald-700 dark:hover:text-emerald-200'}"
                onclick={(e) => {
                  e.stopPropagation();
                  onSelectItem?.(item);
                }}
                onkeydown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    e.stopPropagation();
                    onSelectItem?.(item);
                  }
                }}
                title="Select as most similar"
              >
                {isSelected ? "Selected" : `Select #${index + 1}`}
              </span>
            {/if}
          </div>
          <div class="overflow-hidden text-ellipsis line-clamp-4 leading-5" use:markHighlight={highlight}>
            <TooltipContent values={item.fields} columnStyles={columnStyles ?? {}} />
          </div>
        </button>
        <hr class="border-slate-300 dark:border-slate-600" />
      {/each}
    {/if}
    {#if hasMore}
      <button
        class="m-3 mt-4 px-4 py-2 rounded-md border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none"
        disabled={loadingMore}
        onclick={handleLoadMore}
      >
        {loadingMore ? "Loading more..." : "Load more results"}
      </button>
    {/if}
  </div>
</div>
