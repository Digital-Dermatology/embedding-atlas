<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import * as SQL from "@uwdata/mosaic-sql";
  import * as vg from "@uwdata/vgplot";
  import { onDestroy, onMount } from "svelte";
  import { slide } from "svelte/transition";

  import { maxDensityModeCategories } from "@embedding-atlas/component";
  import type { CustomCell } from "@embedding-atlas/table";
  import { Table } from "@embedding-atlas/table/svelte";

  import ColumnStylePicker from "./ColumnStylePicker.svelte";
  import EmbeddingView from "./EmbeddingView.svelte";
  import PlotList from "./PlotList.svelte";
  import FilteredCount from "./plots/FilteredCount.svelte";
  import SearchResultList from "./SearchResultList.svelte";
  import ClinicalFeedbackForm from "./ClinicalFeedbackForm.svelte";
  import Spinner from "./Spinner.svelte";
  import ActionButton from "./widgets/ActionButton.svelte";
  import Button from "./widgets/Button.svelte";
  import DatasetUploadWidget from "./widgets/DatasetUploadWidget.svelte";
  import ImageSearchWidget from "./widgets/ImageSearchWidget.svelte";
  import Input from "./widgets/Input.svelte";
  import PopupButton from "./widgets/PopupButton.svelte";
  import Select from "./widgets/Select.svelte";
  import SearchFilters from "./widgets/SearchFilters.svelte";
  import Slider from "./widgets/Slider.svelte";
  import ToggleButton from "./widgets/ToggleButton.svelte";

  import {
    IconDarkMode,
    IconChart,
    IconDownload,
    IconEmbeddingView,
    IconExport,
    IconLightMode,
    IconSearch,
    IconSettings,
    IconTable,
  } from "./icons.js";

  import type { EmbeddingAtlasProps, EmbeddingAtlasState } from "./api.js";
  import { EMBEDDING_ATLAS_VERSION } from "./constants.js";
  import { Context } from "./contexts.js";
  import { CustomOverlay, CustomTooltip } from "./custom_components.js";
  import { makeDarkModeStore } from "./dark_mode_store.js";
  import { predicateToString, TableInfo, type ColumnDesc, type EmbeddingLegend } from "./database_utils.js";
  import { setImageAssets } from "./image_utils.js";
  import { defaultOrdinalColors } from "./colors.js";
  import type { Plot } from "./plots/plot.js";
  import { PlotStateStoreManager } from "./plots/plot_state_store.js";
  import { getRenderer, type ColumnStyle } from "./renderers/index.js";
  import { querySearchResultItems, resolveSearcher, type SearchResultItem } from "./search.js";
import type { UploadedSamplePoint } from "./types/uploaded_samples.js";
  import { tableTheme } from "./table_theme.js";
  import { debounce, startDrag } from "./utils.js";
  import skinmapLogo from "../assets/atlas.png";

const searchLimit = 500;
const searchPageSize = 50;

type UploadSearchFilter =
  | { column: string; type: "string" | "string[]"; values: string[] }
  | { column: string; type: "number"; min: number | null; max: number | null };

