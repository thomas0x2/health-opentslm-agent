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
	const padding = 10;
	const vW = 200, vH = 120;
	let pathD = $derived(
		points.map((p, i) => {
			const x = padding + (i / Math.max(xMax, 1)) * (vW - padding * 2);
			const y = padding + (1 - (p.y - yMin) / yRange) * (vH - padding * 2);
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
	{:else if !result || points.length === 0}
		<div class="nodata">No data</div>
	{:else}
		<svg viewBox="0 0 {vW} {vH}" class="chart">
			<polyline d={pathD} fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
			<text x={vW / 2} y={vH - 2} text-anchor="middle" class="axis-label">{result.xLabel ?? ''}</text>
		</svg>
		{#if result.unit}
			<div class="unit-label">{result.unit}</div>
		{/if}
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
	.axis-label {
		font-size: 5px;
		fill: var(--text-tertiary);
		font-family: inherit;
	}
	.unit-label {
		font-size: 10px;
		color: var(--text-tertiary);
		text-align: right;
		margin-top: 2px;
	}
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
