<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	let {
		chart_html,
		selectedLocation = null,
		onselect
	}: {
		chart_html: string | null;
		selectedLocation?: string | null;
		onselect?: (loc: string | null) => void;
	} = $props();

	let iframeEl = $state<HTMLIFrameElement | null>(null);

	function handleMessage(e: MessageEvent) {
		if (!iframeEl || e.source !== iframeEl.contentWindow) return;
		if (e.data?.type === 'ev_click') {
			const loc = e.data.location as string | null;
			// toggle: clicking same location again deselects
			onselect?.(loc === selectedLocation ? null : loc);
		}
	}

	onMount(() => window.addEventListener('message', handleMessage));
	onDestroy(() => window.removeEventListener('message', handleMessage));

	// When selectedLocation changes externally, tell the iframe to highlight
	$effect(() => {
		iframeEl?.contentWindow?.postMessage({ type: 'ev_highlight', location: selectedLocation }, '*');
	});
</script>

{#if chart_html}
	<iframe
		bind:this={iframeEl}
		srcdoc={chart_html}
		sandbox="allow-scripts"
		scrolling="no"
		style="width: 100%; height: 460px; border: none; display: block;"
		title="Chart"
	></iframe>
{/if}
