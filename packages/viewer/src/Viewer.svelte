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

onMount(async () => {
  try {
    let urlState = await getQueryPayload();
    status = "Initializing database...";
    config = await dataSource.initializeCoordinator(coordinator, "dataset", (s) => {
      status = s;
    });
    if (urlState != null) {
      initialState = urlState;
    } else if (config?.initialState != null) {
      initialState = config.initialState;
    } else {
      initialState = null;
    }
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
          <span class="text-sm text-slate-500 dark:text-slate-400">Dermatology Embedding Atlas</span>
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
