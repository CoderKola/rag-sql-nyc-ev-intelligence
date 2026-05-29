<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

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

	let {
		points = [],
		timeSeries = null,
		selectedLocation = null,
		mapStyle = null,
		onselect
	}: {
		points?: MapPoint[];
		timeSeries?: MapTimeSeries | null;
		selectedLocation?: string | null;
		mapStyle?: MapStyle;
		onselect?: (loc: string | null) => void;
	} = $props();

	let container: HTMLDivElement;
	let map: maplibregl.Map | null = null;
	let popup: maplibregl.Popup | null = null;

	// Playback state
	let frameIndex = $state(0);
	let playing = $state(false);
	let playTimer: ReturnType<typeof setInterval> | null = null;

	function playInterval(): number {
		const n = timeSeries?.periods.length ?? 0;
		return n > 18 ? 600 : n > 12 ? 800 : 1200;
	}
	const CARTO_VOYAGER = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json';
	const NYC_CENTER: [number, number] = [-73.95, 40.73];
	const NYC_ZOOM = 10.5;

	function formatMetric(metric: string): string {
		return metric
			.replace(/_/g, ' ')
			.replace(/\bkwh\b/gi, 'kWh')
			.replace(/\bmin\b/gi, 'min')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	function formatValue(value: number, metric: string): string {
		if (metric.includes('kwh') || metric.includes('energy')) {
			return value.toLocaleString(undefined, { maximumFractionDigits: 1 }) + ' kWh';
		}
		if (metric.includes('min') || metric.includes('duration')) {
			return value.toLocaleString(undefined, { maximumFractionDigits: 1 }) + ' min';
		}
		return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
	}

	function colors() {
		return {
			low:  mapStyle?.low  ?? '#60AEFF',
			mid:  mapStyle?.mid  ?? '#007AFF',
			high: mapStyle?.high ?? '#0040B8',
		};
	}

	function buildGeoJSON(pts: MapPoint[]): GeoJSON.FeatureCollection {
		const maxVal = Math.max(...pts.map((p) => p.value), 1);
		return {
			type: 'FeatureCollection',
			features: pts.map((p) => ({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
				properties: {
					location: p.location,
					value: p.value,
					metric: p.metric,
					normalised: p.value / maxVal
				}
			}))
		};
	}

	function fitToPoints(pts: MapPoint[]) {
		if (!map || pts.length === 0) return;
		if (pts.length === 1) {
			map.flyTo({ center: [pts[0].lng, pts[0].lat], zoom: 14, duration: 900, essential: true });
		} else {
			const bounds = new maplibregl.LngLatBounds();
			pts.forEach((p) => bounds.extend([p.lng, p.lat]));
			map.fitBounds(bounds, { padding: { top: 48, bottom: 48, left: 48, right: 48 }, duration: 900, maxZoom: 13 });
		}
	}

	function applyPoints(pts: MapPoint[], fit = false) {
		if (!map) return;
		const geojson = buildGeoJSON(pts);
		const src = map.getSource('ev-points') as maplibregl.GeoJSONSource | undefined;
		if (src) {
			src.setData(geojson);
			if (fit) fitToPoints(pts);
		} else {
			map.addSource('ev-points', { type: 'geojson', data: geojson });

			const c = colors();
			map.addLayer({
				id: 'ev-halo',
				type: 'circle',
				source: 'ev-points',
				paint: {
					'circle-radius': ['interpolate', ['linear'], ['get', 'normalised'], 0, 14, 1, 50],
					'circle-color': c.mid,
					'circle-opacity': 0.12,
					'circle-blur': 1
				}
			});

			map.addLayer({
				id: 'ev-circles',
				type: 'circle',
				source: 'ev-points',
				paint: {
					'circle-radius': ['interpolate', ['linear'], ['get', 'normalised'], 0, 7, 1, 28],
					'circle-color': [
						'interpolate', ['linear'], ['get', 'normalised'],
						0, c.low, 0.5, c.mid, 1, c.high
					],
					'circle-opacity': 0.85,
					'circle-stroke-width': 1.5,
					'circle-stroke-color': 'rgba(255,255,255,0.90)'
				}
			});

			map.addLayer({
				id: 'ev-labels',
				type: 'symbol',
				source: 'ev-points',
				layout: {
					'text-field': ['get', 'location'],
					'text-size': 10,
					'text-offset': [0, 2.2],
					'text-anchor': 'top',
					'text-max-width': 12
				},
				paint: {
					'text-color': '#0A1E46',
					'text-halo-color': 'rgba(255,255,255,0.9)',
					'text-halo-width': 1.5
				}
			});

			map.on('click', 'ev-circles', (e) => {
				const feature = e.features?.[0];
				if (!feature) return;
				const loc = feature.properties.location as string;
				onselect?.(loc === selectedLocation ? null : loc);
			});

			map.on('mouseenter', 'ev-circles', (e) => {
				map!.getCanvas().style.cursor = 'pointer';
				const feature = e.features?.[0];
				if (!feature) return;
				const { location, value, metric } = feature.properties as {
					location: string; value: number; metric: string;
				};
				popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 })
					.setLngLat(e.lngLat)
					.setHTML(
						`<div style="font-family:system-ui;font-size:12px;line-height:1.5;color:#0A1E46;">
							<div style="font-weight:600;margin-bottom:2px;">${location}</div>
							<div style="color:${colors().mid};">${formatMetric(metric)}: <strong>${formatValue(value, metric)}</strong></div>
						</div>`
					)
					.addTo(map!);
			});

			map.on('mouseleave', 'ev-circles', () => {
				map!.getCanvas().style.cursor = '';
				popup?.remove();
				popup = null;
			});

			if (fit) fitToPoints(pts);
		}
	}

	function stopPlayback() {
		if (playTimer) { clearInterval(playTimer); playTimer = null; }
		playing = false;
	}

	function startPlayback() {
		if (!timeSeries) return;
		playing = true;
		playTimer = setInterval(() => {
			frameIndex = (frameIndex + 1) % timeSeries!.frames.length;
		}, playInterval());
	}

	function togglePlay() {
		if (playing) stopPlayback();
		else startPlayback();
	}

	function stepFrame(dir: -1 | 1) {
		if (!timeSeries) return;
		stopPlayback();
		frameIndex = (frameIndex + dir + timeSeries.frames.length) % timeSeries.frames.length;
	}

	// Reactive: when frameIndex changes, update the map
	$effect(() => {
		if (timeSeries && map?.loaded()) {
			applyPoints(timeSeries.frames[frameIndex]);
		}
	});

	onMount(() => {
		map = new maplibregl.Map({
			container,
			style: CARTO_VOYAGER,
			center: NYC_CENTER,
			zoom: NYC_ZOOM,
			attributionControl: false
		});

		map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
		map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

		map.on('load', () => {
			if (timeSeries) {
				applyPoints(timeSeries.frames[0], true);
				// auto-play after a brief pause
				setTimeout(startPlayback, 600);
			} else if (points.length > 0) {
				applyPoints(points, true);
			}
		});
	});

	onDestroy(() => {
		stopPlayback();
		map?.remove();
		map = null;
	});

	// Static points reactivity
	$effect(() => {
		if (!timeSeries && map?.loaded()) {
			applyPoints(points);
		}
	});

	// Re-color circles when mapStyle changes (new query)
	$effect(() => {
		if (!map?.loaded() || !map.getLayer('ev-circles')) return;
		const c = colors();
		map.setPaintProperty('ev-halo', 'circle-color', c.mid);
		map.setPaintProperty('ev-circles', 'circle-color', [
			'interpolate', ['linear'], ['get', 'normalised'],
			0, c.low, 0.5, c.mid, 1, c.high
		]);
	});

	// Highlight selected location on the map + zoom to it / zoom out on deselect
	$effect(() => {
		if (!map?.loaded()) return;
		const loc = selectedLocation;
		// Use first frame for coords — location lat/lng is stable across frames
		const pool = timeSeries ? (timeSeries.frames[0] ?? []) : points;
		if (!loc) {
			map.setPaintProperty('ev-circles', 'circle-opacity', 0.85);
			map.setPaintProperty('ev-circles', 'circle-stroke-width', 1.5);
			map.setPaintProperty('ev-halo', 'circle-opacity', 0.12);
			if (pool.length > 0) fitToPoints(pool);
		} else {
			map.setPaintProperty('ev-circles', 'circle-opacity', [
				'case', ['==', ['get', 'location'], loc], 0.95, 0.18
			]);
			map.setPaintProperty('ev-circles', 'circle-stroke-width', [
				'case', ['==', ['get', 'location'], loc], 3, 0.5
			]);
			map.setPaintProperty('ev-halo', 'circle-opacity', [
				'case', ['==', ['get', 'location'], loc], 0.35, 0.03
			]);
			const pt = pool.find(p => p.location === loc);
			if (pt) map.flyTo({ center: [pt.lng, pt.lat], zoom: 14, duration: 700, essential: true });
		}
	});
