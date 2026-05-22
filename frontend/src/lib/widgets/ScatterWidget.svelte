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

	let points = $derived((result?.series ?? []).filter(p => typeof p.y === 'number' && typeof p.x === 'number' && !isNaN(p.y) && !isNaN(p.x)));
	let xVals = $derived(points.map(p => p.x as number));
	let yVals = $derived(points.map(p => p.y));
	let xMin = $derived(Math.min(...xVals));
	let xMax = $derived(Math.max(...xVals, xMin + 1));
	let yMin = $derived(Math.min(0, ...yVals));
	let yMax = $derived(Math.max(...yVals, yMin + 1));
	const pad = 14, vW = 200, vH = 120;
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
			{#each points as p}
				{@const cx = pad + ((p.x as number) - xMin) / (xMax - xMin) * (vW - pad * 2)}
				{@const cy = pad + (1 - (p.y - yMin) / (yMax - yMin)) * (vH - pad * 2)}
				<circle cx={cx.toFixed(1)} cy={cy.toFixed(1)} r="2.5" fill="var(--green)" opacity="0.8" />
			{/each}
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
