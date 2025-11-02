<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";
  import type { SearchResultItem } from "./search.js";

  interface Props {
    items: SearchResultItem[];
    highlightItem?: SearchResultItem | null;
    focusPoint?: { x: number; y: number } | null;
    proxy: OverlayProxy;
    groupMode?: boolean;
    groupColors?: Record<string, string> | null;
  }

  let {
    items,
    highlightItem,
    focusPoint,
    proxy,
    groupMode = false,
    groupColors = null,
  }: Props = $props();

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

  const DEFAULT_FILL = "#f97316";
  const DEFAULT_STROKE = "#c2410c";

  function resolveItemColor(item: SearchResultItem): { fill: string; stroke: string } {
    if (groupMode && item?.groupKey != null && groupColors != null) {
      const fillColor = groupColors[item.groupKey];
      if (typeof fillColor === "string" && fillColor.trim() !== "") {
        const sanitized = fillColor.trim();
        return { fill: sanitized, stroke: sanitized };
      }
    }
    return { fill: DEFAULT_FILL, stroke: DEFAULT_STROKE };
  }
</script>

<svg width={proxy.width} height={proxy.height}>
  <g>
    {#each items as item}
      {#if item.x != null && item.y != null}
        {@const loc = proxy.location(item.x, item.y)}
        {@const isHighlight = item.id == highlightItem?.id}
        {@const colorSpec = resolveItemColor(item)}
        {#if isHighlight}
          <line x1={loc.x - 20} x2={loc.x - 10} y1={loc.y} y2={loc.y} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x + 20} x2={loc.x + 10} y1={loc.y} y2={loc.y} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x} x2={loc.x} y1={loc.y - 20} y2={loc.y - 10} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x} x2={loc.x} y1={loc.y + 20} y2={loc.y + 10} stroke={colorSpec.stroke} stroke-width="2" />
        {/if}
        <circle cx={loc.x} cy={loc.y} r={4} fill={colorSpec.fill} stroke={colorSpec.stroke} stroke-width={isHighlight ? 2.5 : 2} opacity={isHighlight ? 1 : 0.92} />
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
