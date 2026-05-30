<script lang="ts">
	import { onMount, tick } from 'svelte';
	import BudgetBar from '$lib/BudgetBar.svelte';
	import ChatBubble from '$lib/ChatBubble.svelte';
	import SqlDisplay from '$lib/SqlDisplay.svelte';
	import ChartDisplay from '$lib/ChartDisplay.svelte';
	import MapDisplay from '$lib/MapDisplay.svelte';

	type MapPoint = {
		location: string;
		lat: number;
		lng: number;
		value: number;
		metric: string;
	};

	type MapTimeSeries = {
		periods: string[];
		frames: MapPoint[][];
		metric: string;
		time_col: string;
	};

	type MapStyle = { low: string; mid: string; high: string } | null;

	type Message = {
		id: number;
		role: 'user' | 'assistant';
		content: string;
		sql?: string;
		chart_html?: string | null;
		map_data?: MapPoint[] | null;
		map_time_series?: MapTimeSeries | null;
		map_style?: MapStyle;
		data_gap_warning?: boolean;
		thinking?: string[];
		thinking_duration?: number;
	};

	const PROMPT_GROUPS = [
		{
			label: 'Recent Trends',
			prompts: [
				'How did total session volume change year-over-year from 2022 to 2025?',
				'Which 3 locations had the fastest session growth from 2024 to 2025?',
				'Show monthly session trends for 2025 — which months saw the highest demand?',
			]
		},
		{
			label: 'Utilization',
			prompts: [
				'Which stations fell below half the network average sessions in 2025?',
				'What hour of day sees peak demand citywide, and which locations drive it?',
				'Compare weekend vs weekday session volume by location for 2025',
			]
		},
		{
			label: 'Expansion Planning',
			prompts: [
				'Rank locations by sessions per connector in 2025 — where should we add capacity?',
				'Show total sessions and energy delivered by location for 2025, ranked highest to lowest',
				'Which locations have grown the most since 2021 and may need infrastructure upgrades?',
			]
		},
		{
			label: 'Session Quality',
			prompts: [
				'How has median energy per session trended annually from 2021 to 2025?',
				'Which locations have the longest average session duration in 2025?',
				'What share of sessions are ROAMING vs PAID at each location in 2025?',
			]
		},
		{
			label: 'Behavior',
			prompts: [
				'In 2025, what share of drivers charged just once vs. regularly — and which locations have the highest share of repeat users?',
				'Which stations in 2025 had the most sessions with 30+ minutes of idle time after charging — and how many connector-hours were lost to overstay?',
				'Who are the top 10 heaviest users in 2025 by session count, and what are their average charge duration and idle time?',
			]
		},
	];

	function buildLandingCards() {
		const cards = PROMPT_GROUPS.map(g => ({
			label: g.label,
			prompt: g.prompts[Math.floor(Math.random() * g.prompts.length)]
		}));
		// 6th card: random group, avoid repeating the same prompt
		const gi = Math.floor(Math.random() * PROMPT_GROUPS.length);
		const g = PROMPT_GROUPS[gi];
		const alreadyShown = cards[gi].prompt;
		const others = g.prompts.filter(p => p !== alreadyShown);
		cards.push({
			label: 'Random Prompt',
			prompt: others[Math.floor(Math.random() * others.length)]
		});
		return cards;
	}

	const landingCards = buildLandingCards();

	let messages = $state<Message[]>([]);
	let input = $state('');
	let loading = $state(false);
	let warning = $state(false);
	let nextId = 0;
	let scrollEl: HTMLDivElement;
	let inputEl: HTMLInputElement;
	let showSavedPrompts = $state(false);
	let thinkingSteps = $state<string[]>([]);
	let thinkingCollapsed = $state<Record<number, boolean>>({});
	let selectedLocation = $state<string | null>(null);

	// Cumulative client-side token estimate — grows with every completed turn, never resets mid-session.
	// Estimated as (userMsg + assistantText + sql) chars ÷ 4 per turn (rough but monotonic).
	// Budget = max_history_turns × ~1000 tokens/turn (fetched from /api/status).
	let convTokens = $state(0);
	let convBudget = $state(10000); // updated from /api/status

	const convPct = $derived(convBudget > 0 ? Math.min(convTokens / convBudget, 1) : 0);
	const convWarning = $derived(convPct >= 0.75 && convPct < 1);
	const convExceeded = $derived(convPct >= 1);

	const latestChart = $derived(
		[...messages].reverse().find((m) => m.chart_html)?.chart_html ?? null
	);

	const latestMapData = $derived(
		[...messages].reverse().find((m) => m.map_data?.length)?.map_data ?? null
	);

	const latestMapTimeSeries = $derived(
		[...messages].reverse().find((m) => m.map_time_series?.frames?.length)?.map_time_series ?? null
	);

	const latestMapStyle = $derived(
		[...messages].reverse().find((m) => m.map_data?.length || m.map_time_series?.frames?.length)?.map_style ?? null
	);

	onMount(async () => {
		try {
			const res = await fetch('/api/status');
			if (res.ok) {
				const data = await res.json();
				warning = data.warning;
				if (data.max_history_turns) convBudget = data.max_history_turns * 1000;
			}
		} catch {}
		inputEl?.focus();
	});

	$effect(() => {
		void messages.length;
		void loading;
		void thinkingSteps.length;
		tick().then(() => {
			if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
		});
	});

	function clearConversation() {
		messages = [];
		convTokens = 0;
		thinkingCollapsed = {};
		thinkingSteps = [];
		selectedLocation = null;
		inputEl?.focus();
	}

	async function send(text: string) {
		text = text.trim();
		if (!text || loading || convExceeded) return;
		showSavedPrompts = false;

		// build history — append prior SQL query to assistant entries so the SQL generator
		// knows exact columns/filters used, without sending raw result rows (too large)
		const history = messages
			.filter((m) => m.role === 'user' || m.role === 'assistant')
			.map((m) => ({
				role: m.role,
				content:
					m.role === 'assistant' && m.sql
						? `${m.content}\n\n[SQL used: ${m.sql}]`
						: m.content
			}));

		messages.push({ id: ++nextId, role: 'user', content: text });
		input = '';
		loading = true;
		thinkingSteps = [];

		const startTime = Date.now();

		try {
			const res = await fetch('/api/chat/stream', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ message: text, history })
			});

			if (!res.ok || !res.body) {
				const data = await res.json().catch(() => ({}));
				messages.push({ id: ++nextId, role: 'assistant', content: (data as { error?: string }).error ?? 'Something went wrong.' });
				return;
			}

			const reader = res.body.getReader();
			const decoder = new TextDecoder();
			let buf = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				buf += decoder.decode(value, { stream: true });
				const lines = buf.split('\n');
				buf = lines.pop() ?? '';

				for (const line of lines) {
					if (!line.startsWith('data: ')) continue;
					try {
						const evt = JSON.parse(line.slice(6)) as Record<string, unknown>;
						if (evt.type === 'thinking') {
							thinkingSteps = [...thinkingSteps, evt.step as string];
						} else if (evt.type === 'answer') {
							const duration = Math.round((Date.now() - startTime) / 100) / 10;
							const msgId = ++nextId;
							thinkingCollapsed = { ...thinkingCollapsed, [msgId]: true };
							warning = evt.warning as boolean;
							// accumulate estimated tokens for this turn (chars ÷ 4)
							const answerText = (evt.answer as string) ?? '';
							const sqlText = (evt.sql as string) ?? '';
							convTokens += Math.ceil((text.length + answerText.length + sqlText.length) / 4);
							messages.push({
								id: msgId,
								role: 'assistant',
								content: evt.answer as string,
								sql: (evt.sql as string) || undefined,
								chart_html: (evt.chart_html as string | null) ?? null,
								map_data: (evt.map_data as MapPoint[] | null) ?? null,
								map_time_series: (evt.map_time_series as MapTimeSeries | null) ?? null,
								map_style: (evt.map_style as MapStyle) ?? null,
								data_gap_warning: (evt.data_gap_warning as boolean) ?? false,
								thinking: [...thinkingSteps],
								thinking_duration: duration,
							});
							loading = false;
						} else if (evt.type === 'error') {
							messages.push({ id: ++nextId, role: 'assistant', content: evt.error as string });
							loading = false;
						}
					} catch {}
				}
			}
		} catch {
			messages.push({ id: ++nextId, role: 'assistant', content: 'Network error — is the backend running?' });
		} finally {
			loading = false;
			thinkingSteps = [];
			tick().then(() => inputEl?.focus());
		}
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		send(input);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send(input);
		}
		if (e.key === 'Escape') showSavedPrompts = false;
	}