</script>

<div class="flex h-full flex-col">
	<!-- Map fills space -->
	<div bind:this={container} class="min-h-0 flex-1"></div>

	<!-- Playback controls — only for time series -->
	{#if timeSeries}
		<div
			class="flex flex-none items-center gap-2 px-3"
			style="height: 36px; border-top: 1px solid rgba(0,0,0,0.07); background: #fafafa;"
		>
			<!-- prev -->
			<button
				onclick={() => stepFrame(-1)}
				class="flex h-6 w-6 cursor-pointer items-center justify-center transition-colors duration-100"
				style="color: rgba(0,0,0,0.40);"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.80)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.40)'; }}
				aria-label="Previous"
			>
				<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
					<polyline points="15 18 9 12 15 6"/>
				</svg>
			</button>

			<!-- play / pause -->
			<button
				onclick={togglePlay}
				class="flex h-6 w-6 cursor-pointer items-center justify-center transition-colors duration-100"
				style="color: rgba(0,60,160,0.70);"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,60,160,1)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,60,160,0.70)'; }}
				aria-label={playing ? 'Pause' : 'Play'}
			>
				{#if playing}
					<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="none">
						<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
					</svg>
				{:else}
					<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="none">
						<polygon points="5 3 19 12 5 21 5 3"/>
					</svg>
				{/if}
			</button>

			<!-- next -->
			<button
				onclick={() => stepFrame(1)}
				class="flex h-6 w-6 cursor-pointer items-center justify-center transition-colors duration-100"
				style="color: rgba(0,0,0,0.40);"
				onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.80)'; }}
				onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgba(0,0,0,0.40)'; }}
				aria-label="Next"
			>
				<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
					<polyline points="9 18 15 12 9 6"/>
				</svg>
			</button>

			<!-- period nav: dots for ≤12 periods, range slider for more -->
			<div class="flex flex-1 items-center justify-center gap-1.5 px-1">
				{#if timeSeries.periods.length <= 12}
					{#each timeSeries.periods as period, i}
						<button
							onclick={() => { stopPlayback(); frameIndex = i; }}
							class="cursor-pointer transition-all duration-200"
							style="width: {i === frameIndex ? '20px' : '5px'}; height: 5px; background: {i === frameIndex ? 'rgba(0,60,160,0.75)' : 'rgba(0,0,0,0.15)'};"
							aria-label={period}
						></button>
					{/each}
				{:else}
					<input
						type="range"
						min="0"
						max={timeSeries.periods.length - 1}
						value={frameIndex}
						oninput={(e) => { stopPlayback(); frameIndex = parseInt((e.target as HTMLInputElement).value); }}
						class="w-full cursor-pointer"
						style="accent-color: rgba(0,60,160,0.75); height: 3px;"
					/>
				{/if}
			</div>

			<!-- current period label -->
			<span class="shrink-0 text-[11px] font-semibold tabular-nums" style="color: rgba(0,60,160,0.75); min-width: 36px; text-align: right;">
				{timeSeries.periods[frameIndex]}
			</span>
		</div>
	{/if}
</div>

<style>
	:global(.maplibregl-popup-content) {
		padding: 8px 12px;
		border-radius: 10px;
		box-shadow: 0 4px 16px rgba(0, 60, 160, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.9);
	}
	:global(.maplibregl-ctrl-group) {
		border-radius: 8px !important;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
	}
</style>
