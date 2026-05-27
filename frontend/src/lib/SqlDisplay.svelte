<script lang="ts">
	let { sql }: { sql: string } = $props();
	let open = $state(false);
</script>

<!-- Phase 4: collapsible SQL block -->
<div>
	<button onclick={() => (open = !open)} class="text-xs text-gray-500 hover:text-gray-300">
		Query used: [{open ? 'hide' : 'show'}]
	</button>
	{#if open}
		<pre class="text-xs mt-1 p-2 bg-gray-900 rounded overflow-x-auto">{sql}</pre>
	{/if}
</div>
