<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SeriesResult } from './types';

	let { widget, records }: WidgetProps = $props();

	let result = $state<SeriesResult | null>(null);
	let error = $state('');

	try {
		const r = executeWidget(widget, records);
		if (r.kind === 'series') result = r;
		else error = `Expected series result, got ${r.kind}`;
	} catch (e: any) {
		error = e.message || String(e);
	}

	let points = $derived((result?.series ?? []).filter(p => typeof p.y === 'number' && !isNaN(p.y)));
	let xMax = $derived(points.length - 1 || 1);
	let yVals = $derived(points.map(p => p.y));
	let yMin = $derived(Math.min(0, ...yVals));
	let yMax = $derived(Math.max(...yVals, 1));
	let yRange = $derived(yMax - yMin || 1);
	const pad = 10, vW = 200, vH = 120;

	let areaD = $derived((() => {
		if (points.length === 0) return '';
		const parts: string[] = [];
		for (let i = 0; i < points.length; i++) {
			const x = pad + (i / Math.max(xMax, 1)) * (vW - pad * 2);
			const y = pad + (1 - (points[i].y - yMin) / yRange) * (vH - pad * 2);
			parts.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`);
		}
		const lastX = pad + (points.length - 1) / Math.max(xMax, 1) * (vW - pad * 2);
		parts.push(`L ${lastX.toFixed(1)} ${vH - pad}`);
		parts.push(`L ${pad} ${vH - pad}`);
		parts.push('Z');
		return parts.join(' ');
	})());

	let lineD = $derived(
		points.map((p, i) => {
			const x = pad + (i / Math.max(xMax, 1)) * (vW - pad * 2);
			const y = pad + (1 - (p.y - yMin) / yRange) * (vH - pad * 2);
			return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
		}).join(' ')
	);
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
	</div>
	{#if error}
		<div class="error">{error}</div>
	{:else if points.length === 0}
		<div class="nodata">No data</div>
	{:else}
		<svg viewBox="0 0 {vW} {vH}" class="chart">
			<defs>
				<linearGradient id="area-{widget.id}" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" stop-color="var(--green)" />
					<stop offset="100%" stop-color="var(--green)" stop-opacity="0.05" />
				</linearGradient>
			</defs>
			<path d={areaD} fill="url(#area-{widget.id})" />
			<polyline d={lineD} fill="none" stroke="var(--green)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
	{/if}
</div>

<style>
	.widget-card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 14px 16px;
	}
	.header { margin-bottom: 4px; }
	.title {
		font-family: 'Instrument Serif', serif;
		font-size: 14px;
		color: var(--text-primary);
	}
	.chart { width: 100%; height: auto; display: block; }
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
