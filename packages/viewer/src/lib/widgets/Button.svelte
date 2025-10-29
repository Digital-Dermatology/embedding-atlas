<!-- Copyright (c) 2025 Apple Inc. Licensed under MIT License. -->
<script lang="ts">
  interface Props {
    label?: string | null;
    icon?: any | null;
    title?: string;
    order?: number | null;
    style?: string;
    class?: string | null;
    onClick?: () => void;
    disabled?: boolean;
  }

  let {
    label = null,
    icon = null,
    title = "",
    order = null,
    style = "default",
    onClick,
    class: additionalClasses,
    disabled = false,
  }: Props = $props();

  const styles: Record<string, string> = {
    default:
      "bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 dark:text-slate-400 focus-visible:outline-2 outline-blue-600 -outline-offset-1",
    plotCell:
      "bg-white text-slate-400 border-slate-300 hover:text-slate-500 hover:border-slate-500 dark:text-slate-500 dark:border-slate-500 dark:bg-slate-800 dark:hover:border-slate-300 dark:hover:text-slate-300",
    plotCellClose: "bg-white text-red-500 border-red-500 hover:text-white hover:bg-red-500 dark:bg-slate-800",
  };
</script>

<button
  class="rounded-md px-1.5 py-1.5 h-[28px] flex select-none items-center border {styles[style]} {additionalClasses ??
    ''}"
  style:order={order}
  title={title}
  disabled={disabled}
  aria-disabled={disabled}
  onclick={() => {
    if (!disabled) {
      onClick?.();
    }
  }}
>
  {#if icon != null}
    {@const SvelteComponent = icon}
    <SvelteComponent class="w-5 h-5" />
  {/if}
  {#if label != null && label != ""}
    <span class:ml-1={icon != null}>{label}</span>
  {/if}
</button>
