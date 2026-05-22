<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SingleValueResult } from './types';

	let { widget, records }: WidgetProps = $props();

	let result = $state<SingleValueResult | null>(null);
	let error = $state('');

	try {
		const r = executeWidget(widget, records);
		if (r.kind === 'single_value') result = r;
		else error = `Expected single_value result, got ${r.kind}`;
	} catch (e: any) {
		error = e.message || String(e);
	}

	let trendSymbol = $derived(result?.trend === 'up' ? '↑' : result?.trend === 'down' ? '↓' : '→');
	let trendColor = $derived(result?.trend === 'up' ? 'var(--green)' : result?.trend === 'down' ? '#e74c3c' : 'var(--text-tertiary)');
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
		<span class="desc">{widget.description}</span>
	</div>
	<div class="content">
		{#if result}
			<div class="value-row">
				<span class="value">{result.value}</span>
				<span class="unit">{result.unit}</span>
			</div>
			<div class="label-row">{result.label}</div>
			{#if result.trend}
				<div class="trend-row" style="color: {trendColor}">
					{trendSymbol} {result.trendValue != null ? result.trendValue : ''}
				</div>
			{/if}
		{:else if error}
			<div class="error">{error}</div>
		{:else}
			<div class="nodata">No data</div>
		{/if}
	</div>
</div>

<style>
	.widget-card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 14px 16px;
	}
	.header {
		margin-bottom: 10px;
	}
	.title {
		font-family: 'Instrument Serif', serif;
		font-size: 16px;
		letter-spacing: -0.01em;
		color: var(--text-primary);
		display: block;
	}
	.desc {
		font-size: 11px;
		color: var(--text-tertiary);
		margin-top: 2px;
		display: block;
	}
	.content {
		text-align: center;
		padding: 8px 0;
	}
	.value-row {
		display: flex;
		align-items: baseline;
		justify-content: center;
		gap: 4px;
	}
	.value {
		font-family: 'Instrument Serif', serif;
		font-size: 44px;
		line-height: 1;
		color: var(--text-primary);
	}
	.unit {
		font-size: 14px;
		color: var(--text-tertiary);
		font-weight: 500;
	}
	.label-row {
		font-size: 12px;
		color: var(--text-secondary);
		margin-top: 4px;
		font-weight: 500;
	}
	.trend-row {
		font-size: 13px;
		font-weight: 600;
		margin-top: 6px;
	}
	.error {
		color: #e74c3c;
		font-size: 12px;
	}
	.nodata {
		color: var(--text-tertiary);
		font-size: 13px;
	}
</style>