interface UploadSearchResultDetail {
  neighbors: { id: any; distance?: number }[];
  previewUrl: string | null;
  filters: UploadSearchFilter[];
  setStatus?: (value: string) => void;
  refetch?: (options?: { maxK?: number }) => Promise<boolean>;
  queryPoint?: { x: number; y: number } | null;
  topK?: number;
}

  let densityCategoryLimit: number = $state(Math.min(20, maxDensityModeCategories()));

  const animationDuration = 300;

  let {
    coordinator,
    data,
    initialState,
    activeRoute = null,
    routeTabs = null,
    searcher: specifiedSearcher,
    searchColumns = null,
    embeddingViewConfig = null,
    embeddingViewLabels = null,
    colorScheme,
    tableCellRenderers,
    onExportApplication,
    onExportSelection,
    onStateChange,
    cache,
    assets = null,
    uploadSearch = null,
  }: EmbeddingAtlasProps = $props();

  const { darkMode, userDarkMode } = makeDarkModeStore();

  Context.coordinator = coordinator;
  Context.darkMode = darkMode;

  setImageAssets(assets?.images ?? null);

  const defaultUploadConfig: NonNullable<EmbeddingAtlasProps["uploadSearch"]> = {
    enabled: true,
    endpoint: "/data/upload-neighbors",
    batchEndpoint: "/data/upload-embeddings",
  };
  let uploadSearchConfig = $derived(uploadSearch ?? defaultUploadConfig);
  let uploadSearchEndpoint = $derived(uploadSearchConfig?.endpoint ?? defaultUploadConfig.endpoint);
  let uploadEmbeddingEndpoint = $derived(uploadSearchConfig?.batchEndpoint ?? defaultUploadConfig.batchEndpoint);
  let uploadSearchEnabledFlag = $derived(
    uploadSearchConfig && typeof uploadSearchConfig === "object" && "enabled" in uploadSearchConfig
      ? (uploadSearchConfig as { enabled?: boolean }).enabled
      : undefined,
  );
  let uploadSearchAvailable = $derived(uploadSearchEnabledFlag !== false);
  let uploadSearchWarning = $derived(uploadSearchEnabledFlag === false);
  let isClinicalRoute = $derived((activeRoute ?? "").toLowerCase() === "clinical");
  let showUploadSearchWidget = $derived(Boolean(uploadSearchConfig?.endpoint ?? defaultUploadConfig.endpoint));
  let showBatchUploadWidget = $derived(Boolean(uploadEmbeddingEndpoint) && !isClinicalRoute);
  let clinicalSearchTab = $state<"image" | "text">("image");
  let normalizedActiveRoute = $derived((activeRoute ?? "").toLowerCase());

  function isRouteActive(route: string | null) {
    return (route ?? "").toLowerCase() === normalizedActiveRoute;
  }

  onMount(() => {
    if (typeof window === "undefined") {
      return;
    }
    const listener = (event: Event) => {
      let detail = (event as CustomEvent<number>).detail;
      let limit = Math.min(20, detail ?? maxDensityModeCategories());
      if (densityCategoryLimit !== limit) {
        densityCategoryLimit = limit;
        setCategoryColumn(selectedCategoryColumn);
      }
    };
    window.addEventListener("embedding-atlas-density-limit-changed", listener);
    return () => {
      window.removeEventListener("embedding-atlas-density-limit-changed", listener);
    };
  });
  $effect(() => {
    setImageAssets(assets?.images ?? null);
  });
  onDestroy(() => {
    setImageAssets(null);
  });

  $effect(() => {
    switch (colorScheme) {
      case "light":
        $userDarkMode = false;
        break;
      case "dark":
        $userDarkMode = true;
        break;
      case null:
        $userDarkMode = null;
        break;
    }
  });

  let initialized = $state(false);

  // View mode
  let showEmbedding: boolean = $state(data.projection != null);
  let showTable: boolean = $state(!(data.projection != null));
  let showNNPanel: boolean = $state(true);
  let showWidgetPanel: boolean = $state(false);

  let tableHeight: number = $state(320);
  let nnPanelWidth: number = $state(400);
  let widgetPanelWidth: number = $state(360);

  type SidePanelKind = "nn" | "widgets" | null;
  let showMainView = $derived(showEmbedding || showTable);
  let anyPanelVisible = $derived(showNNPanel || showWidgetPanel);
  let firstPanel = $derived<SidePanelKind>(showNNPanel ? "nn" : showWidgetPanel ? "widgets" : null);
  let widgetFullWidth = $derived(!showEmbedding && !showTable && !showNNPanel);
  let nnPanelLayoutClasses = $derived(
    showMainView ? "flex-col overflow-y-auto" : "flex-col xl:flex-row xl:overflow-hidden",
  );
  let nnPanelSidebarClasses = $derived(
    showMainView ? "w-full" : "w-full xl:w-1/3 xl:min-w-[18rem] xl:pr-2 xl:overflow-y-auto",
  );
  let nnPanelFullWidth = $derived(showNNPanel && !showMainView && !showWidgetPanel);
  let widgetPanelFullWidth = $derived(showWidgetPanel && !showMainView && !showNNPanel);

  const tableInfo = new TableInfo(coordinator, data.table);

  let embeddingViewMode: "points" | "density" = $state("points");
  let minimumDensityExpFactor: number = $state(0);
  let defaultViewportScale = $derived(
    data.projection != null ? tableInfo.defaultViewportScale(data.projection.x, data.projection.y) : null,
  );

  let exportFormat: "json" | "jsonl" | "csv" | "parquet" = $state("parquet");

  const crossFilter = vg.Selection.crossfilter();

  function currentPredicate(): string | null {
    return predicateToString(crossFilter.predicate(null));
  }

  let columns: ColumnDesc[] = $state.raw([]);
  let columnsReadyResolve: (() => void) | null = null;
  const columnsReady = new Promise<void>((resolve) => {
    columnsReadyResolve = resolve;
  });
  let columnsLoaded = false;

  async function waitForColumns() {
    if (columnsLoaded) {
      return;
    }
    await columnsReady;
  }
  let plots: Plot[] = $state.raw([]);
  let plotStateStores = new PlotStateStoreManager();

  let embeddingView: EmbeddingView | null = $state.raw(null);

  // let selection: any[] | null = $state.raw([]);
  let additionalFields = $derived(makeAdditionalFields(columns));


  // Column styles
  let columnStyles: Record<string, ColumnStyle> = $state.raw({});

  export function resolveCustomCellRenderers(
    columns: ColumnDesc[],
    columnStyles: Record<string, ColumnStyle>,
    tableCellRenderers: Record<string, string | CustomCell> | null | undefined,
  ) {
    let result: Record<string, any> = {};
    for (let column of columns) {
      if (tableCellRenderers?.[column.name] != null) {
        result[column.name] = getRenderer(tableCellRenderers[column.name]);
      }
      if (columnStyles[column.name]?.renderer != null) {
        result[column.name] = getRenderer(columnStyles[column.name]?.renderer);
      }
    }
    return result;
  }

  function resolveColumnStyles(
    columns: ColumnDesc[],
    styles: Record<string, ColumnStyle>,
  ): Record<string, ColumnStyle> {
    let result: Record<string, ColumnStyle> = {};
    for (let column of columns) {
      let style = styles[column.name];
      if (style == null) {
        // Default display style
        style = { display: data.text == column.name ? "full" : "badge" };
      }
      result[column.name] = style;
    }
    return result;
  }

  let resolvedCustomCellRenderers = $derived(resolveCustomCellRenderers(columns, columnStyles, tableCellRenderers));
  let resolvedColumnStyles = $derived(resolveColumnStyles(columns, columnStyles));

  // Search

  // Use a default searcher FullTextSearcher when searcher is not specified
  let searcher = $derived(
    resolveSearcher({
      coordinator,
      table: data.table,
      idColumn: data.id,
      textColumn: data.text,
      neighborsColumn: data.neighbors,
      vectorNeighborsEndpoint: data.vectorNeighborsEndpoint ?? null,
      textSearchEndpoint: data.textSearchEndpoint ?? null,
      searcher: specifiedSearcher,
      textColumns: searchColumns,
    }),
  );

  let allowFullTextSearch = $derived(searcher.fullTextSearch != null);
  let allowVectorSearch = $derived(searcher.vectorSearch != null);
  let allowNearestNeighborSearch = $derived(searcher.nearestNeighbors != null);
  let searchMode = $state<"full-text" | "vector" | "neighbors">("vector");
  let searchModeOptions = $derived([
    ...(allowVectorSearch ? [{ label: "Vector NN", value: "vector" }] : []),
    ...(allowFullTextSearch ? [{ label: "Full Text", value: "full-text" }] : []),
    ...(allowNearestNeighborSearch ? [{ label: "Neighbors", value: "neighbors" }] : []),
  ]);
  $effect(() => {
    const availableModes = searchModeOptions.map((option) => option.value);
    if (availableModes.length === 0) {
      return;
    }
    if (!availableModes.includes(searchMode)) {
      searchMode = availableModes[0] as typeof searchMode;
    }
  });

  let searchQuery = $state("");
  let searcherStatus = $state("");
  let searchResultVisible = $state(false);
  type SearchResultState = {
    label: string;
    highlight: string;
    items: SearchResultItem[];
  };
  let searchResult: SearchResultState | null = $state(null);
  let searchResultHighlight = $state<SearchResultItem | null>(null);
  let searchResultVisibleCount: number = $state(searchPageSize);
  let searchResultLoadingMore: boolean = $state(false);
  let searchResultFetchLimit: number = $state(searchPageSize);
  let searchResultBackendHasMore: boolean = $state(false);
  let lastSearchArgs = $state.raw<{ query: any; mode: "full-text" | "vector" | "neighbors" } | null>(null);
  let searchRequestId = 0;
  let textSearchFilters: UploadSearchFilter[] = $state.raw([]);
  type ClinicalFeedbackContext =
    | {
        mode: "neighbors";
        signature: string;
        query: any;
        queryDisplay: string;
        uploadSummary: null;
      }
    | {
        mode: "upload";
        signature: string;
        query: string;
        queryDisplay: string;
        uploadSummary: {
          previewUrl: string | null;
          filters: UploadSearchFilter[];
          topK: number;
        };
      };

  function generateSurveySignature(mode: string, identifier: string): string {
    let unique: string;
    try {
      unique = typeof crypto !== "undefined" && typeof (crypto as any).randomUUID === "function"
        ? (crypto as any).randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    } catch {
      unique = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }
    return `${mode}:${identifier}:${unique}`;
  }

  let clinicalFeedbackContext = $state.raw<ClinicalFeedbackContext | null>(null);

  function countSearchResultItems(result: SearchResultState | null): number {
    return result ? result.items.length : 0;
  }
  let clinicalSearchResultCount = $derived(countSearchResultItems(searchResult));
  let shouldShowClinicalFeedback = $derived(
    Boolean(isClinicalRoute && searchResultVisible && clinicalFeedbackContext != null && clinicalSearchResultCount > 0),
  );
  let clinicalSurveyKey = $derived(shouldShowClinicalFeedback ? clinicalFeedbackContext?.signature ?? "" : "");
  let pendingUploadSurveySignature = $state<string | null>(null);
  const clinicalUploadBlockMessage = "Complete the clinical survey before uploading another case.";
  let clinicalUploadBlocked = $derived(Boolean(isClinicalRoute && pendingUploadSurveySignature != null));

  function handleClinicalSurveySubmitted(event: CustomEvent<{ signature: string | null }>) {
    const signature = event.detail?.signature ?? clinicalFeedbackContext?.signature ?? null;
    if (signature != null && signature === pendingUploadSurveySignature) {
      pendingUploadSurveySignature = null;
    }
  }
  function handleTextFiltersChange(event: { filters: UploadSearchFilter[] }) {
    textSearchFilters = event?.filters ?? [];
  }
  let uploadSearchDetail = $state.raw<UploadSearchResultDetail | null>(null);
  let uploadSearchNeighborCount: number = $state(0);
  let uploadSearchHasMore: boolean = $state(false);
  let uploadFocusPoint: { x: number; y: number } | null = $state(null);
  type BatchUploadError = { label: string; message: string };
  let uploadedSamples: UploadedSamplePoint[] = $state.raw([]);
  let uploadedSamplesHighlightId: string | null = $state(null);

  const NEIGHBOR_GROUP_COLUMN = "condition";
  const UNKNOWN_CONDITION_LABEL = "Unknown condition";

  type NeighborGroupSummary = {
    key: string;
    label: string;
    representative: SearchResultItem;
    items: SearchResultItem[];
    count: number;
    distance: number;
  };

  function normalizeGroupLabel(value: any): string {
    if (value == null) {
      return UNKNOWN_CONDITION_LABEL;
    }
    const text = typeof value === "string" ? value : String(value);
    const trimmed = text.trim();
    return trimmed === "" ? UNKNOWN_CONDITION_LABEL : trimmed;
  }

  function computeNeighborGroupKey(item: SearchResultItem): string {
    if (typeof item.groupKey === "string") {
      const trimmed = item.groupKey.trim();
      if (trimmed !== "") {
        return trimmed;
      }
    }
    return normalizeGroupLabel(item.fields?.[NEIGHBOR_GROUP_COLUMN]);
  }

  function augmentSearchResultsWithGroup(items: SearchResultItem[]): SearchResultItem[] {
    return items.map((item) => {
      const key = computeNeighborGroupKey(item);
      if (item.groupKey === key) {
        return item;
      }
      return {
        ...item,
        groupKey: key,
      };
    });
  }

  function normalizedDistance(distance?: number): number {
    return typeof distance === "number" && Number.isFinite(distance) ? distance : Number.POSITIVE_INFINITY;
  }

  let groupNeighborsByCondition: boolean = $state(false);
  let activeNeighborGroup: string | null = $state(null);

  function buildNeighborGroupSummaries(): NeighborGroupSummary[] {
    if (searchResult?.items == null || searchResult.items.length === 0) {
      return [];
    }
    const groups = new Map<string, NeighborGroupSummary>();
    for (const item of searchResult.items) {
      const key = computeNeighborGroupKey(item);
      const distance = normalizedDistance(item.distance);
      const existing = groups.get(key);
      if (existing == null) {
        groups.set(key, {
          key,
          label: key,
          representative: item,
          items: [item],
          count: 1,
          distance,
        });
      } else {
        existing.items.push(item);
        existing.count += 1;
        if (distance < existing.distance) {
          existing.representative = item;
          existing.distance = distance;
        }
      }
    }
    return Array.from(groups.values()).sort((a, b) => {
      const diff = a.distance - b.distance;
      if (Number.isFinite(diff) && diff !== 0) {
        return diff;
      }
      if (!Number.isFinite(a.distance) && Number.isFinite(b.distance)) {
        return 1;
      }
      if (Number.isFinite(a.distance) && !Number.isFinite(b.distance)) {
        return -1;
      }
      return a.label.localeCompare(b.label);
    });
  }

  let neighborGroupSummaries = $derived(buildNeighborGroupSummaries());

  function resolveActiveNeighborGroupLabel(): string | null {
    if (activeNeighborGroup == null) {
      return null;
    }
    const match = neighborGroupSummaries.find((group) => group.key === activeNeighborGroup);
    return match?.label ?? null;
  }

  let activeNeighborGroupLabel = $derived(resolveActiveNeighborGroupLabel());

  function buildNeighborGroupColors(): Record<string, string> | null {
    if (!groupNeighborsByCondition || activeNeighborGroup != null) {
      return null;
    }
    if (neighborGroupSummaries.length === 0) {
      return null;
    }
    const palette = defaultOrdinalColors(Math.max(1, neighborGroupSummaries.length));
    const colorMap: Record<string, string> = {};
    neighborGroupSummaries.forEach((group, index) => {
      colorMap[group.key] = palette[index % palette.length];
    });
    return colorMap;
  }

  let neighborGroupColors = $derived(buildNeighborGroupColors());

  function buildSearchResultDisplayItems(): SearchResultItem[] {
    if (searchResult?.items == null) {
      return [];
    }
    if (groupNeighborsByCondition && activeNeighborGroup != null) {
      return searchResult.items.filter((item) => computeNeighborGroupKey(item) === activeNeighborGroup);
    }
    return searchResult.items;
  }

  let searchResultDisplayItems = $derived(buildSearchResultDisplayItems());

  function buildSearchResultDisplayLabel(): string {
    if (searchResult == null) {
      return "";
    }
    if (!groupNeighborsByCondition) {
      return searchResult.label;
    }
    if (activeNeighborGroup != null) {
      return `${searchResult.label} • ${activeNeighborGroupLabel ?? activeNeighborGroup}`;
    }
    return `${searchResult.label} (grouped by condition)`;
  }

  let searchResultDisplayLabel = $derived(buildSearchResultDisplayLabel());

  $effect(() => {
    if (!groupNeighborsByCondition || searchResult == null) {
      activeNeighborGroup = null;
      return;
    }
    if (activeNeighborGroup != null) {
      const exists = neighborGroupSummaries.some((group) => group.key === activeNeighborGroup);
      if (!exists) {
        activeNeighborGroup = null;
      }
    }
  });

  function updateSearchResultVisibleCount(totalCount: number, preserveIncrement: boolean) {
    if (totalCount <= 0) {
      searchResultVisibleCount = 0;
    } else if (preserveIncrement) {
      let nextTarget = searchResultVisibleCount + searchPageSize;
      searchResultVisibleCount = Math.min(totalCount, nextTarget);
    } else {
      searchResultVisibleCount = Math.min(searchPageSize, totalCount);
    }
  }

  function shouldShowLoadMore(): boolean {
    if (searchResult == null) {
      return false;
    }
    if (searchResultLoadingMore) {
      return true;
    }
    let total = searchResult.items.length;
    if (total === 0) {
      return false;
    }
    if (total > searchResultVisibleCount) {
      return true;
    }
    return uploadSearchHasMore || searchResultBackendHasMore;
  }

  async function doSearch(query: any, mode: string, options?: { limit?: number; preserveIncrement?: boolean }) {
    if (searcher == null || searchModeOptions.length == 0) {
      clearSearch();
      return;
    }

    const requestId = ++searchRequestId;
    searchResultVisible = true;
    searcherStatus = "Searching...";
    uploadSearchDetail = null;
    uploadSearchHasMore = false;
    searchResultBackendHasMore = false;

    await waitForColumns();
    if (requestId !== searchRequestId) {
      return;
    }

    const availableModes = searchModeOptions.map((x) => x.value);
    if (availableModes.length === 0) {
      clearSearch();
      return;
    }
    let resolvedMode: "full-text" | "vector" | "neighbors" =
      availableModes.includes(mode as any)
        ? (mode as "full-text" | "vector" | "neighbors")
        : (availableModes[0] as "full-text" | "vector" | "neighbors");

    let predicate = currentPredicate();
    let searcherResult: { id: any }[] = [];
    let highlight: string = "";
    let label = query != null ? query.toString() : "";
    let effectiveQuery = query;
    const displayLimit = Math.min(searchLimit, options?.limit ?? searchPageSize);
    const fetchLimit =
      resolvedMode === "full-text" && searcher.fullTextSearch != null
        ? Math.min(searchLimit, options?.limit ?? searchLimit)
        : displayLimit;

    if (resolvedMode == "full-text" && searcher.fullTextSearch != null) {
      effectiveQuery = String(query).trim();
      searcherResult = await searcher.fullTextSearch(effectiveQuery, {
        limit: fetchLimit,
        predicate: predicate,
        onStatus: (status: string) => {
          searcherStatus = status;
        },
      });
      highlight = effectiveQuery;
    } else if (resolvedMode == "vector" && searcher.vectorSearch != null) {
      effectiveQuery = String(query).trim();
      searcherResult = await searcher.vectorSearch(effectiveQuery, {
        limit: fetchLimit,
        predicate: predicate,
        onStatus: (status: string) => {
          searcherStatus = status;
        },
      });
      highlight = "";
    } else if (resolvedMode == "neighbors" && searcher.nearestNeighbors != null) {
      label = "Neighbors of #" + effectiveQuery.toString();
      searcherResult = await searcher.nearestNeighbors(effectiveQuery, {
        limit: fetchLimit,
        predicate: predicate,
        onStatus: (status: string) => {
          searcherStatus = status;
        },
      });
    }
    if (requestId !== searchRequestId) {
      return;
    }

    const hasTextFilters = textSearchFilters.some(isFilterActive);
    let filteredSearcherResult = searcherResult;
    if (hasTextFilters) {
      searcherStatus = "Filtering...";
      try {
        const neighbors = searcherResult.map((item: any) => ({
          id: item?.id ?? item,
          distance: typeof item?.distance === "number" ? item.distance : undefined,
        }));
        const filtered = await filterNeighborsByMetadata(neighbors, textSearchFilters);
        filteredSearcherResult = filtered.map((neighbor) => ({
          id: neighbor.id,
          distance: neighbor.distance,
        }));
      } catch (error) {
        console.error("Failed to apply text search filters", error);
        filteredSearcherResult = searcherResult;
      }
    }
    if (requestId !== searchRequestId) {
      return;
    }

    let neighborAnchorPoint: { x: number; y: number } | null = null;
    if (resolvedMode === "neighbors") {
      neighborAnchorPoint = await resolveEmbeddingPoint(effectiveQuery);
    }
    if (requestId !== searchRequestId) {
      return;
    }

    // Apply predicate in case the searcher does not handle predicate.
    // And convert the search result ids to tuples.
    let result = await querySearchResultItems(
      coordinator,
      data.table,
      { id: data.id, x: data.projection?.x, y: data.projection?.y, text: data.text },
      additionalFields,
      predicate,
      filteredSearcherResult,
    );
    if (requestId !== searchRequestId) {
      return;
    }

    const augmented = augmentSearchResultsWithGroup(result);
    searcherStatus = "";
    searchResult = { label: label, highlight: highlight, items: augmented };
    searchResultFetchLimit = displayLimit;
    let searcherHasMore = (searcherResult as any)?.__hasMore === true;
    searchResultBackendHasMore = (searcherHasMore || searcherResult.length >= fetchLimit) && fetchLimit < searchLimit;
    updateSearchResultVisibleCount(augmented.length, options?.preserveIncrement === true);
    if (options?.preserveIncrement !== true) {
      searchResultLoadingMore = false;
    }
    uploadSearchNeighborCount = 0;
    lastSearchArgs = { query: effectiveQuery, mode: resolvedMode as "full-text" | "vector" | "neighbors" };
    if (resolvedMode === "neighbors" && augmented.length > 0) {
      clinicalFeedbackContext = {
        mode: "neighbors",
        signature: generateSurveySignature("neighbors", String(effectiveQuery ?? "")),
        query: effectiveQuery,
        queryDisplay: label,
        uploadSummary: null,
      };
    } else if (resolvedMode !== "neighbors" || augmented.length === 0) {
      clinicalFeedbackContext = null;
    }
    if (resolvedMode === "neighbors") {
      if (neighborAnchorPoint != null) {
        uploadFocusPoint = neighborAnchorPoint;
        if (options?.preserveIncrement !== true) {
          void animateEmbeddingViewToPoint(effectiveQuery, neighborAnchorPoint.x, neighborAnchorPoint.y);
        }
      } else {
        const fallbackAnchor = computeUploadFocusPoint(augmented);
        uploadFocusPoint = fallbackAnchor ?? null;
        if (fallbackAnchor != null && options?.preserveIncrement !== true) {
          void animateEmbeddingViewToPoint(undefined, fallbackAnchor.x, fallbackAnchor.y);
        }
      }
    } else {
      uploadFocusPoint = null;
    }
    if (groupNeighborsByCondition && activeNeighborGroup != null) {
      const stillPresent = augmented.some((item) => computeNeighborGroupKey(item) === activeNeighborGroup);
      if (!stillPresent) {
        activeNeighborGroup = null;
      }
    }
  }

