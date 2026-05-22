<script lang="ts">
	import type { SparkPoint } from '$lib/data/vitals';
	interface Props { points: SparkPoint[]; color: string }
	let { points, color }: Props = $props();

	const polylineStr = $derived(points.map(p => `${p.x},${p.y}`).join(' '));
	const areaStr = $derived(
		`0,38 ${points.map(p => `${p.x},${p.y}`).join(' ')} 140,38`
	);
</script>

<div class="sparkline-container">
	<svg class="sparkline" viewBox="0 0 140 40">
		<polyline class="area" points={areaStr} style="fill: {color}"/>
		<polyline points={polylineStr} style="stroke: {color}"/>
	</svg>
</div>

<style>
	.sparkline-container { margin-top: 10px; }
	.sparkline { width: 100%; height: 40px; }
	.sparkline polyline {
		fill: none;
		stroke-width: 1.8;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.sparkline .area {
		stroke: none;
		opacity: 0.12;
	}
</style>
