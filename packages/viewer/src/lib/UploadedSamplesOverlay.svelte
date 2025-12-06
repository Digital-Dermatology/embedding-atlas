<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";

  export type UploadedSamplePoint = {
    id: string;
    label?: string | null;
    x: number;
    y: number;
    previewUrl?: string | null;
  };

  interface Props {
    proxy: OverlayProxy;
    points: UploadedSamplePoint[];
    highlightId?: string | null;
  }

  let { proxy, points, highlightId = null }: Props = $props();
</script>

<svg width={proxy.width} height={proxy.height} class="pointer-events-none">
  <g>
    {#each points as point (point.id)}
      {#if Number.isFinite(point.x) && Number.isFinite(point.y)}
        {@const loc = proxy.location(point.x, point.y)}
        {@const isHighlight = highlightId === point.id}
        <circle
          cx={loc.x}
          cy={loc.y}
          r={isHighlight ? 6.5 : 5}
          fill="#0ea5e9"
          stroke="#0284c7"
          stroke-width={isHighlight ? 3 : 2}
          opacity={isHighlight ? 0.95 : 0.9}
        />
        <circle cx={loc.x} cy={loc.y} r={isHighlight ? 3.6 : 3} fill="#38bdf8" opacity={isHighlight ? 0.96 : 0.85} />
      {/if}
    {/each}
  </g>
</svg>
