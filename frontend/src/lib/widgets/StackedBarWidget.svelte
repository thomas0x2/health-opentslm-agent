<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SeriesResult } from './types';

	let { widget, records }: WidgetProps = $props();

	let execution = $derived.by(() => {
		if (!records || records.length === 0) return { result: null as SeriesResult | null, error: '' };
		try {
			const r = executeWidget(widget, records);
			if (r.kind === 'series') {
				console.log(`[Widget "${widget.title}"] stacked, ${r.series.length} segments`);
				return { result: r as SeriesResult, error: '' };
			}
			console.warn(`[Widget "${widget.title}"] wrong kind:`, r.kind);
			return { result: null as SeriesResult | null, error: `Expected series result, got ${r.kind}` };
		} catch (e: any) {
			console.error(`[Widget "${widget.title}"] error:`, e.message || e);
			return { result: null as SeriesResult | null, error: e.message || String(e) };
		}
	});
	let result = $derived(execution.result);
	let error = $derived(execution.error);

	let segments = $derived((result?.series ?? []).filter(p => typeof p.y === 'number' && !isNaN(p.y)));
	let total = $derived(segments.reduce((s, p) => s + p.y, 0) || 1);

	const palette = ['var(--green)', 'var(--blue)', 'var(--terracotta)', 'var(--gold)', 'var(--purple)'];
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
	</div>
	{#if error}
		<div class="error">{error}</div>
	{:else if segments.length === 0}
		<div class="nodata">No data</div>
	{:else}
		<div class="bar-container">
			<div class="bar-track">
				{#each segments as seg, i}
					<div
						class="bar-segment"
						style="width: {(seg.y / total * 100).toFixed(1)}%; background: {palette[i % palette.length]}"
						title="{seg.label ?? seg.x}: {seg.y}"
					></div>
				{/each}
			</div>
		</div>
		<div class="legend">
			{#each segments as seg, i}
				<div class="legend-item">
					<span class="swatch" style="background: {palette[i % palette.length]}"></span>
					<span class="legend-label">{seg.label ?? seg.x}</span>
					<span class="legend-val">{seg.y}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.widget-card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 14px 16px;
	}
	.header { margin-bottom: 8px; }
	.title {
		font-family: 'Instrument Serif', serif;
		font-size: 14px;
		color: var(--text-primary);
	}
	.bar-container { padding: 4px 0; }
	.bar-track {
		display: flex;
		height: 20px;
		border-radius: 6px;
		overflow: hidden;
		background: var(--bg);
	}
	.bar-segment {
		height: 100%;
		transition: width 0.3s;
		min-width: 2px;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-top: 8px;
	}
	.legend-item {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 10px;
		color: var(--text-secondary);
	}
	.swatch {
		width: 8px;
		height: 8px;
		border-radius: 2px;
		flex-shrink: 0;
	}
	.legend-val {
		font-weight: 600;
		color: var(--text-primary);
	}
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
