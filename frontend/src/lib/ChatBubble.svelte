<script lang="ts">
	let { role, content }: { role: 'user' | 'assistant'; content: string } = $props();
</script>

<!-- Phase 4: implement chat bubble -->
<div class="chat-bubble {role}">{content}</div>
