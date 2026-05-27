<script lang="ts">
	let { chart_html }: { chart_html: string | null } = $props();
</script>

<!-- Phase 4: render Plotly HTML -->
{#if chart_html}
	<div>{@html chart_html}</div>
{/if}
