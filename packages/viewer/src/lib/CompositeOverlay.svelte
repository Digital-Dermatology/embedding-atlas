<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";

  import SearchResultOverlay from "./SearchResultOverlay.svelte";
  import UploadedSamplesOverlay from "./UploadedSamplesOverlay.svelte";
  import type { UploadedSamplePoint } from "./types/uploaded_samples.js";
  import type { SearchResultItem } from "./search.js";

  interface Props {
    proxy: OverlayProxy;
    items: SearchResultItem[];
    highlightItem?: SearchResultItem | null;
    focusPoint?: { x: number; y: number } | null;
    groupMode?: boolean;
    groupColors?: Record<string, string> | null;
    uploadedPoints?: UploadedSamplePoint[];
    uploadedHighlightId?: string | null;
  }

  let {
    proxy,
    items,
    highlightItem = null,
    focusPoint = null,
    groupMode = false,
    groupColors = null,
    uploadedPoints = [],
    uploadedHighlightId = null,
  }: Props = $props();
</script>

<div class="relative w-full h-full">
  <SearchResultOverlay
    proxy={proxy}
    items={items}
    highlightItem={highlightItem}
    focusPoint={focusPoint}
    groupMode={groupMode}
    groupColors={groupColors}
  />
  {#if uploadedPoints?.length}
    <UploadedSamplesOverlay proxy={proxy} points={uploadedPoints} highlightId={uploadedHighlightId} />
  {/if}
</div>
