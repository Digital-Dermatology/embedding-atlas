<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  import { coordinator as defaultCoordinator } from "@uwdata/mosaic-core";
  import { onMount } from "svelte";

  import EmbeddingAtlas from "./lib/EmbeddingAtlas.svelte";
  import Spinner from "./lib/Spinner.svelte";

  import type { DataSource } from "./data_source.js";
  import type { EmbeddingAtlasProps, EmbeddingAtlasState } from "./lib/api.js";
  import { systemDarkMode } from "./lib/dark_mode_store.js";
  import { type ExportFormat } from "./lib/mosaic_exporter.js";
  import { debounce } from "./lib/utils.js";
  import { getQueryPayload, setQueryPayload } from "./query_payload.js";
  import skinmapLogo from "./assets/atlas.png";

  const coordinator = defaultCoordinator();

  interface Props {
    dataSource: DataSource;
  }

  let { dataSource }: Props = $props();

  let ready = $state(false);
  let error = $state(false);
  let status = $state("Loading...");
  let initialState: any | null = $state.raw(null);
  let config: Partial<EmbeddingAtlasProps> | null = $state.raw(null);
  let activeRoute: string | null = $state(null);
  let routeTabs: { label: string; route: string | null; href: string }[] = $state([]);

  type RouteSource = "query" | "path" | null;

  function routeLabel(route: string | null) {
    if (!route || route.toLowerCase() === "atlas") {
      return "Atlas";
    }
    return route
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function routeHref(route: string | null) {
    if (!route || route.toLowerCase() === "atlas") {
      return "/";
    }
    return `/${encodeURIComponent(route)}`;
  }

  function buildRouteTabs(cfg: Partial<EmbeddingAtlasProps> | null, currentRoute: string | null) {
    const variants = cfg?.initialStateVariants ?? null;
    const routes = variants ? Object.keys(variants) : [];
    const seen = new Set<string>();
    const tabs: { label: string; route: string | null; href: string }[] = [];
    if (currentRoute && !routes.includes(currentRoute)) {
      routes.push(currentRoute);
    }
    routes.unshift(null as unknown as string);
    routes.forEach((route) => {
      const trimmed = route?.trim() ?? null;
      const normalizedRoute = trimmed && trimmed.toLowerCase() === "atlas" ? null : trimmed;
      const seenKey = normalizedRoute ? normalizedRoute.toLowerCase() : "__root__";
      if (seen.has(seenKey)) {
        return;
      }
      seen.add(seenKey);
      tabs.push({
        label: routeLabel(normalizedRoute),
        route: normalizedRoute,
        href: routeHref(normalizedRoute),
      });
    });
    return tabs;
  }

  function atlasRouteFromQuery(): string | null {
    if (typeof window === "undefined" || !window.location) {
      return null;
    }
    try {
      const params = new URL(window.location.href).searchParams;
      const value = params.get("atlas_route");
      if (value && value.trim()) {
        return value.trim();
      }
    } catch (_err) {
      return null;
    }
    return null;
  }

  function currentPathSegment(): string | null {
    if (typeof window === "undefined" || !window.location) {
      return null;
    }
    let pathname = window.location.pathname ?? "";
    pathname = pathname.replace(/^\/+/, "");
    if (!pathname) {
      return null;
    }
    const [segment] = pathname.split("/");
    return segment || null;
  }

  function normalizeLocation(source: RouteSource) {
    if (typeof window === "undefined" || typeof window.history === "undefined") {
      return;
    }
    try {
      const url = new URL(window.location.href);
      let changed = false;
      if (source === "query" || source === "path") {
        if (url.searchParams.has("atlas_route")) {
          url.searchParams.delete("atlas_route");
          changed = true;
        }
        if (url.pathname !== "/") {
          url.pathname = "/";
          changed = true;
        }
      }
      if (!changed) {
        return;
      }
      window.history.replaceState(
        window.history.state,
        "",
        url.pathname + url.search + url.hash,
      );
    } catch (_err) {
      // ignore cleanup errors
    }
  }

  function cloneState<T>(value: T): T {
    if (value == null) {
      return value;
    }
    const structured = (globalThis as any).structuredClone;
    if (typeof structured === "function") {
      return structured(value);
    }
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (_err) {
      return value;
    }
  }

  function resolveInitialState(cfg: Partial<EmbeddingAtlasProps> | null) {
    activeRoute = null;
    if (!cfg) {
      return null;
    }
    const querySegment = atlasRouteFromQuery();
    const pathSegment = currentPathSegment();
    const segment = querySegment ?? pathSegment;
    const source: RouteSource = querySegment ? "query" : pathSegment ? "path" : null;
    const variants = cfg.initialStateVariants ?? null;
    if (segment && variants && variants[segment] != null) {
      activeRoute = segment;
      normalizeLocation(source);
      return cloneState(variants[segment]);
    }
    normalizeLocation(null);
    if (segment) {
      activeRoute = segment;
    }
    if (cfg.initialState != null) {
      return cloneState(cfg.initialState);
    }
    return null;
  }

onMount(async () => {
  try {
    let urlState = await getQueryPayload();
    status = "Initializing database...";
    config = await dataSource.initializeCoordinator(coordinator, "dataset", (s) => {
      status = s;
    });
    if (urlState != null) {
      activeRoute = atlasRouteFromQuery() ?? currentPathSegment();
      initialState = urlState;
    } else {
      initialState = resolveInitialState(config);
    }
    routeTabs = buildRouteTabs(config, activeRoute);
    ready = true;
  } catch (e: any) {
    error = true;
    status = e.message;
    return;
  }
});

  async function onExportSelection(predicate: string | null, format: ExportFormat) {
    if (dataSource.downloadSelection) {
      await dataSource.downloadSelection(predicate, format);
    }
  }

  async function onDownloadArchive() {
    if (dataSource.downloadArchive) {
      await dataSource.downloadArchive();
    }
  }

  function onStateChange(state: EmbeddingAtlasState) {
    setQueryPayload({ ...state, predicate: undefined });
  }
</script>

<div class="fixed left-0 right-0 top-0 bottom-0">
  {#if ready && config != null}
    <EmbeddingAtlas
      searchColumns={config.searchColumns}
      uploadSearch={config.uploadSearch}
      coordinator={coordinator}
      data={{
        ...(config.data ?? { id: "id" }),
        // table is loaded with the name "dataset" above.
        table: "dataset",
      }}
      embeddingViewConfig={config.embeddingViewConfig}
      embeddingViewLabels={config.embeddingViewLabels}
      assets={config.assets}
      initialState={initialState}
      onExportApplication={dataSource.downloadArchive ? onDownloadArchive : null}
      onExportSelection={dataSource.downloadSelection ? onExportSelection : null}
      onStateChange={debounce(onStateChange, 200)}
      cache={dataSource.cache}
      activeRoute={activeRoute}
      routeTabs={routeTabs}
    />
  {:else}
    <div
      class="w-full h-full grid place-content-center select-none text-slate-800 bg-slate-200 dark:text-slate-200 dark:bg-slate-800"
      class:dark={$systemDarkMode}
    >
      <div class="flex flex-col items-center gap-6 text-center">
        <img src={skinmapLogo} alt="SkinMap logo" class="w-32 h-auto rounded-xl" />
        <div class="flex flex-col items-center gap-1">
          <span class="text-2xl font-semibold tracking-wide">SkinMap</span>
          <span class="text-sm text-slate-500 dark:text-slate-400">Dermatology Atlas</span>
        </div>
        {#if error}
          <div class="max-w-md text-red-500 dark:text-red-400">{status}</div>
        {:else}
          <div class="w-72 flex justify-center">
            <Spinner status={status} />
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
