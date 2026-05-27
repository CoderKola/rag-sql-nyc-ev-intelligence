<script lang="ts">
	let { warning = false }: { warning?: boolean } = $props();
</script>

<!-- Phase 4: budget warning banner -->
{#if warning}
	<div class="bg-amber-900/40 border border-amber-700 text-amber-300 text-xs px-4 py-2 text-center">
		Demo budget running low — may be unavailable soon
	</div>
{/if}
