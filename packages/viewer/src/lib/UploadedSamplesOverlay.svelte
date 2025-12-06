<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import type { OverlayProxy } from "@embedding-atlas/component";
  import type { UploadedSamplePoint } from "./types/uploaded_samples.js";

  interface Props {
    proxy: OverlayProxy;
    points: UploadedSamplePoint[];
    highlightId?: string | null;
  }

  function starPoints(cx: number, cy: number, outerRadius: number, innerRadius: number): string {
    let pts: string[] = [];
    for (let i = 0; i < 10; i++) {
      const angle = (Math.PI / 5) * i - Math.PI / 2;
      const radius = i % 2 === 0 ? outerRadius : innerRadius;
      const x = cx + Math.cos(angle) * radius;
      const y = cy + Math.sin(angle) * radius;
      pts.push(`${x},${y}`);
    }
    return pts.join(" ");
  }

  let { proxy, points, highlightId = null }: Props = $props();
</script>

<svg width={proxy.width} height={proxy.height} class="pointer-events-none">
  <g>
    {#each points as point (point.id)}
      {#if Number.isFinite(point.x) && Number.isFinite(point.y)}
        {@const loc = proxy.location(point.x, point.y)}
        {@const isHighlight = highlightId === point.id}
        <polygon
          points={starPoints(loc.x, loc.y, isHighlight ? 10 : 8, isHighlight ? 4 : 3)}
          class="fill-amber-300 stroke-amber-600"
          stroke-width={isHighlight ? 2.8 : 2.2}
          opacity={isHighlight ? 0.95 : 0.88}
        />
        <circle cx={loc.x} cy={loc.y} r={isHighlight ? 3.6 : 3} class="fill-amber-600" opacity={isHighlight ? 0.96 : 0.9} />
      {/if}
    {/each}
  </g>
</svg>