const debouncedSearch = debounce(doSearch, 500);

function isFilterActive(filter: UploadSearchFilter): boolean {
  if (filter.type === "number") {
    return filter.min != null || filter.max != null;
  }
  return Array.isArray(filter.values) && filter.values.length > 0;
}

function normalizeToStringArray(value: any): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (item == null ? null : String(item)))
      .filter((item): item is string => item != null && item !== "");
  }
  if (value == null) {
    return [];
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item: any) => (item == null ? null : String(item)))
          .filter((item): item is string => item != null && item !== "");
      }
    } catch {
      // Fall through: treat as single value.
    }
    return value === "" ? [] : [value];
  }
  return [String(value)];
}

function matchesFilterValue(value: any, filter: UploadSearchFilter): boolean {
  if (filter.type === "number") {
    if (value == null || value === "") {
      return false;
    }
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) {
      return false;
    }
    if (filter.min != null && numeric < filter.min) {
      return false;
    }
    if (filter.max != null && numeric > filter.max) {
      return false;
    }
    return true;
  }

  if (!Array.isArray(filter.values) || filter.values.length === 0) {
    return true;
  }
  const candidates = normalizeToStringArray(value);
  if (candidates.length === 0) {
    return false;
  }
  return candidates.some((candidate) => filter.values.includes(candidate));
}

