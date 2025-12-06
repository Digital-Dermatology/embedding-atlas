// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import type { DataPoint, OverlayProxy } from "@embedding-atlas/component";
import type { Component } from "svelte";
import { createClassComponent } from "svelte/legacy";

import CompositeOverlay from "./CompositeOverlay.svelte";
import SearchResultOverlay from "./SearchResultOverlay.svelte";
import Tooltip from "./Tooltip.svelte";

import type { ColumnStyle } from "./renderers/index.js";
import type { SearchResultItem } from "./search.js";
import type { UploadedSamplePoint } from "./types/uploaded_samples.js";

function createCustomComponentClass<Props extends {}>(Component: Component<Props>): any {
  return class {
    private component: any;

    constructor(target: HTMLDivElement, props: Props) {
      this.component = createClassComponent({ component: Component, target: target, props: props });
    }

    update(props: Partial<Props>) {
      this.component.$set(props);
    }

    destroy() {
      this.component.$destroy();
    }
  };
}

export const CustomTooltip = createCustomComponentClass<{
  tooltip: DataPoint;
  darkMode: boolean;
  columnStyles?: Record<string, ColumnStyle>;
  onNearestNeighborSearch?: (id: any) => void;
}>(Tooltip);

export const CustomOverlay = createCustomComponentClass<{
  proxy: OverlayProxy;
  items: SearchResultItem[];
  highlightItem?: SearchResultItem | null;
  focusPoint?: { x: number; y: number } | null;
  groupMode?: boolean;
  groupColors?: Record<string, string> | null;
}>(SearchResultOverlay);

export const CombinedOverlay = createCustomComponentClass<{
  proxy: OverlayProxy;
  items: SearchResultItem[];
  highlightItem?: SearchResultItem | null;
  focusPoint?: { x: number; y: number } | null;
  groupMode?: boolean;
  groupColors?: Record<string, string> | null;
  uploadedPoints?: UploadedSamplePoint[];
  uploadedHighlightId?: string | null;
}>(CompositeOverlay);
