// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import type { Coordinator } from "@uwdata/mosaic-core";
import * as SQL from "@uwdata/mosaic-sql";

import type { Searcher } from "./api.js";

const DEFAULT_NEIGHBOR_LIMIT = 500;

class SearchWorkerAPI {
  worker: Worker;
  callbacks: Map<string, (data: any) => void>;

  constructor() {
    this.worker = new Worker(new URL("./search.worker.js", import.meta.url), { type: "module" });
    this.callbacks = new Map();
    this.worker.onmessage = (e) => {
      let cb = this.callbacks.get(e.data.identifier);
      if (cb != null) {
        this.callbacks.delete(e.data.identifier);
        cb(e.data);
      }
    };
  }

  rpc(message: any): Promise<any> {
    return new Promise((resolve, _) => {
      let identifier = new Date().getTime() + "-" + Math.random();
      this.callbacks.set(identifier, resolve);
      this.worker.postMessage({ ...message, identifier: identifier });
    });
  }

  async clear() {
    await this.rpc({ type: "clear" });
  }

  async addPoints(points: { id: string | number; text: string }[]) {
    await this.rpc({ type: "points", points: points });
  }

  async query(query: string, limit: number): Promise<string[]> {
    let data = await this.rpc({ type: "query", query: query, limit: limit });
    return data.result;
  }
}

export class FullTextSearcher implements Searcher {
  coordinator: Coordinator;
  table: string;
  columns: { text: string | string[]; id: string };

  backend: SearchWorkerAPI;
  currentIndex: { predicate: string | null } | null = null;

  constructor(
    coordinator: Coordinator,
    table: string,
    columns: {
      text: string | string[];
      id: string;
    },
  ) {
    this.coordinator = coordinator;
    this.table = table;
    this.columns = columns;
    this.currentIndex = null;
    this.backend = new SearchWorkerAPI();
  }

  predicateString(predicate: any | null): string | null {
    if (predicate != null && predicate.toString() != "") {
      return predicate.toString();
    } else {
      return null;
    }
  }

  async buildIndexIfNeeded(predicate: any | null) {
    let predicateString = this.predicateString(predicate);
    if (this.currentIndex != null && this.currentIndex.predicate == predicateString) {
      return;
    }

    let textColumns = (Array.isArray(this.columns.text) ? this.columns.text : [this.columns.text]).filter(
      (col): col is string => col != null && col !== "",
    );
    if (textColumns.length == 0) {
      return;
    }
    // TRY_CAST prevents DuckDB from aborting if a column isn't representable as text (e.g., blobs)
    let textExpressions = textColumns.map(
      (column) => `COALESCE(TRY_CAST(${SQL.column(column)} AS TEXT), '')`,
    );
    let textExpr =
      textExpressions.length == 1 ? textExpressions[0] : `concat_ws(' ', ${textExpressions.join(", ")})`;

    let result: any;
    if (predicateString != null) {
      result = await this.coordinator.query(`
        SELECT
          ${SQL.column(this.columns.id)} AS id,
          ${textExpr} AS text
        FROM ${this.table}
        WHERE ${predicateString}
      `);
    } else {
      result = await this.coordinator.query(`
        SELECT
          ${SQL.column(this.columns.id)} AS id,
          ${textExpr} AS text
        FROM ${this.table}
      `);
    }
    await this.backend.clear();
    await this.backend.addPoints(Array.from(result));
    this.currentIndex = { predicate: predicateString };
  }

  async fullTextSearch(query: string, options: { limit?: number; predicate?: any } = {}): Promise<{ id: any }[]> {
    let limit = options.limit ?? 100;
    let predicate = options.predicate;
    await this.buildIndexIfNeeded(predicate);
    let resultIDs = await this.backend.query(query, limit);
    return resultIDs.map((id) => ({ id: id }));
  }
}

export interface SearchResultItem {
  id: any;
  fields: Record<string, any>;
  distance?: number;
  x?: number;
  y?: number;
  text?: string;
}

export async function querySearchResultItems(
  coordinator: Coordinator,
  table: string,
  columns: { id: string; x?: string | null; y?: string | null; text?: string | null },
  additionalFields: Record<string, any> | null,
  predicate: string | null,
  items: { id: any; distance?: number }[],
): Promise<SearchResultItem[]> {
  let fieldExpressions: string[] = [`${SQL.column(columns.id, table)} AS id`];
  if (columns.x) {
    fieldExpressions.push(`${SQL.column(columns.x, table)} AS x`);
  }
  if (columns.y) {
    fieldExpressions.push(`${SQL.column(columns.y, table)} AS y`);
  }
  if (columns.text) {
    fieldExpressions.push(`${SQL.column(columns.text, table)} AS text`);
  }
  let fields = additionalFields ?? {};
  for (let key in fields) {
    let spec = fields[key];
    if (typeof spec == "string") {
      fieldExpressions.push(`${SQL.column(spec, table)} AS "field_${key}"`);
    } else {
      fieldExpressions.push(`${SQL.sql(spec.sql)} AS "field_${key}"`);
    }
  }

  let ids = items.map((x) => x.id);
  let id2order = new Map<any, number>();
  let id2item = new Map<any, { id: any; distance?: number }>();
  for (let i = 0; i < ids.length; i++) {
    id2order.set(ids[i], i);
    id2item.set(ids[i], items[i]);
  }
  let r = await coordinator.query(`
    SELECT
      ${fieldExpressions.join(", ")}
    FROM (
      SELECT ${SQL.column(columns.id, table)} AS __search_result_id__
      FROM ${table}
      WHERE
        ${SQL.column(columns.id, table)} IN [${ids.map((x) => SQL.literal(x)).join(", ")}]
        ${predicate ? `AND (${predicate})` : ``}
    )
    LEFT JOIN ${table} ON ${SQL.column(columns.id, table)} = __search_result_id__
  `);

  let result = Array.from(r).map((x: any): any => {
    let r: Record<string, any> = { id: x.id, distance: id2item.get(x.id)?.distance, fields: {} };
    for (let key in x) {
      if (key.startsWith("field_")) {
        r.fields[key.substring(6)] = x[key];
      } else {
        r[key] = x[key];
      }
    }
    return r;
  });
  result = result.sort((a, b) => (id2order.get(a.id) ?? 0) - (id2order.get(b.id) ?? 0));
  return result;
}