function computeUploadFocusPoint(items: SearchResultItem[]): { x: number; y: number } | null {
  const valid = items.filter(
    (item) =>
      typeof item.x === "number" && Number.isFinite(item.x) && typeof item.y === "number" && Number.isFinite(item.y),
  );
  if (valid.length === 0) {
    return null;
  }
  const EPS = 1e-6;
  let sumW = 0;
  let sumX = 0;
  let sumY = 0;
  for (const item of valid) {
    const distance = item.distance;
    const weight = distance != null && Number.isFinite(distance) ? 1 / Math.max(distance, EPS) : 1;
    sumW += weight;
    sumX += weight * (item.x as number);
    sumY += weight * (item.y as number);
  }
  if (sumW <= EPS) {
    return {
      x: valid.reduce((acc, item) => acc + (item.x as number), 0) / valid.length,
      y: valid.reduce((acc, item) => acc + (item.y as number), 0) / valid.length,
    };
  }
  return {
    x: sumX / sumW,
    y: sumY / sumW,
  };
}

async function resolveEmbeddingPoint(identifier: any): Promise<{ x: number; y: number } | null> {
  if (
    identifier == null ||
    data?.projection?.x == null ||
    data?.projection?.y == null ||
    data?.id == null ||
    data?.table == null
  ) {
    return null;
  }
  try {
    const result = await coordinator.query(`
      SELECT
        ${SQL.column(data.projection.x, data.table)} AS __x__,
        ${SQL.column(data.projection.y, data.table)} AS __y__
      FROM ${data.table}
      WHERE ${SQL.column(data.id, data.table)} = ${SQL.literal(identifier)}
      LIMIT 1
    `);
    const rows = Array.from(result) as Record<string, any>[];
    if (rows.length === 0) {
      return null;
    }
    const x = Number(rows[0].__x__);
    const y = Number(rows[0].__y__);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    return { x, y };
  } catch (error) {
    console.warn("Failed to resolve embedding point for anchor", error);
    return null;
  }
}

function toggleGroupByCondition(checked: boolean) {
  groupNeighborsByCondition = checked;
  if (!checked) {
    activeNeighborGroup = null;
    return;
  }
  searchResultHighlight = null;
}

function selectNeighborGroup(groupKey: string) {
  if (groupKey == null || groupKey === "") {
    return;
  }
  activeNeighborGroup = groupKey;
  searchResultHighlight = null;
  const items =
    searchResult?.items?.filter((item) => computeNeighborGroupKey(item) === groupKey) ?? ([] as SearchResultItem[]);
  if (items.length > 0) {
    const focus = computeUploadFocusPoint(items);
    if (focus != null) {
      void animateEmbeddingViewToPoint(undefined, focus.x, focus.y);
    }
  }
}

function clearNeighborGroupSelection() {
  activeNeighborGroup = null;
  searchResultHighlight = null;
  if (uploadFocusPoint != null) {
    void animateEmbeddingViewToPoint(undefined, uploadFocusPoint.x, uploadFocusPoint.y);
  }
}

async function filterNeighborsByMetadata(
  neighbors: { id: any; distance?: number }[],
  filters: UploadSearchFilter[],
): Promise<{ id: any; distance?: number }[]> {
  const activeFilters = filters.filter(isFilterActive);
  if (activeFilters.length === 0) {
    return neighbors;
  }
  if (!data?.id || !data?.table) {
    return neighbors;
  }

  const ids = Array.from(new Set(neighbors.map((neighbor) => neighbor.id).filter((id) => id != null)));
  if (ids.length === 0) {
    return [];
  }

  const selectSpec: Record<string, any> = {
    __neighbor_id__: SQL.column(data.id, data.table),
  };

  for (const filter of activeFilters) {
    const alias = `field_${filter.column}`;
    if (selectSpec[alias]) {
      continue;
    }
    if (filter.type === "string[]") {
      selectSpec[alias] = SQL.sql`CASE WHEN ${SQL.column(filter.column, data.table)} IS NULL THEN NULL ELSE list_transform(${SQL.column(filter.column, data.table)}, x -> CAST(x AS TEXT)) END`;
    } else {
      selectSpec[alias] = SQL.column(filter.column, data.table);
    }
  }

  const query = SQL.Query.from(data.table)
    .select(selectSpec)
    .where(
      SQL.isIn(
        SQL.column(data.id, data.table),
        ids.map((id) => SQL.literal(id)),
      ),
    );

  const result = await coordinator.query(query);
  const rows = Array.from(result) as Record<string, any>[];
  const valueById = new Map<any, Record<string, any>>();
  for (const row of rows) {
    valueById.set(row.__neighbor_id__, row);
  }

  return neighbors.filter((neighbor) => {
    const row = valueById.get(neighbor.id);
    if (!row) {
      return false;
    }
    return activeFilters.every((filter) => matchesFilterValue(row[`field_${filter.column}`], filter));
  });
}

function updateUploadSearchStatus(
  setStatus: ((value: string) => void) | undefined,
  neighbors: { id: any; distance?: number }[],
  filters: UploadSearchFilter[],
) {
  if (!setStatus) {
    return;
  }
  const hasFilters = filters.some(isFilterActive);
  if (neighbors.length === 0) {
    setStatus(hasFilters ? "No neighbors match the filters." : "No neighbors found.");
    return;
  }
  const distances = neighbors
    .map((neighbor) => neighbor.distance)
    .filter((distance): distance is number => typeof distance === "number" && Number.isFinite(distance));
  if (distances.length === 0) {
    setStatus("");
    return;
  }
  const avg = distances.reduce((acc, value) => acc + value, 0) / distances.length;
  setStatus(`Average distance: ${avg.toFixed(4)}`);
}

