<script lang="ts">
	let { sql }: { sql: string } = $props();
	let open = $state(false);
</script>

<div class="mt-1">
	<button
		onclick={() => (open = !open)}
		class="flex cursor-pointer items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider transition-colors duration-150"
		style="color: rgba(0,80,200,0.45);"
		onmouseenter={(e) => ((e.currentTarget as HTMLElement).style.color = 'rgba(0,80,200,0.80)')}
		onmouseleave={(e) => ((e.currentTarget as HTMLElement).style.color = 'rgba(0,80,200,0.45)')}
	>
		<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
			{#if open}
				<polyline points="18 15 12 9 6 15"/>
			{:else}
				<polyline points="6 9 12 15 18 9"/>
			{/if}
		</svg>
		SQL query
	</button>
	{#if open}
		<pre
			class="mt-1.5 overflow-x-auto px-4 py-3 text-[11px] leading-relaxed"
			style="background: rgba(0,80,200,0.05); border: 1px solid rgba(0,80,200,0.12); color: #0044bb; font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;"
		>{sql}</pre>
	{/if}
</div>