export function resolveSearcher(options: {
  coordinator: Coordinator;
  table: string;
  searcher?: Searcher | null;
  idColumn: string;
  textColumn?: string | null;
  textColumns?: string[] | null;
  neighborsColumn?: string | null;
  vectorNeighborsEndpoint?: string | null;
}): Searcher {
  let {
    coordinator,
    table,
    idColumn,
    searcher,
    textColumn,
    textColumns,
    neighborsColumn,
    vectorNeighborsEndpoint,
  } = options;

  let result: Searcher = {};

  if (searcher != null && searcher.fullTextSearch != null) {
    result.fullTextSearch = searcher.fullTextSearch.bind(searcher);
  } else {
    let textColumnsForSearch: string[] = [];
    if (textColumns != null) {
      textColumnsForSearch.push(...textColumns);
    }
    if (textColumn != null && textColumnsForSearch.indexOf(textColumn) < 0) {
      textColumnsForSearch.unshift(textColumn);
    }
    // Remove duplicates while preserving order and drop invalid entries
    let seen = new Set<string>();
    textColumnsForSearch = textColumnsForSearch
      .filter((col): col is string => col != null && col !== "")
      .filter((col) => {
        if (seen.has(col)) {
          return false;
        }
        seen.add(col);
        return true;
      });
    if (textColumnsForSearch.length > 0) {
      let fts = new FullTextSearcher(coordinator, table, { id: idColumn, text: textColumnsForSearch });
      result.fullTextSearch = fts.fullTextSearch.bind(fts);
    }
  }

  if (searcher != null && searcher.nearestNeighbors != null) {
    result.nearestNeighbors = searcher.nearestNeighbors.bind(searcher);
  } else if (neighborsColumn != null) {
    // Search with pre-computed nearest neighbors.
    result.nearestNeighbors = async (id: any): Promise<{ id: any; distance: number }[]> => {
      try {
        let q = SQL.Query.from(table)
          .select({ knn: SQL.column(neighborsColumn) })
          .where(SQL.eq(SQL.column(idColumn), SQL.literal(id)))
          .limit(1);
        let result = await coordinator.query(q);
        let items: any[] = Array.from(result);
        if (items.length != 1 || items[0].knn == null) {
          return [];
        }
        let { distances, ids } = items[0].knn;
        let r = Array.from(ids ?? [])
          .map((nid, i) => {
            return { id: nid, distance: distances?.[i] };
          })
          .filter((x) => x.id != id && x.id != null);
        return r;
      } catch (error) {
        console.warn("Failed to resolve nearest neighbors from precomputed column.", error);
        return [];
      }
    };
  } else if (vectorNeighborsEndpoint != null) {
    let endpoint = vectorNeighborsEndpoint;
    result.nearestNeighbors = async (
      id: any,
      options: { limit?: number; predicate?: string | null; onStatus?: (status: string) => void } = {},
    ): Promise<{ id: any; distance?: number }[]> => {
      let limit = Math.max(1, Math.min(options.limit ?? DEFAULT_NEIGHBOR_LIMIT, DEFAULT_NEIGHBOR_LIMIT));
      options.onStatus?.("Searching neighbors...");
      try {
        let url = new URL(endpoint, typeof window !== "undefined" ? window.location.href : "http://localhost");
        url.searchParams.set("id", String(id));
        url.searchParams.set("k", String(Math.min(limit + 1, DEFAULT_NEIGHBOR_LIMIT)));
        let response = await fetch(url.toString());
        if (!response.ok) {
          throw new Error(`Failed with status ${response.status}`);
        }
        let payload = await response.json();
        let neighbors: any[] = Array.isArray(payload?.neighbors) ? payload.neighbors : [];
        return neighbors
          .filter((neighbor) => neighbor && neighbor.id != null)
          .map((neighbor) => ({
            id: neighbor.id,
            distance: typeof neighbor.distance === "number" ? neighbor.distance : undefined,
          }))
          .slice(0, limit);
      } catch (error) {
        console.warn("Failed to fetch nearest neighbors from endpoint.", error);
        return [];
      } finally {
        options.onStatus?.("");
      }
    };
  }

  return result;
}
