<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";
  import type { SearchResultItem } from "./search.js";

  interface Props {
    items: SearchResultItem[];
    highlightItem?: SearchResultItem | null;
    focusPoint?: { x: number; y: number } | null;
    proxy: OverlayProxy;
  }

  let { items, highlightItem, focusPoint, proxy }: Props = $props();

  function starPoints(cx: number, cy: number, outerRadius: number, innerRadius: number): string {
    let points: string[] = [];
    for (let i = 0; i < 10; i++) {
      const angle = (Math.PI / 5) * i - Math.PI / 2;
      const radius = i % 2 === 0 ? outerRadius : innerRadius;
      const x = cx + Math.cos(angle) * radius;
      const y = cy + Math.sin(angle) * radius;
      points.push(`${x},${y}`);
    }
    return points.join(" ");
  }
</script>

<svg width={proxy.width} height={proxy.height}>
  <g>
    {#each items as item}
      {#if item.x != null && item.y != null}
        {@const loc = proxy.location(item.x, item.y)}
        {@const isHighlight = item.id == highlightItem?.id}
        {#if isHighlight}
          <line x1={loc.x - 20} x2={loc.x - 10} y1={loc.y} y2={loc.y} class="stroke-orange-500" />
          <line x1={loc.x + 20} x2={loc.x + 10} y1={loc.y} y2={loc.y} class="stroke-orange-500" />
          <line x1={loc.x} x2={loc.x} y1={loc.y - 20} y2={loc.y - 10} class="stroke-orange-500" />
          <line x1={loc.x} x2={loc.x} y1={loc.y + 20} y2={loc.y + 10} class="stroke-orange-500" />
        {/if}
        <circle cx={loc.x} cy={loc.y} r={4} class="fill-orange-500 stroke-orange-700 stroke-2" />
      {/if}
    {/each}
    {#if focusPoint && Number.isFinite(focusPoint.x) && Number.isFinite(focusPoint.y)}
      {@const loc = proxy.location(focusPoint.x, focusPoint.y)}
      <polygon
        points={starPoints(loc.x, loc.y, 10, 4)}
        class="fill-amber-300 stroke-amber-600 stroke-2"
        opacity="0.95"
      />
      <circle cx={loc.x} cy={loc.y} r={3} class="fill-amber-600" />
    {/if}
  </g>
</svg>
