<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SeriesResult } from './types';

	let { widget, records }: WidgetProps = $props();

	let execution = $derived.by(() => {
		if (!records || records.length === 0) return { result: null as SeriesResult | null, error: '' };
		try {
			const r = executeWidget(widget, records);
			if (r.kind === 'series') {
				console.log(`[Widget "${widget.title}"] heatmap, ${r.series.length} cells`);
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

	// Extract unique x (rows) and y (columns) labels, plus min/max value for coloring
	let cells = $derived((result?.series ?? []).filter(p => typeof p.y === 'number' && !isNaN(p.y)));
	let rows = $derived([...new Set(cells.map(c => String(c.x)))]);
	let cols = $derived([...new Set(cells.map(c => String(c.label ?? '')))]);
	let values = $derived(cells.map(c => c.y));
	let minV = $derived(Math.min(...values));
	let maxV = $derived(Math.max(...values, minV + 1));

	function cellColor(x: string, col: string): string {
		const cell = cells.find(c => String(c.x) === x && String(c.label ?? '') === col);
		if (!cell) return 'transparent';
		const ratio = (cell.y - minV) / (maxV - minV || 1);
		const g = Math.round(22 + ratio * 200);
		const r = Math.round(200 - ratio * 180);
		return `rgb(${r},${g},40)`;
	}
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
	</div>
	{#if error}
		<div class="error">{error}</div>
	{:else if cells.length === 0 || rows.length === 0}
		<div class="nodata">No data</div>
	{:else}
		<div class="grid" style="grid-template-columns: 50px repeat({cols.length}, 1fr)">
			<div class="corner"></div>
			{#each cols as col}
				<div class="col-label">{col}</div>
			{/each}
			{#each rows as row}
				<div class="row-label">{row}</div>
				{#each cols as col}
					{@const cell = cells.find(c => String(c.x) === row && String(c.label ?? '') === col)}
					<div
						class="cell"
						style="background: {cellColor(row, col)}"
						title="{row} / {col}: {cell?.y ?? '-'}"
					>
						{#if cell}
							<span class="cell-val">{typeof cell.y === 'number' ? cell.y.toFixed(0) : cell.y}</span>
						{/if}
					</div>
				{/each}
			{/each}
		</div>
		<div class="scale">
			<span>{minV.toFixed(0)}</span>
			<div class="scale-bar"></div>
			<span>{maxV.toFixed(0)}</span>
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
	.grid {
		display: grid;
		gap: 2px;
		font-size: 9px;
	}
	.corner { }
	.col-label, .row-label {
		color: var(--text-tertiary);
		font-weight: 500;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1px;
	}
	.cell {
		aspect-ratio: 1;
		border-radius: 3px;
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 18px;
	}
	.cell-val {
		font-size: 8px;
		font-weight: 600;
		color: white;
		text-shadow: 0 1px 2px rgba(0,0,0,0.4);
	}
	.scale {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 6px;
		font-size: 9px;
		color: var(--text-tertiary);
	}
	.scale-bar {
		flex: 1;
		height: 6px;
		border-radius: 3px;
		background: linear-gradient(to right, rgb(22,200,40), rgb(200,200,40));
	}
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
