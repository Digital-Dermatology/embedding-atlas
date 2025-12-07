<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";
  import { color as d3color } from "d3-color";
  import type { UploadedSamplePoint } from "./types/uploaded_samples.js";
  import type { SearchResultItem } from "./search.js";

  interface Props {
    items: SearchResultItem[];
    highlightItem?: SearchResultItem | null;
    focusPoint?: { x: number; y: number } | null;
    proxy: OverlayProxy;
    groupMode?: boolean;
    groupColors?: Record<string, string> | null;
    uploadedPoints?: UploadedSamplePoint[];
    uploadedHighlightId?: string | null;
  }

  let {
    items,
    highlightItem,
    focusPoint,
    proxy,
    groupMode = false,
    groupColors = null,
    uploadedPoints = [],
    uploadedHighlightId = null,
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
  const DEFAULT_CORE = "#fb923c";

  function deriveStrokeColor(base: string): string {
    const c = d3color(base);
    if (!c) {
      return base;
    }
    return c.darker(0.8).formatHex();
  }

  function deriveFillColor(base: string): string {
    const c = d3color(base);
    if (!c) {
      return base;
    }
    return c.brighter(0.8).formatHex();
  }

  function deriveCoreColor(base: string): string {
    const c = d3color(base);
    if (!c) {
      return base;
    }
    return c.brighter(1.4).formatHex();
  }

  function resolveItemColor(item: SearchResultItem): { fill: string; stroke: string } {
    if (groupMode && item?.groupKey != null && groupColors != null) {
      const fillColor = groupColors[item.groupKey];
      if (typeof fillColor === "string" && fillColor.trim() !== "") {
        const sanitized = fillColor.trim();
        return {
          fill: deriveFillColor(sanitized),
          stroke: deriveStrokeColor(sanitized),
        };
      }
    }
    return {
      fill: deriveFillColor(DEFAULT_FILL),
      stroke: deriveStrokeColor(DEFAULT_FILL),
    };
  }

  function resolveCoreColor(item: SearchResultItem): string {
    if (groupMode && item?.groupKey != null && groupColors != null) {
      const fillColor = groupColors[item.groupKey];
      if (typeof fillColor === "string" && fillColor.trim() !== "") {
        return deriveCoreColor(fillColor.trim());
      }
    }
    return deriveCoreColor(DEFAULT_CORE);
  }
</script>

<svg width={proxy.width} height={proxy.height}>
  <g>
    {#each items as item}
      {#if item.x != null && item.y != null}
        {@const loc = proxy.location(item.x, item.y)}
        {@const isHighlight = item.id == highlightItem?.id}
        {@const colorSpec = resolveItemColor(item)}
        {@const coreColor = resolveCoreColor(item)}
        {#if isHighlight}
          <line x1={loc.x - 20} x2={loc.x - 10} y1={loc.y} y2={loc.y} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x + 20} x2={loc.x + 10} y1={loc.y} y2={loc.y} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x} x2={loc.x} y1={loc.y - 20} y2={loc.y - 10} stroke={colorSpec.stroke} stroke-width="2" />
          <line x1={loc.x} x2={loc.x} y1={loc.y + 20} y2={loc.y + 10} stroke={colorSpec.stroke} stroke-width="2" />
        {/if}
        <circle cx={loc.x} cy={loc.y} r={4.4} fill={colorSpec.fill} stroke={colorSpec.stroke} stroke-width={isHighlight ? 3 : 2.2} opacity={isHighlight ? 0.96 : 0.9} />
        <circle cx={loc.x} cy={loc.y} r={2.8} fill={coreColor} opacity={isHighlight ? 0.95 : 0.85} />
      {/if}
    {/each}
    {#if uploadedPoints?.length}
      {#each uploadedPoints as point (point.id)}
        {#if Number.isFinite(point.x) && Number.isFinite(point.y)}
          {@const loc = proxy.location(point.x, point.y)}
          {@const isHighlight = uploadedHighlightId === point.id}
          <polygon
            points={starPoints(loc.x, loc.y, isHighlight ? 10 : 8, isHighlight ? 4 : 3)}
            class="fill-amber-300 stroke-amber-600"
            stroke-width={isHighlight ? 2.8 : 2.2}
            opacity={isHighlight ? 0.95 : 0.88}
          />
          <circle
            cx={loc.x}
            cy={loc.y}
            r={isHighlight ? 3.6 : 3}
            class="fill-amber-600"
            opacity={isHighlight ? 0.96 : 0.9}
          />
        {/if}
      {/each}
    {/if}
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
