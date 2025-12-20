<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import { nanoid } from "nanoid";
  import * as SQL from "@uwdata/mosaic-sql";

  import Button from "./Button.svelte";
  import Select from "./Select.svelte";
  import Spinner from "../Spinner.svelte";

  import type { ColumnDesc } from "../database_utils.js";
  import type { Coordinator } from "@uwdata/mosaic-core";

  type SerializedFilter =
    | { column: string; type: "string"; values: string[] }
    | { column: string; type: "string[]"; values: string[] }
    | { column: string; type: "number"; min: number | null; max: number | null };

  interface $$Props {
    disabled?: boolean;
    coordinator: Coordinator;
    table: string;
    columns?: ColumnDesc[];
    label?: string;
  }

  interface $$Events {
    change: { filters: SerializedFilter[] };
  }

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

  let { disabled = false, coordinator, table, columns = [] as ColumnDesc[], label = "Filters" } = $props();

  let filters: FilterRow[] = $state.raw([]);
  let filterChangeTimer: any = null;

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

  onDestroy(() => {
    if (filterChangeTimer) {
      clearTimeout(filterChangeTimer);
    }
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

  function scheduleFiltersChanged() {
    if (filterChangeTimer) {
      clearTimeout(filterChangeTimer);
    }
    filterChangeTimer = setTimeout(() => {
      filterChangeTimer = null;
      dispatch("change", { filters: serializeFilters() });
    }, 150);
  }
</script>

<div class="flex flex-col gap-2">
  <div class="flex items-center gap-2">
    <span class="font-medium text-slate-600 dark:text-slate-300">{label}</span>
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
                  <span class="text-xs text-slate-400 dark:text-slate-500">
                    Available range: {filter.minBound} – {filter.maxBound}
                  </span>
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
