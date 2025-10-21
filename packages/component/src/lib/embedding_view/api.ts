// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import { isWebGPUAvailable } from "../webgpu_renderer/utils.js";
export { EmbeddingView, type EmbeddingViewProps } from "./embedding_view_api.js";
export { EmbeddingViewMosaic, type EmbeddingViewMosaicProps } from "./embedding_view_mosaic_api.js";

declare global {
  interface Window {
    __embeddingAtlasMaxDensityCategories?: number;
  }
}

export function maxDensityModeCategories(): number {
  if (typeof window !== "undefined" && window.__embeddingAtlasMaxDensityCategories != null) {
    return window.__embeddingAtlasMaxDensityCategories;
  }
  // In WebGL2, we only support max 4 categories.
  // In WebGPU, technically we can support 256 categories, but it's limited by speed and memory usage.
  // 32 is chosen here so that the total memory usage of a 2048 x 2048 x categories x f16 buffer is 256MB.
  return isWebGPUAvailable() ? 32 : 4;
}

export function overrideMaxDensityModeCategories(limit: number) {
  if (typeof window === "undefined") {
    return;
  }
  window.__embeddingAtlasMaxDensityCategories = limit;
  try {
    window.dispatchEvent(new CustomEvent("embedding-atlas-density-limit-changed", { detail: limit }));
  } catch (error) {
    // If CustomEvent is unavailable (e.g., in non-browser environments), ignore.
  }
}
