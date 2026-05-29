<script lang="ts">
	import { marked } from 'marked';

	let { role, content }: { role: 'user' | 'assistant'; content: string } = $props();

	function processHtml(raw: string): string {
		let html = marked.parse(raw) as string;
		html = html.replace(
			/<h3>([^<]*key finding[s]?[^<]*)<\/h3>/gi,
			'<h3 class="key-findings">$1</h3>'
		);
		html = html.replace(
			/<h3>([^<]*limitation[s]?[^<]*)<\/h3>/gi,
			'<h3 class="limitations">$1</h3>'
		);
		html = html.replace(
			/<h3>([^<]*recommendation[s]?[^<]*)<\/h3>/gi,
			'<h3 class="recommendation">$1</h3>'
		);
		return html;
	}

	const html = $derived(role === 'assistant' ? processHtml(content) : null);
</script>

{#if role === 'user'}
	<div
		class="px-4 py-2.5 text-sm leading-relaxed"
		style="background: #1a1a1a; color: rgba(255,255,255,0.90);"
	>
		{content}
	</div>
{:else}
	<div class="md text-sm leading-relaxed" style="color: rgba(0,0,0,0.78);">
		{@html html}
	</div>
{/if}
