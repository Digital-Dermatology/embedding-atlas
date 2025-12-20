// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import type { Coordinator } from "@uwdata/mosaic-core";
import * as SQL from "@uwdata/mosaic-sql";

import type { DataSource } from "./data_source.js";
import type { EmbeddingAtlasProps } from "./lib/api.js";
import { initializeDatabase } from "./lib/database_utils.js";
import { exportMosaicSelection, filenameForSelection, type ExportFormat } from "./lib/mosaic_exporter.js";
import { downloadBuffer } from "./lib/utils.js";

function joinUrl(a: string, b: string) {
  if (b.startsWith(".")) {
    b = b.slice(1);
  }
  if (a.endsWith("/") && b.startsWith("/")) {
    return a + b.slice(1);
  } else if (!a.endsWith("/") && !b.startsWith("/")) {
    return a + "/" + b;
  } else {
    return a + b;
  }
}

interface Metadata {
  props: Partial<EmbeddingAtlasProps>;

  isStatic?: boolean;
  database?: {
    type: "wasm" | "socket" | "rest";
    uri?: string;
    load?: boolean;
  };
  uploadSearch?: EmbeddingAtlasProps["uploadSearch"];
}

export class BackendDataSource implements DataSource {
  private serverUrl: string;
  private serverUrlCandidates: string[];
  downloadArchive: (() => Promise<void>) | undefined = undefined;
  downloadSelection: ((predicate: string | null, format: ExportFormat) => Promise<void>) | undefined = undefined;

  constructor(serverUrl: string) {
    if (serverUrl.startsWith("http")) {
      this.serverUrl = serverUrl;
      this.serverUrlCandidates = [serverUrl];
      return;
    }

    const originBase = new URL(serverUrl, window.location.origin + "/").toString();
    const hrefBase = new URL(serverUrl, window.location.href).toString();

    const candidates = [originBase, hrefBase];
    const seen = new Set<string>();
    this.serverUrlCandidates = candidates.filter((url) => {
      if (seen.has(url)) {
        return false;
      }
      seen.add(url);
      return true;
    });
    this.serverUrl = this.serverUrlCandidates[0];
  }

  async initializeCoordinator(
    coordinator: Coordinator,
    table: string,
    onStatus: (message: string) => void,
  ): Promise<Partial<EmbeddingAtlasProps>> {
    let metadata = await this.metadata();
    if (metadata.props?.assets?.images) {
      let relative = metadata.props.assets.images.relativePath ?? "images";
      let baseUrl = joinUrl(this.serverUrl, relative);
      metadata.props.assets.images = {
        ...metadata.props.assets.images,
        baseUrl: baseUrl,
      };
    }

    if (metadata.props?.data?.vectorNeighborsEndpoint) {
      metadata.props.data.vectorNeighborsEndpoint = joinUrl(
        this.serverUrl,
        metadata.props.data.vectorNeighborsEndpoint,
      );
    }
    if (metadata.props?.data?.textSearchEndpoint) {
      metadata.props.data.textSearchEndpoint = joinUrl(
        this.serverUrl,
        metadata.props.data.textSearchEndpoint,
      );
    }

    onStatus("Initializing DuckDB...");
    let dbType = metadata.database?.type ?? "wasm";
    await initializeDatabase(coordinator, dbType, metadata.database?.uri ?? joinUrl(this.serverUrl, "query"));

    if (metadata.database?.load) {
      onStatus("Loading data...");
      let datasetUrl = joinUrl(this.serverUrl, "dataset.parquet");
      await coordinator.exec(`
        CREATE OR REPLACE TABLE ${table} AS (SELECT * FROM read_parquet(${SQL.literal(datasetUrl)}));
      `);
    }

    if (!metadata.isStatic) {
      this.downloadArchive = async () => {
        let resp = await this.fetchEndpoint("archive.zip");
        let data = await resp.arrayBuffer();
        downloadBuffer(data, "embedding-atlas.zip");
      };
    }

    if (dbType == "wasm") {
      this.downloadSelection = async (predicate, format) => {
        let [bytes, name] = await exportMosaicSelection(coordinator, table, predicate, format);
        downloadBuffer(bytes, name);
      };
    } else if (!metadata.isStatic) {
      this.downloadSelection = async (predicate, format) => {
        let name = filenameForSelection(format);
        let resp = await this.fetchEndpoint("selection", {
          method: "POST",
          body: JSON.stringify({ predicate: predicate, format: format }),
        });
        let data = await resp.arrayBuffer();
        downloadBuffer(data, name);
      };
    }

    let props: Partial<EmbeddingAtlasProps> = metadata.props ?? {};
    if (metadata.uploadSearch) {
      props = { ...props, uploadSearch: metadata.uploadSearch };
    }
    return props;
  }

  private async fetchEndpoint(endpoint: string, init?: RequestInit) {
    let resp = await fetch(joinUrl(this.serverUrl, endpoint), init);
    if (resp.status != 200) {
      const error: any = new Error(`Request failed (${resp.status})`);
      error.status = resp.status;
      throw error;
    }
    return resp;
  }

  private async metadata(): Promise<Metadata> {
    let lastError: unknown = null;
    for (let i = 0; i < this.serverUrlCandidates.length; i++) {
      this.serverUrl = this.serverUrlCandidates[i];
      try {
        const result = await this.fetchEndpoint("metadata.json").then((x) => x.json());
        if (i !== 0) {
          this.serverUrlCandidates.splice(0, this.serverUrlCandidates.length, this.serverUrl);
        }
        return result;
      } catch (err) {
        lastError = err;
      }
    }
    throw new Error("Network Error: Failed to fetch dataset metadata");
  }

  async cacheGet(key: string) {
    try {
      return await this.fetchEndpoint("cache/" + key).then((x) => x.json());
    } catch (e) {
      return null;
    }
  }

  async cacheSet(key: string, value: any) {
    try {
      await this.fetchEndpoint("cache/" + key, {
        method: "POST",
        body: JSON.stringify(value),
      });
    } catch (e) {
      // Ignore set cache errors.
    }
  }

  cache = {
    get: (key: string) => this.cacheGet(key),
    set: (key: string, value: any) => this.cacheSet(key, value),
  };
}
