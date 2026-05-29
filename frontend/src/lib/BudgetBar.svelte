<script lang="ts">
	let { warning = false }: { warning?: boolean } = $props();
</script>

{#if warning}
	<div
		class="flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium"
		style="background: rgba(251,191,36,0.10); border-top: 1px solid rgba(217,119,6,0.22); color: rgba(150,80,0,0.85);"
	>
		<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
			<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
		</svg>
		Demo budget running low — may be unavailable soon
	</div>
{/if}
