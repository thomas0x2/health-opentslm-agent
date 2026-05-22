<script lang="ts">
	import { executeWidget } from './execute';
	import type { WidgetProps, SingleValueResult } from './types';

	let { widget, records }: WidgetProps = $props();

	let execution = $derived.by(() => {
		if (!records || records.length === 0) return { result: null as SingleValueResult | null, error: '' };
		try {
			const r = executeWidget(widget, records);
			if (r.kind === 'single_value') {
				console.log(`[Widget "${widget.title}"] value=${r.value} ${r.unit}`);
				return { result: r as SingleValueResult, error: '' };
			}
			console.warn(`[Widget "${widget.title}"] wrong kind:`, r.kind);
			return { result: null as SingleValueResult | null, error: `Expected single_value result, got ${r.kind}` };
		} catch (e: any) {
			console.error(`[Widget "${widget.title}"] error:`, e.message || e);
			return { result: null as SingleValueResult | null, error: e.message || String(e) };
		}
	});
	let result = $derived(execution.result);
	let error = $derived(execution.error);

	let trendSymbol = $derived(result?.trend === 'up' ? '↑' : result?.trend === 'down' ? '↓' : '→');
	let trendColor = $derived(result?.trend === 'up' ? 'var(--green)' : result?.trend === 'down' ? '#e74c3c' : 'var(--text-tertiary)');
	let accentColor = $derived(`var(--${widget.color ?? 'green'})`);
</script>

<div class="widget-card">
	<div class="header">
		<span class="title">{widget.title}</span>
		<span class="desc">{widget.description}</span>
	</div>
	<div class="content">
		{#if result}
			<div class="value-row">
				<span class="value" style="color: {accentColor}">{result.value}</span>
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
