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
  import Spinner from "./Spinner.svelte";
  import ActionButton from "./widgets/ActionButton.svelte";
  import Button from "./widgets/Button.svelte";
  import ImageSearchWidget from "./widgets/ImageSearchWidget.svelte";
  import Input from "./widgets/Input.svelte";
  import PopupButton from "./widgets/PopupButton.svelte";
  import Select from "./widgets/Select.svelte";
  import Slider from "./widgets/Slider.svelte";
  import ToggleButton from "./widgets/ToggleButton.svelte";

  import {
    IconDarkMode,
    IconDownload,
    IconEmbeddingView,
    IconExport,
    IconLightMode,
    IconMenu,
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
  import type { Plot } from "./plots/plot.js";
  import { PlotStateStoreManager } from "./plots/plot_state_store.js";
  import { getRenderer, type ColumnStyle } from "./renderers/index.js";
  import { querySearchResultItems, resolveSearcher, type SearchResultItem } from "./search.js";
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

  let uploadSearchConfig = $derived(uploadSearch);
  let uploadSearchAvailable = $derived(uploadSearchConfig?.enabled === true);
  let uploadSearchEndpoint = $derived(uploadSearchConfig?.endpoint ?? "/data/upload-neighbors");

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
  let showSidebar: boolean = $state(true);

  let tableHeight: number = $state(320);
  let panelWidth: number = $state(400);

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
      searcher: specifiedSearcher,
      textColumns: searchColumns,
    }),
  );

  let allowFullTextSearch = $derived(searcher.fullTextSearch != null);
  let allowVectorSearch = $derived(searcher.vectorSearch != null);
  let allowNearestNeighborSearch = $derived(searcher.nearestNeighbors != null);
  let searchMode = $state<"full-text" | "vector" | "neighbors">("full-text");
  let searchModeOptions = $derived([
    ...(allowFullTextSearch ? [{ label: "Full Text", value: "full-text" }] : []),
    ...(allowVectorSearch ? [{ label: "Vector", value: "vector" }] : []),
    ...(allowNearestNeighborSearch ? [{ label: "Neighbors", value: "neighbors" }] : []),
  ]);

  let searchQuery = $state("");
  let searcherStatus = $state("");
  let searchResultVisible = $state(false);
  let searchResult: {
    label: string;
    highlight: string;
    items: SearchResultItem[];
  } | null = $state(null);
  let searchResultHighlight = $state<SearchResultItem | null>(null);
  let searchResultVisibleCount: number = $state(searchPageSize);
  let searchResultLoadingMore: boolean = $state(false);
  let searchResultFetchLimit: number = $state(searchPageSize);
  let searchResultBackendHasMore: boolean = $state(false);
  let lastSearchArgs = $state.raw<{ query: any; mode: "full-text" | "vector" | "neighbors" } | null>(null);
  let uploadSearchDetail = $state.raw<UploadSearchResultDetail | null>(null);
  let uploadSearchNeighborCount: number = $state(0);
  let uploadSearchHasMore: boolean = $state(false);
  let uploadFocusPoint: { x: number; y: number } | null = $state(null);

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

    searchResultVisible = true;
    searcherStatus = "Searching...";
    uploadSearchDetail = null;
    uploadSearchHasMore = false;
    searchResultBackendHasMore = false;

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
    const fetchLimit = Math.min(searchLimit, options?.limit ?? searchPageSize);

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
      highlight = effectiveQuery;
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

    // Apply predicate in case the searcher does not handle predicate.
    // And convert the search result ids to tuples.
    let result = await querySearchResultItems(
      coordinator,
      data.table,
      { id: data.id, x: data.projection?.x, y: data.projection?.y, text: data.text },
      additionalFields,
      predicate,
      searcherResult,
    );

    searcherStatus = "";
    searchResult = { label: label, highlight: highlight, items: result };
    searchResultFetchLimit = fetchLimit;
    let searcherHasMore = (searcherResult as any)?.__hasMore === true;
    searchResultBackendHasMore = (searcherHasMore || searcherResult.length >= fetchLimit) && fetchLimit < searchLimit;
    updateSearchResultVisibleCount(result.length, options?.preserveIncrement === true);
    if (options?.preserveIncrement !== true) {
      searchResultLoadingMore = false;
    }
    uploadSearchNeighborCount = 0;
    lastSearchArgs = { query: effectiveQuery, mode: resolvedMode as "full-text" | "vector" | "neighbors" };
    uploadFocusPoint = null;
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
    searchResult = { label, highlight: "", items: result };
    updateSearchResultVisibleCount(result.length, searchResultLoadingMore);
    return result;
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
    let nextLimit = Math.min(searchLimit, searchResultFetchLimit + searchPageSize);
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
}

  $effect.pre(() => {
    if (searchQuery == "") {
      clearSearch();
    } else {
      debouncedSearch(searchQuery, searchMode);
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

  async function animateEmbeddingViewToPoint(identifier?: any, x?: number, y?: number): Promise<void> {
    if (defaultViewportScale == null) {
      return;
    }

    let scale = (await defaultViewportScale) * 2;
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
    load("showSidebar", (x) => (showSidebar = x));
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
        showSidebar: showSidebar,
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

  // Load initial state.
  if (initialState) {
    loadState(initialState);
  }

  onMount(async () => {
    let ignoreColumns = [data.id, data.text, data.projection?.x, data.projection?.y].filter((x) => x != null);
    columns = (await tableInfo.columnDescriptions()).filter((x) => !x.name.startsWith("__"));
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
              <div>Embedding Atlas, {EMBEDDING_ATLAS_VERSION}</div>
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
        <ToggleButton icon={IconMenu} title="Show / hide sidebar" bind:checked={showSidebar} />
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
                customOverlay={searchResult
                  ? {
                      class: CustomOverlay,
                      props: {
                        items: searchResult.items,
                        highlightItem: searchResultHighlight,
                        focusPoint: uploadFocusPoint,
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
                onmousedown={(e1) => {
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
      {#if showSidebar}
        {@const fullWidth = !(showTable || showEmbedding)}
        {#if !fullWidth}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div
            class="w-2 -ml-2 cursor-col-resize"
            onmousedown={(e) => {
              let w0 = panelWidth;
              startDrag(e, (dx, _) => (panelWidth = Math.max(300, w0 - dx)));
            }}
          ></div>
        {/if}
        <div
          class="flex flex-col mr-2 mb-2 gap-2 dark:bg-slate-800"
          style:width={fullWidth ? null : `${panelWidth}px`}
          class:ml-2={fullWidth}
          class:flex-none={!fullWidth}
          class:flex-1={fullWidth}
          transition:slide={{ axis: "x", duration: animationDuration }}
        >
          {#if uploadSearchConfig}
            <ImageSearchWidget
              disabled={!uploadSearchAvailable}
              endpoint={uploadSearchEndpoint}
              coordinator={coordinator}
              table={data.table}
              columns={columns}
              on:result={handleImageSearchResult}
            />
          {/if}
          {#if searcher}
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
            </div>
          {/if}
          {#if searcher && searchResultVisible}
            <div class="flex-none rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm shadow-lg overflow-hidden h-[28rem] max-h-[65vh]">
              {#if searchResult != null}
                <SearchResultList
                  items={searchResult.items}
                  label={searchResult.label}
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
                />
              {:else if searcherStatus != null}
                <div class="flex h-full items-center justify-center p-4">
                  <Spinner status={searcherStatus} />
                </div>
              {/if}
            </div>
          {/if}
          <div
            class="flex-1 w-full rounded-md overflow-x-hidden overflow-y-scroll"
            style:width={fullWidth ? null : `${panelWidth}px`}
          >
            <PlotList
              bind:plots={plots}
              table={data.table}
              columns={columns}
              filter={crossFilter}
              layout={fullWidth ? "full" : "sidebar"}
              stateStores={plotStateStores}
            />
          </div>
        </div>
      {/if}
    </div>
  </div>
</div>
<svelte:window onkeydown={onWindowKeydown} />
