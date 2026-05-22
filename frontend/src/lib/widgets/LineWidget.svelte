<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SeriesResult } from './types';
	import InteractiveChart from '$lib/components/InteractiveChart.svelte';
	import ChartModal from '$lib/components/ChartModal.svelte';

	let { widget, records }: WidgetProps = $props();

	let execution = $derived.by(() => {
		if (!records || records.length === 0) return { result: null as SeriesResult | null, error: '' };
		try {
			const r = executeWidget(widget, records);
			if (r.kind === 'series') return { result: r as SeriesResult, error: '' };
			return { result: null as SeriesResult | null, error: `Expected series, got ${r.kind}` };
		} catch (e: any) {
			console.error(`[Widget "${widget.title}"] error:`, e.message || e);
			return { result: null as SeriesResult | null, error: e.message || String(e) };
		}
	});
	let result = $derived(execution.result);
	let error = $derived(execution.error);
	let hasData = $derived(!!result && result.series.some((p) => typeof p.y === 'number' && Number.isFinite(p.y)));

	let showModal = $state(false);
	let color = $derived(widget.color ?? 'green');
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
		{#if result?.unit}<span class="unit-tag">{result.unit}</span>{/if}
	</div>
	{#if error}
		<div class="error">{error}</div>
	{:else if !hasData}
		<div class="nodata">No data</div>
	{:else if result}
		<InteractiveChart
			type="line"
			{result}
			{color}
			title={widget.title}
			compact={true}
			onExpandClick={() => (showModal = true)}
		/>
	{/if}
</div>

{#if showModal && result}
	<ChartModal
		title={widget.title}
		description={widget.description}
		type="line"
		{result}
		{color}
		unit={result.unit ?? ''}
		onClose={() => (showModal = false)}
	/>
{/if}

<style>
	.widget-card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 14px 16px 8px;
	}
	.header {
		margin-bottom: 4px;
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 8px;
	}
	.title {
		font-family: 'Instrument Serif', serif;
		font-size: 14px;
		color: var(--text-primary);
	}
	.unit-tag {
		font-size: 10px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.error { color: #e74c3c; font-size: 12px; padding: 8px 0; }
	.nodata { color: var(--text-tertiary); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
