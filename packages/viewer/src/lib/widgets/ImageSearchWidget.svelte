<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import { nanoid } from "nanoid";
  import * as SQL from "@uwdata/mosaic-sql";

  import Button from "./Button.svelte";
  import Select from "./Select.svelte";
  import Spinner from "../Spinner.svelte";

import type { ColumnDesc } from "../database_utils.js";
import type { Coordinator } from "@uwdata/mosaic-core";

interface Neighbor {
  id: any;
  distance: number;
  rowIndex?: number;
}

type SerializedFilter =
  | { column: string; type: "string"; values: string[] }
  | { column: string; type: "string[]"; values: string[] }
  | { column: string; type: "number"; min: number | null; max: number | null };

interface $$Props {
  disabled?: boolean;
  endpoint?: string;
  coordinator: Coordinator;
  table: string;
  columns?: ColumnDesc[];
}

interface $$Events {
  result: {
    neighbors: Neighbor[];
    previewUrl: string | null;
    filters: SerializedFilter[];
    setStatus: (value: string) => void;
    refetch: (options?: { maxK?: number }) => Promise<boolean>;
  };
}

interface $$Slots {}

interface FilterRow {
    id: string;
    column: string | null;
    columnType: "string" | "string[]" | "number" | null;
    loading: boolean;
    error: string | null;
    options: { value: string; count: number | null }[];
    selectedValues: string[];
    minBound: number | null;
    maxBound: number | null;
    minValue: number | null;
    maxValue: number | null;
    minInput: string;
    maxInput: string;
  }

const dispatch = createEventDispatcher<$$Events>();

const {
  disabled = false,
  endpoint = "/data/upload-neighbors",
  coordinator,
  table,
  columns = [] as ColumnDesc[],
} = $props();

const MAX_AUTO_REFETCH_K = 1000;

let file: File | null = $state(null);
let previewUrl: string | null = $state(null);
let status: string = $state("");
let errorMessage: string | null = $state(null);
let uploading: boolean = $state(false);
let topK: number = $state(50);

