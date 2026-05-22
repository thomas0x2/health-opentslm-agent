<script lang="ts">
	import type { SleepStage } from '$lib/data/vitals';
	interface Props { stages: SleepStage[] }
	let { stages }: Props = $props();
	const legends = [
		{ label: 'Awake', opacity: 0.15 },
		{ label: 'Light', opacity: 0.35 },
		{ label: 'REM',   opacity: 0.6 },
		{ label: 'Deep',  opacity: 0.9 }
	];
</script>

<div class="sleep-stages">
	{#each stages as s}
		<div class="stage" style="flex: {s.flex}; opacity: {s.opacity}"></div>
	{/each}
</div>
<div class="legend">
	{#each legends as l}
		<div class="legend-item">
			<div class="dot" style="opacity: {l.opacity}"></div>
			{l.label}
		</div>
	{/each}
</div>

<style>
	.sleep-stages {
		display: flex;
		height: 14px;
		border-radius: 7px;
		overflow: hidden;
		margin-top: 10px;
		gap: 2px;
	}
	.stage {
		height: 100%;
		border-radius: 4px;
		background: var(--blue);
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
	.dot {
		width: 6px;
		height: 6px;
		border-radius: 2px;
		background: var(--blue);
	}
</style>