async function displayNeighborResults(
  label: string,
  neighbors: { id: any; distance?: number }[],
): Promise<SearchResultItem[]> {
  searchResultVisible = true;
  searchResultHighlight = null;
  if (neighbors.length === 0) {
    searchResult = { label, highlight: "", items: [] };
    searcherStatus = "";
    return [];
  }

  searcherStatus = "Fetching neighbors...";
  try {
    let predicate = currentPredicate();
    let result = await querySearchResultItems(
      coordinator,
      data.table,
      { id: data.id, x: data.projection?.x, y: data.projection?.y, text: data.text },
      additionalFields,
      predicate,
      neighbors,
    );
    const augmented = augmentSearchResultsWithGroup(result);
    searchResult = { label, highlight: "", items: augmented };
    updateSearchResultVisibleCount(augmented.length, searchResultLoadingMore);
    if (groupNeighborsByCondition && activeNeighborGroup != null) {
      const stillPresent = augmented.some((item) => computeNeighborGroupKey(item) === activeNeighborGroup);
      if (!stillPresent) {
        activeNeighborGroup = null;
      }
    }
    return augmented;
  } catch (error) {
    console.error("Failed to resolve neighbor results", error);
    searchResult = { label, highlight: "", items: [] };
    updateSearchResultVisibleCount(0, false);
    return [];
  } finally {
    searcherStatus = "";
  }
}

async function handleImageSearchResult(detail: UploadSearchResultDetail) {
  await waitForColumns();
  const payload = (detail as any)?.detail ? ((detail as any).detail as UploadSearchResultDetail) : detail;
  let neighbors = payload?.neighbors ?? [];
  const filters = payload?.filters ?? [];
  const setStatus = payload?.setStatus;
  const refetch = payload?.refetch;
  const queryPoint = payload?.queryPoint ?? null;
  const desiredTopK = payload?.topK ?? 50;

  searchResultBackendHasMore = false;
  lastSearchArgs = null;
  searchResultFetchLimit = searchPageSize;
  uploadSearchNeighborCount = neighbors.length;
  uploadSearchDetail = payload;
  uploadSearchHasMore = payload?.refetch != null && neighbors.length >= (payload?.topK ?? 0);

  let filteredNeighbors = neighbors;
  try {
    filteredNeighbors = await filterNeighborsByMetadata(neighbors, filters);
  } catch (error) {
    console.error("Failed to apply upload search filters", error);
    filteredNeighbors = neighbors;
  }

  const hasActiveFilters = filters.some(isFilterActive);
  if (hasActiveFilters && filteredNeighbors.length < desiredTopK && typeof refetch === "function") {
    uploadFocusPoint = null;
    const triggered = await refetch();
    if (triggered) {
      return;
    }
  }

  updateUploadSearchStatus(setStatus, filteredNeighbors, filters);
  const items = await displayNeighborResults("Uploaded image neighbors", filteredNeighbors);
  uploadSearchDetail =
    payload != null
      ? {
          ...payload,
          neighbors: filteredNeighbors,
        }
      : null;
  uploadSearchHasMore =
    uploadSearchDetail?.refetch != null && filteredNeighbors.length >= (uploadSearchDetail?.topK ?? 0);
  if (items.length > 0) {
    const signature = generateSurveySignature("upload", payload?.previewUrl ?? "uploaded-image");
    clinicalFeedbackContext = {
      mode: "upload",
      signature: signature,
      query: "uploaded-image",
      queryDisplay: "Uploaded image neighbors",
      uploadSummary: {
        previewUrl: payload?.previewUrl ?? null,
        filters: filters,
        topK: payload?.topK ?? desiredTopK,
      },
    };
    pendingUploadSurveySignature = signature;
  } else {
    clinicalFeedbackContext = null;
    pendingUploadSurveySignature = null;
  }
  if (queryPoint != null) {
    uploadFocusPoint = queryPoint;
    await animateEmbeddingViewToPoint(undefined, queryPoint.x, queryPoint.y);
  } else {
    const newFocusPoint = computeUploadFocusPoint(items);
    if (newFocusPoint != null) {
      uploadFocusPoint = newFocusPoint;
    } else if (!hasActiveFilters) {
      uploadFocusPoint = null;
    }
  }
  searchResultLoadingMore = false;
}

function computeUploadedSamplesFocus(points: UploadedSamplePoint[]): { x: number; y: number } | null {
  const valid = points.filter(
    (p) => p != null && Number.isFinite(p.x) && Number.isFinite(p.y),
  );
  if (valid.length === 0) {
    return null;
  }
  const total = valid.reduce(
    (acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }),
    { x: 0, y: 0 },
  );
  return {
    x: total.x / valid.length,
    y: total.y / valid.length,
  };
}

function clearUploadedSamples() {
  uploadedSamples = [];
  uploadedSamplesHighlightId = null;
}

async function handleDatasetEmbeddingResult(detail: { points?: UploadedSamplePoint[]; errors?: BatchUploadError[]; truncated?: boolean } | null) {
  const normalized = detail ?? {};
  const points = Array.isArray(normalized.points) ? normalized.points : [];
  uploadedSamples = points;
  uploadedSamplesHighlightId = points[0]?.id ?? null;
  let focus = computeUploadedSamplesFocus(points);
  if (focus == null && points[0] && Number.isFinite(points[0].x) && Number.isFinite(points[0].y)) {
    focus = { x: points[0].x, y: points[0].y };
  }
  if (focus != null) {
    uploadFocusPoint = focus;
    await animateEmbeddingViewToPoint(undefined, focus.x, focus.y, 3);
  }
}

async function handleDatasetSampleSelect(detail: { point: UploadedSamplePoint } | null) {
  const point = detail?.point;
  if (point == null || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
    return;
  }
  uploadedSamplesHighlightId = point.id;
  uploadFocusPoint = { x: point.x, y: point.y };
  await animateEmbeddingViewToPoint(undefined, point.x, point.y, 3);
}

function handleDatasetClear() {
  clearUploadedSamples();
  uploadFocusPoint = null;
}

async function loadMoreSearchResults() {
  if (searchResult == null || searchResultLoadingMore) {
    return;
  }
  let total = searchResult.items.length;
  if (searchResultVisibleCount < total) {
    searchResultVisibleCount = Math.min(total, searchResultVisibleCount + searchPageSize);
    return;
  }
  if (uploadSearchHasMore && uploadSearchDetail?.refetch != null) {
    searchResultLoadingMore = true;
    try {
      let triggered = await uploadSearchDetail.refetch();
      if (!triggered) {
        uploadSearchDetail = {
          ...uploadSearchDetail,
          refetch: undefined,
        };
        uploadSearchHasMore = false;
      }
    } catch (error) {
      console.error("Failed to load additional upload neighbors", error);
      uploadSearchDetail = {
        ...uploadSearchDetail,
        refetch: undefined,
      };
      uploadSearchHasMore = false;
    } finally {
      if (!uploadSearchHasMore) {
        searchResultLoadingMore = false;
      }
    }
    return;
  }
  if (searchResultBackendHasMore && lastSearchArgs != null) {
    let nextLimit = Math.min(searchLimit, searchResultFetchLimit * 2);
    if (nextLimit <= searchResultFetchLimit) {
      searchResultBackendHasMore = false;
      return;
    }
    searchResultLoadingMore = true;
    try {
      await doSearch(lastSearchArgs.query, lastSearchArgs.mode, { limit: nextLimit, preserveIncrement: true });
    } catch (error) {
      console.error("Failed to load additional search results", error);
      searchResultBackendHasMore = false;
      searcherStatus = "Additional neighbors are unavailable.";
    } finally {
      searchResultLoadingMore = false;
    }
  }
}