</script>

<div class="flex h-screen overflow-hidden" style="background: #fff;">

	<!-- LEFT: Chat panel -->
	<div class="flex flex-col" style="width: 42%; min-width: 320px; border-right: 1px solid rgba(0,0,0,0.08);">

		<!-- Header -->
		<header style="border-bottom: 1px solid rgba(0,0,0,0.08); background: #fff;">
			<div class="flex items-center justify-between px-5 py-4">
				<div>
					<p class="text-sm font-semibold" style="color: rgba(0,0,0,0.82);">NYC EV Intelligence</p>
					<p class="mt-0.5 text-[11px] font-medium uppercase tracking-widest" style="color: rgba(0,0,0,0.32);">
						Municipal Lots · 2021–2026
					</p>
				</div>
				{#if messages.length > 0}
					<button
						onclick={clearConversation}
						class="text-[11px] px-2.5 py-1 cursor-pointer transition-colors duration-150"
						style="color: rgba(0,0,0,0.36); border: 1px solid rgba(0,0,0,0.10);"
						onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.72)'; }}
						onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.36)'; }}
					>
						New chat
					</button>
				{/if}
			</div>
			<BudgetBar {warning} />
		</header>

		<!-- Message thread -->
		<div class="flex-1 overflow-y-auto" bind:this={scrollEl}>
			<div class="px-5 py-6">

				<!-- Empty state -->
				{#if messages.length === 0}
					<div class="flex flex-col items-center justify-center gap-6 min-h-[55vh]">
						<div class="text-center">
							<p class="text-base font-semibold" style="color: rgba(0,0,0,0.78);">NYC EV Charging — Strategic Analysis</p>
							<p class="mt-1.5 text-sm" style="color: rgba(0,0,0,0.50);">Data through May 2026 · Municipal lots</p>
						</div>
						<div class="grid grid-cols-2 gap-2.5 w-full max-w-sm">
							{#each landingCards as card}
								<button
									onclick={() => send(card.prompt)}
									class="cursor-pointer px-3.5 py-3.5 text-left transition-colors duration-150 flex flex-col gap-2"
									style="background: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.09);"
									onmouseenter={(e) => {
										(e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.06)';
										(e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,0,0,0.14)';
									}}
									onmouseleave={(e) => {
										(e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.03)';
										(e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,0,0,0.09)';
									}}
								>
									<span class="text-[11px] font-bold uppercase tracking-widest" style="color: rgba(0,80,200,0.75);">{card.label}</span>
									{#if card.label !== 'Random Prompt'}
										<span class="text-[13px] leading-snug" style="color: rgba(0,0,0,0.62);">{card.prompt}</span>
									{:else}
										<span class="text-[13px] leading-snug" style="color: rgba(0,0,0,0.28);">✦ surprise me</span>
									{/if}
								</button>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Messages -->
				<div class="space-y-5">
					{#each messages as msg (msg.id)}
						<div class={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
							<div class="max-w-[90%]">

								<!-- Thinking trace -->
								{#if msg.role === 'assistant' && msg.thinking?.length}
									<div class="mb-3 pl-3" style="border-left: 2px solid rgba(0,0,0,0.10);">
										<button
											onclick={() => { thinkingCollapsed = { ...thinkingCollapsed, [msg.id]: !(thinkingCollapsed[msg.id] ?? true) }; }}
											class="flex items-center gap-1.5 text-[11px] cursor-pointer select-none"
											style="color: rgba(0,0,0,0.32);"
										>
											<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
												{#if thinkingCollapsed[msg.id] ?? true}
													<polyline points="6 9 12 15 18 9"/>
												{:else}
													<polyline points="18 15 12 9 6 15"/>
												{/if}
											</svg>
											Thought for {msg.thinking_duration}s
										</button>
										{#if !(thinkingCollapsed[msg.id] ?? true)}
											<div class="mt-2 space-y-1.5">
												{#each msg.thinking as step}
													<div class="flex items-center gap-2 text-[11px]" style="color: rgba(0,0,0,0.28);">
														<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
															<polyline points="20 6 9 17 4 12"/>
														</svg>
														{step}
													</div>
												{/each}
											</div>
										{/if}
									</div>
								{/if}

								<ChatBubble role={msg.role} content={msg.content} />

								{#if msg.role === 'assistant' && msg.data_gap_warning}
									<div
										class="mt-2 flex items-start gap-2 px-3 py-2 text-xs leading-snug"
										style="background: rgba(251,191,36,0.10); border: 1px solid rgba(217,119,6,0.22); color: rgba(150,80,0,0.85);"
									>
										<svg class="mt-0.5 shrink-0" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
											<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
											<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
										</svg>
										<span>Data is only available through May 2026.</span>
									</div>
								{/if}

								{#if msg.role === 'assistant' && msg.sql}
									<SqlDisplay sql={msg.sql} />
								{/if}
							</div>
						</div>
					{/each}

					<!-- Live thinking trace -->
					{#if loading}
						<div class="flex justify-start">
							<div class="pl-3" style="border-left: 2px solid rgba(0,0,0,0.12);">
								{#if thinkingSteps.length === 0}
									<div class="flex items-center gap-1.5 py-1">
										<div class="h-1.5 w-1.5 animate-bounce delay-0" style="background: rgba(0,0,0,0.22);"></div>
										<div class="delay-150 h-1.5 w-1.5 animate-bounce" style="background: rgba(0,0,0,0.22);"></div>
										<div class="delay-300 h-1.5 w-1.5 animate-bounce" style="background: rgba(0,0,0,0.22);"></div>
									</div>
								{:else}
									<div class="text-[10px] font-bold uppercase tracking-widest mb-2" style="color: rgba(0,0,0,0.22);">Thinking</div>
									{#each thinkingSteps as step, i}
										<div class="flex items-center gap-2 text-[11px] py-0.5"
											style="color: {i === thinkingSteps.length - 1 ? 'rgba(0,0,0,0.65)' : 'rgba(0,0,0,0.30)'};">
											{#if i < thinkingSteps.length - 1}
												<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
													<polyline points="20 6 9 17 4 12"/>
												</svg>
											{:else}
												<div class="h-1.5 w-1.5 animate-pulse" style="background: currentColor;"></div>
											{/if}
											{step}
										</div>
									{/each}
								{/if}
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Input bar -->
		<div class="flex-none px-4 py-3" style="border-top: 1px solid rgba(0,0,0,0.08); background: #fff;">

			<!-- Analysis chip -->
			<div class="relative mb-2 flex items-center gap-2">
				<button
					onclick={() => (showSavedPrompts = !showSavedPrompts)}
					class="flex cursor-pointer items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium transition-colors duration-150 select-none"
					style="background: {showSavedPrompts ? 'rgba(0,80,200,0.08)' : 'rgba(0,0,0,0.05)'}; border: 1px solid {showSavedPrompts ? 'rgba(0,80,200,0.25)' : 'rgba(0,0,0,0.09)'}; color: {showSavedPrompts ? 'rgba(0,80,200,0.85)' : 'rgba(0,0,0,0.48)'};"
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
					</svg>
					Analysis
					<svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.55;">
						{#if showSavedPrompts}
							<polyline points="18 15 12 9 6 15"/>
						{:else}
							<polyline points="6 9 12 15 18 9"/>
						{/if}
					</svg>
				</button>

				{#if showSavedPrompts}
					<button
						class="fixed inset-0 z-10 cursor-default"
						onclick={() => (showSavedPrompts = false)}
						tabindex="-1"
						aria-hidden="true"
					></button>

					<div
						class="absolute bottom-full left-0 z-20 mb-2 w-80"
						style="background: #fff; border: 1px solid rgba(0,0,0,0.10); box-shadow: 0 -4px 24px rgba(0,0,0,0.10); max-width: calc(100vw - 2rem); max-height: 400px; overflow-y: auto;"
					>
						{#each PROMPT_GROUPS as group, gi}
							<div
								class="px-4 py-2"
								style="{gi > 0 ? 'border-top: 1px solid rgba(0,0,0,0.06);' : ''} background: rgba(0,0,0,0.02);"
							>
								<p class="text-[9px] font-bold uppercase tracking-widest" style="color: rgba(0,80,200,0.55);">
									{group.label}
								</p>
							</div>
							<div class="px-1 pb-1">
								{#each group.prompts as prompt}
									<button
										onclick={() => send(prompt)}
										class="flex w-full cursor-pointer items-start gap-2 px-3 py-2 text-left transition-colors duration-100"
										style="color: rgba(0,0,0,0.52);"
										onmouseenter={(e) => {
											(e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.04)';
											(e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.82)';
										}}
										onmouseleave={(e) => {
											(e.currentTarget as HTMLElement).style.background = 'transparent';
											(e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.52)';
										}}
									>
										<svg class="mt-0.5 shrink-0" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: rgba(0,80,200,0.50);">
											<polyline points="9 18 15 12 9 6"/>
										</svg>
										<span class="text-[11px] leading-snug">{prompt}</span>
									</button>
								{/each}
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<form
				class="flex items-center gap-3 px-4 py-2.5"
				style="background: #f0f0f0; border: 1px solid rgba(0,0,0,0.09);"
				onsubmit={handleSubmit}
			>
				<input
					bind:this={inputEl}
					bind:value={input}
					onkeydown={handleKeydown}
					type="text"
					placeholder={convExceeded ? 'Conversation full — start a new chat' : 'e.g. Which stations are underutilized in 2025?'}
					disabled={loading || convExceeded}
					maxlength={500}
					autocomplete="off"
					class="flex-1 bg-transparent text-sm outline-none disabled:opacity-40"
					style="color: rgba(0,0,0,0.82);"
				/>
				<!-- Context rectangle widget — cumulative client-side estimate, grows per turn -->
				{#if convTokens > 0}
					{@const pct = Math.round(convPct * 100)}
					{@const color = convExceeded ? 'rgba(220,38,38,0.80)' : convWarning ? 'rgba(217,119,6,0.78)' : 'rgba(0,0,0,0.38)'}
					{@const borderColor = convExceeded ? 'rgba(220,38,38,0.38)' : convWarning ? 'rgba(217,119,6,0.38)' : 'rgba(0,0,0,0.16)'}
					<div class="group relative flex-none cursor-default select-none">
						<!-- rectangle body -->
						<div
							class="flex h-7 flex-col justify-between px-1.5 pb-1 pt-1"
							style="width: 38px; border: 1px solid {borderColor};"
						>
							<!-- percent label -->
							<span
								class="block text-center text-[9px] font-semibold tabular-nums leading-none"
								style="color: {color};"
							>{pct}%</span>
							<!-- fill bar -->
							<div class="w-full overflow-hidden" style="height: 3px; background: rgba(0,0,0,0.09);">
								<div
									class="h-full transition-all duration-500"
									style="width: {pct}%; background: {color};"
								></div>
							</div>
						</div>
						<!-- hover tooltip -->
						<div
							class="pointer-events-none absolute bottom-full right-0 z-30 mb-1.5 whitespace-nowrap px-2 py-1 text-[10px] opacity-0 transition-opacity duration-100 group-hover:opacity-100"
							style="background: rgba(12,12,12,0.90); color: rgba(255,255,255,0.88);"
						>
							{convExceeded ? 'Conversation full — start a new chat' : `~${convTokens.toLocaleString()} / ${convBudget.toLocaleString()} tokens`}
						</div>
					</div>
				{/if}

				<button
					type="submit"
					disabled={loading || !input.trim() || convExceeded}
					class="flex h-7 w-7 flex-none cursor-pointer items-center justify-center text-white transition-opacity duration-150 disabled:cursor-not-allowed disabled:opacity-25"
					style="background: rgba(0,0,0,0.75);"
					onmouseenter={(e) => { if (!loading && input.trim()) (e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.90)'; }}
					onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.75)'; }}
				>
					{#if loading}
						<div class="h-3 w-3 animate-spin" style="border: 1.5px solid rgba(255,255,255,0.4); border-top-color: white;"></div>
					{:else}
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
						</svg>
					{/if}
				</button>
			</form>
		</div>
	</div>

	<!-- RIGHT: Chart + Map panel -->
	<div class="flex-1 flex flex-col overflow-hidden p-4 gap-3" style="background: #f5f5f5; border-left: 1px solid rgba(0,0,0,0.08);">

		{#if !latestChart && !latestMapData && !latestMapTimeSeries}
			<div class="flex flex-1 flex-col justify-between p-7 select-none">
			<div class="flex flex-col gap-6">
				<div>
					<p class="text-[11px] font-bold uppercase tracking-widest mb-3.5" style="color: rgba(0,0,0,0.48);">Data Coverage</p>
					<div class="space-y-4">
						<div class="flex items-start gap-3">
							<div class="mt-1.5 h-2 w-2 shrink-0" style="background: rgba(22,163,74,0.80);"></div>
							<div>
								<p class="text-sm font-semibold" style="color: rgba(0,0,0,0.78);">Complete — 2021 to 2025</p>
								<p class="text-xs mt-1" style="color: rgba(0,0,0,0.55); line-height: 1.55;">Full-year sessions available. Use 2025 as the baseline for all YoY comparisons.</p>
							</div>
						</div>
						<div class="flex items-start gap-3">
							<div class="mt-1.5 h-2 w-2 shrink-0" style="background: rgba(217,119,6,0.80);"></div>
							<div>
								<p class="text-sm font-semibold" style="color: rgba(0,0,0,0.78);">Partial — Jan to May 2026</p>
								<p class="text-xs mt-1" style="color: rgba(0,0,0,0.55); line-height: 1.55;">Incomplete year. Totals will undercount vs prior years — avoid using as a trend baseline.</p>
							</div>
						</div>
						<div class="flex items-start gap-3">
							<div class="mt-1.5 h-2 w-2 shrink-0" style="background: rgba(59,130,246,0.80);"></div>
							<div>
								<p class="text-sm font-semibold" style="color: rgba(0,0,0,0.78);">9 municipal parking lots · NYC DOT</p>
								<p class="text-xs mt-1" style="color: rgba(0,0,0,0.55); line-height: 1.55;">PlugNYC program. Includes PAID and ROAMING sessions. DISCONNECTED excluded from utilization counts.</p>
							</div>
						</div>
					</div>
				</div>

				<div class="pt-4" style="border-top: 1px solid rgba(0,0,0,0.09);">
					<p class="text-[11px] font-bold uppercase tracking-widest mb-3.5" style="color: rgba(0,0,0,0.42);">Known Limitations</p>
					<ul class="space-y-3.5">
						<li class="flex items-start gap-2.5 text-xs" style="color: rgba(0,0,0,0.58);">
							<span class="shrink-0 mt-0.5 font-medium" style="color: rgba(0,0,0,0.32);">—</span>
							<span style="line-height: 1.6;">
								<span class="font-semibold" style="color: rgba(0,0,0,0.72);">Idle time is sparse.</span>
								{' '}An <code style="font-size:11px; background:rgba(0,0,0,0.06); padding: 1px 4px;">idle_time_min</code> column exists — time parked after charging completed — but non-zero coverage collapsed from ~52% of sessions in 2021 to ~9% in 2024, likely due to EVSE firmware changes. Use it for single-year spot checks; avoid year-over-year idle comparisons.
							</span>
						</li>
						<li class="flex items-start gap-2.5 text-xs" style="color: rgba(0,0,0,0.58);">
							<span class="shrink-0 mt-0.5 font-medium" style="color: rgba(0,0,0,0.32);">—</span>
							<span style="line-height: 1.6;">
								<span class="font-semibold" style="color: rgba(0,0,0,0.72);">Energy is right-skewed.</span>
								{' '}A small share of sessions report implausibly high kWh — likely meter errors or multi-session aggregation artifacts. Median per session sits around 40 kWh; the mean runs significantly higher. Always use <code style="font-size:11px; background:rgba(0,0,0,0.06); padding: 1px 4px;">MEDIAN</code> for typical-session energy analysis.
							</span>
						</li>
						<li class="flex items-start gap-2.5 text-xs" style="color: rgba(0,0,0,0.58);">
							<span class="shrink-0 mt-0.5 font-medium" style="color: rgba(0,0,0,0.32);">—</span>
							<span style="line-height: 1.6;">
								<span class="font-semibold" style="color: rgba(0,0,0,0.72);">No demand-side signal.</span>
								{' '}The dataset records completed sessions only. Vehicles turned away from full lots leave no trace — a high-utilization station may have substantially more unmet demand than its session count implies. Saturation analysis should be paired with connector-count data.
							</span>
						</li>
						<li class="flex items-start gap-2.5 text-xs" style="color: rgba(0,0,0,0.58);">
							<span class="shrink-0 mt-0.5 font-medium" style="color: rgba(0,0,0,0.32);">—</span>
							<span style="line-height: 1.6;">
								<span class="font-semibold" style="color: rgba(0,0,0,0.72);">Two duration columns, different meanings.</span>
								{' '}<code style="font-size:11px; background:rgba(0,0,0,0.06); padding: 1px 4px;">charge_duration_min</code> is active charging time; <code style="font-size:11px; background:rgba(0,0,0,0.06); padding: 1px 4px;">connected_duration_min</code> is total plug-in time (charge + idle). Using the wrong one overstates or understates station occupancy.
							</span>
						</li>
					</ul>
				</div>
			</div>

				<p class="text-[11px] text-center" style="color: rgba(0,0,0,0.32);">Charts and maps appear here as you ask data questions</p>
			</div>
		{/if}

		<!-- Chart card -->
		{#if latestChart}
			<div
				class="{latestMapData || latestMapTimeSeries ? 'flex-none' : 'flex-1 min-h-0'} overflow-hidden"
				style="{latestMapData || latestMapTimeSeries ? 'height: calc(55% - 6px);' : ''}background: #fff; border: 1px solid rgba(0,0,0,0.08);"
			>
				<div
					class="flex items-center gap-2 px-4 py-2.5"
					style="background: #f8f8f8; border-bottom: 1px solid rgba(0,0,0,0.07);"
				>
					<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color: rgba(0,60,160,0.45);">
						<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
					</svg>
					<span class="text-[10px] font-bold uppercase tracking-widest" style="color: rgba(0,50,140,0.50);">Chart</span>
				</div>
				<ChartDisplay chart_html={latestChart} {selectedLocation} onselect={(loc) => (selectedLocation = loc)} />
			</div>
		{/if}

		<!-- Map card -->
		{#if latestMapData || latestMapTimeSeries}
			<div
				class="flex-1 min-h-0 flex flex-col overflow-hidden"
				style="background: #fff; border: 1px solid rgba(0,0,0,0.08);"
			>
				<div
					class="flex-none flex items-center gap-2 px-4 py-2.5"
					style="background: #f8f8f8; border-bottom: 1px solid rgba(0,0,0,0.07);"
				>
					<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color: rgba(0,120,60,0.55);">
						<circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"/>
					</svg>
					<span class="text-[10px] font-bold uppercase tracking-widest" style="color: rgba(0,100,50,0.55);">Map</span>
					{#if latestMapTimeSeries}
						<span
							class="ml-1.5 px-2 py-0.5 text-[9px] font-semibold"
							style="background: rgba(0,130,70,0.08); color: rgba(0,100,50,0.65);"
						>
							{latestMapTimeSeries.periods[0]}–{latestMapTimeSeries.periods[latestMapTimeSeries.periods.length - 1]}
						</span>
						<span class="ml-1 text-[9px]" style="color: rgba(0,0,0,0.28);">animated · {latestMapTimeSeries.periods.length} {latestMapTimeSeries.time_col}s</span>
						<span class="ml-auto text-[9px]" style="color: rgba(0,0,0,0.28);">
							{latestMapTimeSeries.metric.replace(/_/g, ' ')}
						</span>
					{:else if latestMapData}
						<span
							class="ml-1.5 px-2 py-0.5 text-[9px] font-semibold"
							style="background: rgba(0,130,70,0.08); color: rgba(0,100,50,0.65);"
						>
							{latestMapData.length} {latestMapData.length === 1 ? 'location' : 'locations'}
						</span>
						{#if latestMapData[0]?.metric}
							<span class="ml-auto text-[9px]" style="color: rgba(0,0,0,0.28);">
								{latestMapData[0].metric.replace(/_/g, ' ')}
							</span>
						{/if}
					{/if}
				</div>
				<div class="flex-1 min-h-0">
					<MapDisplay points={latestMapData ?? []} timeSeries={latestMapTimeSeries} mapStyle={latestMapStyle} {selectedLocation} onselect={(loc) => (selectedLocation = loc)} />
				</div>
			</div>
		{/if}
	</div>

</div>
