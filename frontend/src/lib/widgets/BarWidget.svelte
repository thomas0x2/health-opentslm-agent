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
	let yMax = $derived(Math.max(...points.map(p => p.y), 1));
	const pad = 8, vW = 200, vH = 120;
	let barW = $derived(Math.max(4, (vW - pad * 2) / Math.max(points.length, 1) * 0.7));
	let gap = $derived((vW - pad * 2) / Math.max(points.length, 1));
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
			{#each points as p, i}
				{@const h = Math.max(1, (p.y / yMax) * (vH - pad * 2))}
				{@const x = pad + i * gap + (gap - barW) / 2}
				{@const y = vH - pad - h}
				<rect {x} {y} width={barW} height={h} rx="2" fill="var(--green)" opacity="0.75" />
				<text x={x + barW / 2} y={vH - 1} text-anchor="middle" class="bar-label">{String(p.x).slice(0, 5)}</text>
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
	.bar-label {
		font-size: 4.5px;
		fill: var(--text-tertiary);
		font-family: inherit;
	}
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