function clearSearch() {
  searchResult = null;
  searchResultVisible = false;
  uploadFocusPoint = null;
  searchResultVisibleCount = searchPageSize;
  searchResultLoadingMore = false;
  searchResultFetchLimit = searchPageSize;
  searchResultBackendHasMore = false;
  lastSearchArgs = null;
  uploadSearchDetail = null;
  uploadSearchNeighborCount = 0;
  uploadSearchHasMore = false;
  clinicalFeedbackContext = null;
}

  $effect.pre(() => {
    const _filters = textSearchFilters;
    if (searchQuery == "") {
      clearSearch();
    }
  });

  let selectedLabelColumn: string | null = $state(null);

  $effect(() => {
    if (selectedLabelColumn != null && columns.every((c) => c.name !== selectedLabelColumn)) {
      selectedLabelColumn = null;
    }
  });

  // Category column

  let selectedCategoryColumn: string | null = $state(null);
  let categoryLegend: EmbeddingLegend | null = $state.raw(null);

  async function setCategoryColumn(column: string | null) {
    if (column == null) {
      categoryLegend = null;
      return;
    }
    let candidate = columns.find((x) => x.name == column);
    if (candidate == null) {
      return;
    }
    let result;
    if (candidate.jsType == "string" || candidate.jsType == "string[]") {
      result = await tableInfo.makeCategoryColumn(candidate.name, 10);
    } else if (candidate.jsType == "number") {
      if (candidate.distinctCount <= 10) {
        result = await tableInfo.makeCategoryColumn(candidate.name, 10);
      } else {
        result = await tableInfo.makeBinnedNumericColumn(candidate.name);
      }
    } else {
      return;
    }
    categoryLegend = result;
    if (result.legend.length > densityCategoryLimit) {
      embeddingViewMode = "points";
    }
  }

  $effect.pre(() => {
    setCategoryColumn(selectedCategoryColumn);
  });

  // Animation

  async function animateEmbeddingViewToPoint(
    identifier?: any,
    x?: number,
    y?: number,
    scaleMultiplier: number = 2,
  ): Promise<void> {
    if (defaultViewportScale == null) {
      return;
    }

    let scale = (await defaultViewportScale) * scaleMultiplier;
    if (x == null || y == null) {
      if (data.projection == null) {
        return;
      }
      let result = await coordinator.query(
        SQL.Query.from(data.table)
          .select({
            x: SQL.column(data.projection.x),
            y: SQL.column(data.projection.y),
          })
          .where(SQL.eq(SQL.column(data.id), SQL.literal(identifier))),
      );
      let item = result.get(0) as { x: number; y: number };
      x = item.x;
      y = item.y;
    }
    embeddingView?.startViewportAnimation({
      x: x,
      y: y,
      scale: scale,
    });
    embeddingView?.showTooltip(identifier);
  }

  // Filter

  function resetFilter() {
    for (let item of crossFilter.clauses) {
      let source = item.source;
      source?.reset?.();
      crossFilter.update({ ...item, value: null, predicate: null });
    }
  }

  function resetToHomeView() {
    // Reset filters
    resetFilter();
    // Clear search
    searchQuery = "";
    clearSearch();
    // Reset viewport to default
    embeddingView?.startViewportAnimation({
      x: 0,
      y: 0,
      scale: 1,
    });
    // Clear any tooltips
    embeddingView?.showTooltip(null);
  }

  function makeAdditionalFields(columns: any) {
    let fields: any = {};
    fields.id = data.id;
    for (let c of columns) {
      fields[c.name] = c.name;
    }
    return fields;
  }

  let tableScrollTo: any | null = $state(null);
  const scrollTableTo = (identifier: any) => {
    tableScrollTo = identifier;
  };

  function loadState(state: EmbeddingAtlasState) {
    if (typeof state.version != "string") {
      return;
    }
    // Set plot states
    plotStateStores.set(state.plotStates ?? {});

    // Load the spec
    function load(key: string, setter: (value: any) => void) {
      if (state.view && key in state.view) {
        setter(state.view[key]);
      }
    }
    load("showEmbedding", (x) => (showEmbedding = x));
    load("showTable", (x) => (showTable = x));
    load("showNNPanel", (x) => (showNNPanel = x));
    load("showWidgetPanel", (x) => (showWidgetPanel = x));
    if (state.view && "showSidebar" in state.view && !("showNNPanel" in state.view)) {
      showNNPanel = (state.view as any).showSidebar;
    }
    load("columnStyles", (x) => (columnStyles = x));
    load("selectedCategoryColumn", (x) => (selectedCategoryColumn = x));
    load("selectedLabelColumn", (x) => (selectedLabelColumn = x));
    load("embeddingViewMode", (x) => (embeddingViewMode = x));
    load("minimumDensityExpFactor", (x) => (minimumDensityExpFactor = x));
    load("userDarkMode", (x) => ($userDarkMode = x));

    if (state.plots != null) {
      plots = state.plots;
    }
  }

  // Emit onStateChange event.
  $effect(() => {
    if (!initialized) {
      return;
    }

    let state: EmbeddingAtlasState = {
      version: EMBEDDING_ATLAS_VERSION,
      timestamp: new Date().getTime() / 1000,
      view: {
        showEmbedding: showEmbedding,
        showTable: showTable,
        showNNPanel: showNNPanel,
        showWidgetPanel: showWidgetPanel,
        showSidebar: showNNPanel,
        columnStyles: columnStyles,
        selectedCategoryColumn: selectedCategoryColumn,
        selectedLabelColumn: selectedLabelColumn,
        embeddingViewMode: embeddingViewMode,
        minimumDensityExpFactor: minimumDensityExpFactor,
        userDarkMode: $userDarkMode,
      },
      plots: plots,
      plotStates: $plotStateStores,
      predicate: currentPredicate(),
    };
    onStateChange?.(state);
  });

  let ensuredSearchPanelVisible = false;
  $effect(() => {
    if (ensuredSearchPanelVisible || !initialized) {
      return;
    }
    ensuredSearchPanelVisible = true;
    if (!showNNPanel && allowNearestNeighborSearch) {
      showNNPanel = true;
    }
  });

  // Load initial state.
  if (initialState) {
    loadState(initialState);
  }

  onMount(async () => {
    let ignoreColumns = [data.id, data.text, data.projection?.x, data.projection?.y].filter((x) => x != null);
    columns = (await tableInfo.columnDescriptions()).filter((x) => !x.name.startsWith("__"));
    columnsLoaded = true;
    columnsReadyResolve?.();
    columnsReadyResolve = null;
    if (plots.length == 0) {
      plots = await tableInfo.defaultPlots(columns.filter((x) => ignoreColumns.indexOf(x.name) < 0));
    }
    initialized = true;
  });

  function onWindowKeydown(e: KeyboardEvent) {
    if (e.key == "Escape") {
      resetFilter();
      e.preventDefault();
      try {
        let active: any = document.activeElement;
        active?.blur?.();
      } catch (e) {}
    }
  }

</script>

