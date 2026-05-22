<script lang="ts">
	interface Props { label: string; value: string; unit?: string }
	let { label, value, unit }: Props = $props();
</script>

<div class="metric-row">
	<span class="label">{label}</span>
	<span class="value">{value}{#if unit}<span class="unit">{unit}</span>{/if}</span>
</div>

<style>
	.metric-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		padding: 10px 0;
		border-bottom: 1px solid var(--bg);
	}
	.metric-row:last-child { border-bottom: none; }
	.label { font-size: 12.5px; color: var(--text-secondary); }
	.value {
		font-family: 'Instrument Serif', serif;
		font-size: 22px;
		letter-spacing: -0.02em;
	}
	.unit { font-family: 'DM Sans', sans-serif; font-size: 11px; color: var(--text-tertiary); }
</style>