let filters: FilterRow[] = $state.raw([]);
let filterChangeTimer: any = null;
let hasExecutedSearch = false;
let currentNeighbors: Neighbor[] = [];
let lastRequestK: number | null = null;
let refetchInProgress = false;

  let filterableColumns = $derived(
    columns.filter((col: ColumnDesc) => col.jsType === "string" || col.jsType === "string[]" || col.jsType === "number"),
  );
  let columnOptions = $derived(filterableColumns.map((col: ColumnDesc) => ({ value: col.name, label: col.name })));

  function createEmptyFilterRow(): FilterRow {
    return {
      id: nanoid(),
      column: null,
      columnType: null,
      loading: false,
      error: null,
      options: [],
      selectedValues: [],
      minBound: null,
      maxBound: null,
      minValue: null,
      maxValue: null,
      minInput: "",
      maxInput: "",
    };
  }

  function resetPreview() {
    if (previewUrl != null) {
      URL.revokeObjectURL(previewUrl);
    }
    previewUrl = null;
  }

  function onFileChange(event: Event) {
    const target = event.target as HTMLInputElement;
    if (!target.files || target.files.length === 0) {
      file = null;
      resetPreview();
      return;
    }
    file = target.files[0];
    resetPreview();
    previewUrl = URL.createObjectURL(file);
    status = "";
    errorMessage = null;
  }

  onDestroy(() => {
    if (filterChangeTimer) {
      clearTimeout(filterChangeTimer);
    }
    resetPreview();
  });

  function addFilter() {
    if (disabled) {
      return;
    }
    filters = [...filters, createEmptyFilterRow()];
  }

  function removeFilter(id: string) {
    filters = filters.filter((filter) => filter.id !== id);
    scheduleFiltersChanged();
  }

  function updateFilterColumn(filterId: string, columnName: string | null) {
    const columnMeta = columnName ? filterableColumns.find((col) => col.name === columnName) : null;
    const columnType: FilterRow["columnType"] =
      columnMeta?.jsType === "number"
        ? "number"
        : columnMeta?.jsType === "string[]"
          ? "string[]"
          : columnMeta?.jsType === "string"
            ? "string"
            : null;

    filters = filters.map((filter) =>
      filter.id === filterId
        ? {
            ...filter,
            column: columnName,
            columnType,
            loading: columnType != null,
            error: null,
            options: [],
            selectedValues: [],
            minBound: null,
            maxBound: null,
            minValue: null,
            maxValue: null,
            minInput: "",
            maxInput: "",
          }
        : filter,
    );

    if (columnName != null && columnType != null) {
      loadFilterData(filterId, columnName, columnType).catch((error) => {
        console.error("Failed to load filter metadata", error);
        filters = filters.map((filter) =>
          filter.id === filterId
            ? {
                ...filter,
                loading: false,
                error: "Failed to load filter options.",
              }
            : filter,
        );
      });
    } else {
      filters = filters.map((filter) =>
        filter.id === filterId
          ? {
              ...filter,
              loading: false,
              error: null,
            }
          : filter,
      );
      scheduleFiltersChanged();
    }
  }

  async function loadFilterData(filterId: string, columnName: string, columnType: "string" | "string[]" | "number") {
    if (!coordinator || !table) {
      filters = filters.map((filter) =>
        filter.id === filterId
          ? {
              ...filter,
              loading: false,
              error: "Data source unavailable.",
            }
          : filter,
      );
      return;
    }

    if (columnType === "number") {
      const columnRef = SQL.column(columnName, table);
      const query = SQL.Query.from(table).select({
        min: SQL.sql`MIN(${columnRef})`,
        max: SQL.sql`MAX(${columnRef})`,
      });
      const result = await coordinator.query(query);
      const rows = Array.from(result) as { min: number | null; max: number | null }[];
      const minBound = rows[0]?.min ?? null;
      const maxBound = rows[0]?.max ?? null;

      filters = filters.map((filter) =>
        filter.id === filterId
          ? {
              ...filter,
              loading: false,
              error: null,
              minBound,
              maxBound,
              minValue: null,
              maxValue: null,
              minInput: "",
              maxInput: "",
            }
          : filter,
      );
      return;
    }

    const columnRef = SQL.column(columnName, table);
    let query;
    if (columnType === "string[]") {
      query = SQL.Query.from(
        SQL.Query.from(table)
          .select({
            value: SQL.sql`UNNEST(${columnRef})`,
          })
          .where(SQL.not(SQL.isNull(columnRef))),
      )
        .select({
          value: "value",
          count: SQL.count(),
        })
        .groupby("value")
        .orderby(SQL.desc("count"))
        .limit(200);
    } else {
      query = SQL.Query.from(table)
        .select({
          value: columnRef,
          count: SQL.count(),
        })
        .where(SQL.not(SQL.isNull(columnRef)))
        .groupby(columnRef)
        .orderby(SQL.desc(SQL.count()))
        .limit(200);
    }

    const result = await coordinator.query(query);
    const options = Array.from(result)
      .map((row: any) => {
        if (row.value == null) {
          return null;
        }
        const text = String(row.value).trim();
        if (text === "") {
          return null;
        }
        return {
          value: text,
          count: typeof row.count === "number" ? row.count : null,
        };
      })
      .filter((option): option is { value: string; count: number | null } => option != null);

    filters = filters.map((filter) =>
      filter.id === filterId
        ? {
            ...filter,
            loading: false,
            error: null,
            options,
            selectedValues: [],
          }
        : filter,
    );
  }

  function toggleStringOption(filterId: string, optionValue: string) {
    filters = filters.map((filter) => {
      if (filter.id !== filterId) {
        return filter;
      }
      const values = new Set(filter.selectedValues);
      if (values.has(optionValue)) {
        values.delete(optionValue);
      } else {
        values.add(optionValue);
      }
      return {
        ...filter,
        selectedValues: Array.from(values).sort(),
      };
    });
    scheduleFiltersChanged();
  }

  function updateNumberValue(filterId: string, which: "min" | "max", rawValue: string) {
    filters = filters.map((filter) => {
      if (filter.id !== filterId) {
        return filter;
      }
      const parsed = rawValue.trim() === "" ? null : Number(rawValue);
      const sanitized = parsed != null && Number.isFinite(parsed) ? parsed : null;
      return {
        ...filter,
        minInput: which === "min" ? rawValue : filter.minInput,
        maxInput: which === "max" ? rawValue : filter.maxInput,
        minValue: which === "min" ? sanitized : filter.minValue,
        maxValue: which === "max" ? sanitized : filter.maxValue,
      };
    });
    scheduleFiltersChanged();
  }

  function serializeFilters(): SerializedFilter[] {
    const activeFilters: SerializedFilter[] = [];
    for (const filter of filters) {
      if (!filter.column || !filter.columnType) {
        continue;
      }
      if ((filter.columnType === "string" || filter.columnType === "string[]") && filter.selectedValues.length > 0) {
        activeFilters.push({
          column: filter.column,
          type: filter.columnType,
          values: [...filter.selectedValues],
        });
      } else if (filter.columnType === "number") {
        const min = filter.minValue;
        const max = filter.maxValue;
        if (min != null || max != null) {
          activeFilters.push({
            column: filter.column,
            type: "number",
            min: min ?? null,
            max: max ?? null,
          });
        }
  }
    }
    return activeFilters;
  }

  async function requestNeighbors(kValue: number): Promise<Neighbor[]> {
    if (!file) {
      throw new Error("No image selected.");
    }
    const formData = new FormData();
    formData.append("file", file);
    const resp = await fetch(`${endpoint}?k=${encodeURIComponent(kValue)}`, {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const message = resp.status === 404 ? "Upload search is not available on this server." : `Server error (${resp.status})`;
      throw new Error(message);
    }
    const payload = await resp.json();
    const neighbors: Neighbor[] = Array.isArray(payload?.neighbors) ? payload.neighbors : [];
    return neighbors;
  }

  async function performAutoRefetch(options?: { maxK?: number }): Promise<boolean> {
    const { maxK = MAX_AUTO_REFETCH_K } = options ?? {};
    if (!file || uploading || refetchInProgress) {
      return false;
    }
    const currentK = lastRequestK ?? topK;
    if (currentK >= maxK) {
      return false;
    }
    const nextK = Math.min(maxK, Math.max(currentK, topK) * 2);
    if (nextK <= currentK) {
      return false;
    }
    refetchInProgress = true;
    uploading = true;
    errorMessage = null;
    status = "Searching...";
    try {
      const neighbors = await requestNeighbors(nextK);
      lastRequestK = nextK;
      emitResult(neighbors, previewUrl, { skipStatusReset: false });
      return true;
    } catch (err: any) {
      console.error("Upload search failed", err);
      errorMessage = err?.message ?? "Failed to query nearest neighbors.";
      status = "";
      return false;
    } finally {
      uploading = false;
      refetchInProgress = false;
    }
  }

  function emitResult(neighbors: Neighbor[], preview: string | null, options?: { skipStatusReset?: boolean }) {
    currentNeighbors = neighbors;
    hasExecutedSearch = true;
    const serializedFilters = serializeFilters();
    if (!options?.skipStatusReset) {
      status = serializedFilters.length > 0 ? "Filtering..." : "";
    }
    const detail: $$Events["result"] = {
      neighbors,
      previewUrl: preview,
      filters: serializedFilters,
      setStatus: (value: string) => {
        status = value;
      },
      refetch: performAutoRefetch,
    };
    dispatch("result", detail);
  }

  function scheduleFiltersChanged() {
    if (!hasExecutedSearch) {
      return;
    }
    if (filterChangeTimer) {
      clearTimeout(filterChangeTimer);
    }
    filterChangeTimer = setTimeout(() => {
      filterChangeTimer = null;
      emitResult(currentNeighbors, previewUrl);
    }, 150);
  }

  async function submit() {
    if (disabled || file == null || uploading) {
      return;
    }
    errorMessage = null;
    status = "Embedding image...";
    uploading = true;
    try {
      const neighbors = await requestNeighbors(topK);
      lastRequestK = topK;
      emitResult(neighbors, previewUrl, { skipStatusReset: false });
    } catch (err: any) {
      console.error("Upload search failed", err);
      errorMessage = err?.message ?? "Failed to query nearest neighbors.";
      status = "";
    } finally {
      uploading = false;
    }
  }

  function updateTopK(value: string) {
    const parsed = parseInt(value, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      topK = Math.min(parsed, 200);
    }
  }
</script>

<div class="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm flex flex-col gap-3 p-3">
  <div class="flex flex-col gap-1">
    <span class="text-base font-semibold text-slate-700 dark:text-slate-200">Image Neighbor Search</span>
    <span class="text-slate-500 dark:text-slate-400">Upload an image to find visually similar samples in SkinMap.</span>
  </div>

  <label class="flex flex-col gap-2 text-slate-600 dark:text-slate-300">
    <span class="font-medium">Image File</span>
    <input
      class="block text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-100 file:text-slate-700 dark:file:bg-slate-800 dark:file:text-slate-200 dark:file:border-slate-600"
      type="file"
      accept="image/*"
      onchange={onFileChange}
      disabled={disabled || uploading}
    />
  </label>

  {#if previewUrl}
    <div class="flex flex-col gap-2">
      <span class="text-slate-500 dark:text-slate-400 font-medium">Preview</span>
      <img src={previewUrl} alt="Uploaded preview" class="rounded-md border border-slate-200 dark:border-slate-700 max-h-48 object-contain bg-slate-100 dark:bg-slate-800" />
    </div>
  {/if}

  <div class="flex flex-col gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-3">
    <div class="flex items-center gap-2">
      <span class="font-medium text-slate-600 dark:text-slate-300">Filters</span>
      <Button label="Add filter" onClick={addFilter} disabled={disabled} />
    </div>
    {#if filters.length === 0}
      <div class="text-slate-400 dark:text-slate-500 text-sm">No filters applied.</div>
    {:else}
      <div class="flex flex-col gap-2">
        {#each filters as filter (filter.id)}
          <div class="flex flex-col gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/70 p-2">
            <div class="flex items-center gap-2">
              <Select
                placeholder="Column"
                value={filter.column}
                options={columnOptions}
                disabled={disabled}
                onChange={(value) => updateFilterColumn(filter.id, (value as string | null) ?? null)}
                class="flex-1"
              />
              <Button label="Remove" onClick={() => removeFilter(filter.id)} disabled={disabled} />
            </div>

            {#if filter.columnType === "string" || filter.columnType === "string[]"}
              {#if filter.loading}
                <div class="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm">
                  <Spinner status="Loading values..." />
                </div>
              {:else if filter.options.length === 0}
                <div class="text-slate-400 dark:text-slate-500 text-sm">No categorical values available.</div>
              {:else}
                <div class="max-h-40 overflow-y-auto flex flex-col gap-1 pr-1">
                  {#each filter.options as option (option.value)}
                    <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                      <input
                        type="checkbox"
                        class="accent-blue-500 rounded"
                        checked={filter.selectedValues.includes(option.value)}
                        onchange={() => toggleStringOption(filter.id, option.value)}
                        disabled={disabled}
                      />
                      <span class="flex-1">{option.value}</span>
                      {#if option.count != null}
                        <span class="text-xs text-slate-400 dark:text-slate-500">({option.count})</span>
                      {/if}
                    </label>
                  {/each}
                </div>
              {/if}
            {:else if filter.columnType === "number"}
              {#if filter.loading}
                <div class="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm">
                  <Spinner status="Loading range..." />
                </div>
              {:else}
                <div class="flex flex-col gap-2 text-sm text-slate-600 dark:text-slate-300">
                  <div class="flex items-center gap-2">
                    <span>Min</span>
                    <input
                      type="number"
                      class="w-28 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1"
                      value={filter.minInput}
                      placeholder={filter.minBound != null ? filter.minBound.toString() : ""}
                      oninput={(event) => updateNumberValue(filter.id, "min", (event.target as HTMLInputElement).value)}
                      disabled={disabled}
                    />
                    <span>Max</span>
                    <input
                      type="number"
                      class="w-28 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1"
                      value={filter.maxInput}
                      placeholder={filter.maxBound != null ? filter.maxBound.toString() : ""}
                      oninput={(event) => updateNumberValue(filter.id, "max", (event.target as HTMLInputElement).value)}
                      disabled={disabled}
                    />
                  </div>
                  {#if filter.minBound != null && filter.maxBound != null}
                    <span class="text-xs text-slate-400 dark:text-slate-500">Available range: {filter.minBound} – {filter.maxBound}</span>
                  {/if}
                </div>
              {/if}
            {/if}

            {#if filter.error}
              <div class="text-sm text-red-600 dark:text-red-400">{filter.error}</div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <div class="flex items-center gap-3">
    <div class="flex items-center gap-2">
      <span class="text-slate-500 dark:text-slate-400">Top K</span>
      <input
        class="w-20 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1"
        type="number"
        min="1"
        max="200"
        step="1"
        value={topK}
        disabled={disabled || uploading}
        oninput={(event) => updateTopK((event.target as HTMLInputElement).value)}
      />
    </div>
    <Button
      class="ml-auto"
      disabled={disabled || uploading || file == null}
      onClick={submit}
      label={uploading ? "Searching..." : "Find Neighbors"}
    />
  </div>

  {#if status}
    <div class="text-slate-500 dark:text-slate-400">{status}</div>
  {/if}
  {#if errorMessage}
    <div class="text-red-600 dark:text-red-400">{errorMessage}</div>
  {/if}
  {#if file == null}
    <div class="text-slate-400 dark:text-slate-500">Select a JPG or PNG file to enable the search button.</div>
  {/if}
</div>