<div class="embedding-atlas-root" style:width="100%" style:height="100%">
  <div
    class="w-full h-full flex flex-col text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800"
    class:dark={$darkMode}
    style:color-scheme={$darkMode ? "dark" : "light"}
  >
    <div class="m-2 flex flex-row items-center gap-4">
      <div class="flex items-center gap-4">
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="flex items-center gap-3 pr-4 border-r border-slate-300 dark:border-slate-700 mr-2 cursor-pointer hover:opacity-75 transition-opacity"
          aria-label="SkinMap"
          onclick={resetToHomeView}
        >
          <img src={skinmapLogo} alt="SkinMap logo" class="h-8 w-auto rounded-md" />
          <div class="text-lg font-semibold tracking-wide text-slate-700 dark:text-slate-200">SkinMap</div>
        </div>
        {#if routeTabs && routeTabs.length > 0}
          <div class="flex items-center gap-2">
            {#each routeTabs as tab (tab.route ?? tab.label)}
              <a
                href={tab.href}
                class={`px-3 py-1 rounded-full text-xs font-semibold border ${
                  isRouteActive(tab.route)
                    ? "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-100 border-slate-300 dark:border-slate-600 shadow"
                    : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}
                aria-current={isRouteActive(tab.route) ? "page" : undefined}
              >
                {tab.label}
              </a>
            {/each}
          </div>
        {/if}
      </div>
      <div class="flex items-center gap-3 flex-1 min-w-0">
        {#if showEmbedding}
          <Select
            label="Color"
            value={selectedCategoryColumn}
            onChange={(v) => (selectedCategoryColumn = v)}
            options={[
              { value: null, label: "(none)" },
              ...columns
                .filter(
                  (c) =>
                    c.distinctCount > 1 &&
                    (((c.jsType == "string" || c.jsType == "string[]") && c.distinctCount <= 10000) || c.jsType == "number"),
                )
                .map((c) => ({ value: c.name, label: `${c.name} (${c.type})` })),
            ]}
          />
          <Select
            label="Labels"
            value={selectedLabelColumn}
            onChange={(v) => (selectedLabelColumn = v)}
            options={[
              {
                value: null,
                label:
                  data.text != null && columns.some((c) => c.name === data.text)
                    ? `${data.text} (default)`
                    : "(none)",
              },
              ...columns.filter((c) => c.name !== data.text).map((c) => ({ value: c.name, label: `${c.name} (${c.type})` })),
            ]}
          />
          <Select
            label="Display"
            value={embeddingViewMode}
            onChange={(v) => (embeddingViewMode = v)}
            disabled={categoryLegend != null && categoryLegend.legend.length > densityCategoryLimit}
            options={[
              { value: "points", label: "Points" },
              { value: "density", label: "Density" },
            ]}
          />
        {/if}
      </div>
      <div class="ml-auto flex items-center gap-3">
        {#if showEmbedding && embeddingViewMode == "density"}
          <div class="select-none flex items-center gap-2">
            <span class="text-slate-500 dark:text-slate-400">Threshold</span>
            <Slider bind:value={minimumDensityExpFactor} min={-4} max={4} step={0.1} />
          </div>
        {/if}
        <FilteredCount filter={crossFilter} table={data.table} />
        <button
          class="flex px-2.5 select-none items-center justify-center text-slate-500 dark:text-slate-300 rounded-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 focus-visible:outline-2 outline-blue-600 -outline-offset-1"
          onclick={resetFilter}
          title="Clear filters"
        >
          Clear
        </button>
        <div class="flex flex-row gap-0.5 items-center">
          <PopupButton icon={IconSettings} title="Options">
            <div class="min-w-[420px]">
              <!-- Text style settings -->
              {#if columns.length > 0}
                <h4 class="text-slate-500 dark:text-slate-400 mb-2 select-none">Column Styles</h4>
                <ColumnStylePicker
                  columns={columns}
                  styles={resolvedColumnStyles}
                  onStylesChange={(value) => {
                    columnStyles = value;
                  }}
                />
              {/if}
              <!-- Export -->
              <h4 class="text-slate-500 dark:text-slate-400 my-2 select-none">Export</h4>
              <div class="flex flex-col gap-2">
                {#if onExportSelection}
                  <div class="flex flex-row gap-2">
                    <ActionButton
                      icon={IconExport}
                      label="Export Selection"
                      title="Export the selected points"
                      class="w-48"
                      onClick={() => onExportSelection(currentPredicate(), exportFormat)}
                    />
                    <Select
                      label="Format"
                      value={exportFormat}
                      onChange={(v) => (exportFormat = v)}
                      options={[
                        { value: "parquet", label: "Parquet" },
                        { value: "jsonl", label: "JSONL" },
                        { value: "json", label: "JSON" },
                        { value: "csv", label: "CSV" },
                      ]}
                    />
                  </div>
                {/if}
                {#if onExportApplication}
                  <ActionButton
                    icon={IconDownload}
                    label="Export Application"
                    title="Download a self-contained static web application"
                    class="w-48"
                    onClick={onExportApplication}
                  />
                {/if}
              </div>
              <h4 class="text-slate-500 dark:text-slate-400 my-2 select-none">About</h4>
              <div>SkinMap, {EMBEDDING_ATLAS_VERSION}</div>
            </div>
          </PopupButton>
        {#if colorScheme == null}
          <Button
            icon={$darkMode ? IconLightMode : IconDarkMode}
            title="Toggle dark mode"
            onClick={() => {
              $userDarkMode = !$darkMode;
            }}
          />
        {/if}
        {#if data.projection != null}
          <ToggleButton icon={IconEmbeddingView} title="Show / hide embedding" bind:checked={showEmbedding} />
        {/if}
        <ToggleButton icon={IconTable} title="Show / hide table" bind:checked={showTable} />
        <ToggleButton icon={IconSearch} title="Show / hide NN tools" bind:checked={showNNPanel} />
        <ToggleButton icon={IconChart} title="Show / hide widgets" bind:checked={showWidgetPanel} />
      </div>
    </div>
    </div>
    <div class="flex flex-row overflow-hidden h-full">
      {#if showTable || showEmbedding}
        <div class="flex-1 flex flex-col mt-0 ml-2 mb-2 mr-2 overflow-hidden">
          {#if showEmbedding && data.projection != null}
            <div class="flex-1 relative bg-white dark:bg-black rounded-md overflow-hidden">
              <EmbeddingView
                bind:this={embeddingView}
                table={data.table}
                filter={crossFilter}
                id={data.id}
                x={data.projection.x}
                y={data.projection.y}
                text={data.text}
                labelColumn={selectedLabelColumn}
                additionalFields={additionalFields}
                categoryLegend={categoryLegend}
                config={{
                  ...(embeddingViewConfig ?? {}),
                  mode: embeddingViewMode,
                  minimumDensity: (1 / 16) * Math.exp(-(minimumDensityExpFactor ?? 0)),
                }}
                labels={embeddingViewLabels}
                customTooltip={{
                  class: CustomTooltip,
                  props: {
                    darkMode: $darkMode,
                    columnStyles: resolvedColumnStyles,
                    onNearestNeighborSearch: allowNearestNeighborSearch
                      ? async (id: any) => {
                          doSearch(id, "neighbors");
                        }
                      : null,
                  },
                }}
                customOverlay={searchResult || uploadedSamples.length > 0
                  ? {
                      class: CustomOverlay,
                      props: {
                        items: searchResult?.items ?? [],
                        highlightItem: searchResultHighlight,
                        focusPoint: uploadFocusPoint,
                        groupMode: groupNeighborsByCondition && activeNeighborGroup == null,
                        groupColors: neighborGroupColors,
                        uploadedPoints: uploadedSamples,
                        uploadedHighlightId: uploadedSamplesHighlightId,
                      },
                    }
                  : null}
                onClickPoint={(p) => scrollTableTo(p.identifier)}
                stateStore={plotStateStores.store("embedding-view")}
                cache={cache}
              />
            </div>
          {/if}
          {#if showTable}
            {#if showEmbedding}
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div
                class="h-2 cursor-row-resize"
                onpointerdown={(e1) => {
                  let h0 = tableHeight;
                  startDrag(e1, (_, dy) => (tableHeight = Math.max(60, h0 - dy)));
                }}
              ></div>
            {/if}
            <div
              class="z-10 bg-white dark:bg-slate-900 rounded-md overflow-hidden"
              style:height={showEmbedding ? tableHeight + "px" : null}
              class:h-full={!showEmbedding}
              transition:slide={{ duration: animationDuration }}
              style:--hover-color="var(--color-amber-200)"
            >
              {#if columns.length > 0}
                {#key columns}
                  <Table
                    coordinator={coordinator}
                    table={data.table}
                    rowKey={data.id}
                    columns={columns.map((x) => x.name)}
                    filter={crossFilter}
                    scrollTo={tableScrollTo}
                    onRowClick={async (identifier) => {
                      await animateEmbeddingViewToPoint(identifier);
                    }}
                    numLines={3}
                    colorScheme={$darkMode ? "dark" : "light"}
                    theme={tableTheme}
                    customCells={resolvedCustomCellRenderers}
                    highlightHoveredRow={true}
                  />
                {/key}
              {/if}
            </div>
          {/if}
        </div>
      {/if}
      {#if anyPanelVisible}
        {#if firstPanel != null && showMainView}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div
            class="w-2 -ml-2 cursor-col-resize"
            onpointerdown={(e) => {
              let w0 = firstPanel === "nn" ? nnPanelWidth : widgetPanelWidth;
              startDrag(e, (dx, _) => {
                if (firstPanel === "nn") {
                  nnPanelWidth = Math.max(300, w0 - dx);
                } else {
                  widgetPanelWidth = Math.max(300, w0 - dx);
                }
              });
            }}
          ></div>
        {/if}
        <div
          class="flex flex-row gap-2 mr-2 mb-2 h-full"
          class:ml-2={!showMainView}
          class:flex-1={!showMainView}
          class:min-w-0={!showMainView}
        >
          {#if showNNPanel}
            <div
              class="flex flex-col bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-md shadow-sm overflow-hidden h-full min-w-0"
              style:width={showMainView ? `${nnPanelWidth}px` : nnPanelFullWidth ? "100%" : null}
              class:flex-1={!showMainView}
              class:w-full={nnPanelFullWidth}
              transition:slide={{ axis: "x", duration: animationDuration }}
            >
              <div class={`flex-1 min-h-0 min-w-0 flex gap-3 p-3 ${nnPanelLayoutClasses}`}>
                <div class={`flex flex-col gap-4 ${nnPanelSidebarClasses}`}>
                  {#if isClinicalRoute}
                    <div class="flex items-center gap-2 rounded-full border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-800 p-1 w-full">
                      <button
                        class={`px-3 py-1 rounded-full text-xs font-semibold flex-1 text-center ${
                          clinicalSearchTab === "image"
                            ? "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-100 shadow"
                            : "text-slate-500 dark:text-slate-400"
                        }`}
                        onclick={() => (clinicalSearchTab = "image")}
                      >
                        Image NN
                      </button>
                      <button
                        class={`px-3 py-1 rounded-full text-xs font-semibold flex-1 text-center ${
                          clinicalSearchTab === "text"
                            ? "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-100 shadow"
                            : "text-slate-500 dark:text-slate-400"
                        }`}
                        onclick={() => (clinicalSearchTab = "text")}
                      >
                        Text NN
                      </button>
                    </div>
                  {/if}
                  {#if !isClinicalRoute || clinicalSearchTab === "image"}
                    <div
                      class={`flex flex-col gap-2 ${
                        isClinicalRoute ? "" : "max-h-[70vh] overflow-y-auto pr-1"
                      }`}
                    >
                      <div class="text-sm font-semibold text-slate-600 dark:text-slate-300 select-none">
                        Image NN Search
                      </div>
                      {#if showUploadSearchWidget}
                        <ImageSearchWidget
                          disabled={!uploadSearchAvailable}
                          endpoint={uploadSearchEndpoint}
                          coordinator={coordinator}
                          table={data.table}
                          columns={columns}
                          uploadBlocked={clinicalUploadBlocked}
                          uploadBlockedMessage={clinicalUploadBlockMessage}
                          scrollable={!isClinicalRoute}
                          on:result={handleImageSearchResult}
                        />
                        {#if uploadSearchWarning}
                          <div class="rounded-md border border-dashed border-slate-300 dark:border-slate-600 bg-slate-100/70 dark:bg-slate-800/50 text-xs text-slate-500 dark:text-slate-400 px-2 py-1.5">
                            Image-based neighbor search is currently unavailable.
                          </div>
                        {/if}
                      {/if}
                      {#if showBatchUploadWidget}
                        <DatasetUploadWidget
                          disabled={!uploadSearchAvailable}
                          endpoint={uploadEmbeddingEndpoint}
                          uploadBlocked={clinicalUploadBlocked}
                          uploadBlockedMessage={clinicalUploadBlockMessage}
                          scrollLists={!isClinicalRoute}
                          on:result={(event) => handleDatasetEmbeddingResult((event as unknown as CustomEvent<any>).detail)}
                          on:select={(event) => handleDatasetSampleSelect((event as unknown as CustomEvent<any>).detail)}
                          on:clear={handleDatasetClear}
                        />
                      {/if}
                    </div>
                  {/if}
                  {#if searcher && (!isClinicalRoute || clinicalSearchTab === "text")}
                    <div class="flex flex-col gap-2 max-h-[70vh] overflow-y-auto pr-1">
                      <div class="text-sm font-semibold text-slate-600 dark:text-slate-300 select-none">
                        Text NN Search
                      </div>
                      <div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3">
                        <div class="flex items-center justify-between gap-2">
                          <div class="text-sm font-semibold text-slate-600 dark:text-slate-300 select-none">Search</div>
                          {#if searchModeOptions.filter((x) => x.value != "neighbors").length > 1}
                            <Select
                              label="Mode"
                              options={searchModeOptions.filter((x) => x.value != "neighbors")}
                              value={searchMode}
                              onChange={(v) => (searchMode = v)}
                              class="min-w-[8rem]"
                            />
                          {/if}
                        </div>
                        <Input
                          type="search"
                          placeholder="Search... (e.g., dermatitis)"
                          className="w-full text-base shadow-md shadow-slate-300/40 dark:shadow-black/40"
                          bind:value={searchQuery}
                        />
                        <div class="flex items-center gap-2">
                          <Button
                            label="Run NN Search"
                            onClick={() => void doSearch(searchQuery, searchMode)}
                            disabled={!searcher || searchQuery.trim() === ""}
                          />
                          {#if searcherStatus}
                            <span class="text-xs text-slate-500 dark:text-slate-400">{searcherStatus}</span>
                          {/if}
                        </div>
                        <SearchFilters
                          disabled={!searcher}
                          coordinator={coordinator}
                          table={data.table}
                          columns={columns}
                          label="Filters"
                          on:change={handleTextFiltersChange}
                        />
                      </div>
                    </div>
                  {/if}
                  {#if shouldShowClinicalFeedback}
                    {#key clinicalSurveyKey}
                      <ClinicalFeedbackForm
                        route={activeRoute}
                        context={clinicalFeedbackContext}
                        searchResult={searchResult}
                        on:submitted={handleClinicalSurveySubmitted}
                      />
                    {/key}
                  {/if}
                </div>
                <div class={`flex-1 min-h-0 min-w-0 flex flex-col gap-3${showMainView ? "" : " overflow-y-auto"}`}>
                  {#if searcher && searchResultVisible}
                    <div class="flex-1 min-h-[12rem] rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm shadow-lg overflow-hidden flex flex-col">
                      {#if searchResult != null}
                        <div class="flex items-center justify-between px-3 py-2 text-xs text-slate-500 dark:text-slate-400 border-b border-slate-300 dark:border-slate-600">
                          <label class="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              class="h-3.5 w-3.5 rounded border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-200"
                              checked={groupNeighborsByCondition}
                              disabled={searchResult.items.length === 0}
                              onchange={(event) => toggleGroupByCondition((event.currentTarget as HTMLInputElement).checked)}
                            />
                            <span>Group by condition</span>
                          </label>
                          {#if groupNeighborsByCondition && activeNeighborGroup != null}
                            <button
                              class="text-slate-500 dark:text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 font-medium"
                              onclick={clearNeighborGroupSelection}
                            >
                              Back to groups
                            </button>
                          {/if}
                        </div>
                        <div class="flex-1 min-h-0">
                          <SearchResultList
                            items={searchResultDisplayItems}
                            label={searchResultDisplayLabel}
                            highlight={searchResult.highlight}
                            visibleCount={searchResultVisibleCount}
                            hasMore={shouldShowLoadMore()}
                            loadingMore={searchResultLoadingMore}
                            onLoadMore={loadMoreSearchResults}
                            onClick={async (item) => {
                              scrollTableTo(item.id);
                              searchResultHighlight = item;
                              await animateEmbeddingViewToPoint(item.id, item.x, item.y);
                            }}
                            onClose={clearSearch}
                            columnStyles={resolvedColumnStyles}
                            groupMode={groupNeighborsByCondition}
                            groups={neighborGroupSummaries}
                            groupColors={neighborGroupColors}
                            activeGroupKey={activeNeighborGroup}
                            activeGroupLabel={activeNeighborGroupLabel}
                            onGroupSelect={selectNeighborGroup}
                            onGroupBack={clearNeighborGroupSelection}
                          />
                        </div>
                      {:else if searcherStatus != null}
                        <div class="flex-1 flex items-center justify-center p-4">
                          <Spinner status={searcherStatus} />
                        </div>
                      {/if}
                    </div>
                  {:else if searcherStatus != null}
                    <div class="flex-1 min-h-[12rem] rounded-md border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm shadow-inner flex items-center justify-center text-slate-500 dark:text-slate-400">
                      {searcherStatus}
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          {/if}
          {#if showWidgetPanel}
            {#if showNNPanel && showMainView}
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div
                class="w-2 cursor-col-resize"
                onpointerdown={(e) => {
                  let w0 = widgetPanelWidth;
                  startDrag(e, (dx, _) => (widgetPanelWidth = Math.max(280, w0 - dx)));
                }}
              ></div>
            {/if}
            <div
              class="flex flex-col bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-md shadow-sm overflow-hidden h-full min-w-0"
              style:width={showMainView ? `${widgetPanelWidth}px` : widgetPanelFullWidth ? "100%" : null}
              class:flex-1={!showMainView}
              class:w-full={widgetPanelFullWidth}
              transition:slide={{ axis: "x", duration: animationDuration }}
            >
              <div class="flex-1 min-h-0 overflow-y-auto p-3">
                <PlotList
                  bind:plots={plots}
                  table={data.table}
                  columns={columns}
                  filter={crossFilter}
                  layout={widgetFullWidth ? "full" : "sidebar"}
                  stateStores={plotStateStores}
                />
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>
<svelte:window onkeydown={onWindowKeydown} />
