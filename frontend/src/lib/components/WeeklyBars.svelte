<script lang="ts">
	import type { WeeklyBar } from '$lib/data/vitals';
	interface Props { bars: WeeklyBar[]; color?: string }
	let { bars, color = 'var(--gold)' }: Props = $props();
</script>

<div class="weekly-bars">
	{#each bars as bar}
		<div class="bar-group">
			<div
				class="bar"
				style="height: {bar.height}%; background: {color}; opacity: {bar.today ? 0.4 : 1}"
			></div>
			<div class="label" class:today={bar.today}>{bar.label}</div>
		</div>
	{/each}
</div>

<style>
	.weekly-bars {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		height: 60px;
		margin-top: 10px;
		gap: 4px;
	}
	.bar-group {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		flex: 1;
	}
	.bar {
		width: 100%;
		max-width: 24px;
		border-radius: 4px 4px 2px 2px;
		min-height: 4px;
	}
	.label {
		font-size: 9px;
		color: var(--text-tertiary);
		font-weight: 500;
		letter-spacing: 0.04em;
	}
	.label.today { color: var(--gold); font-weight: 600; }
</style>
