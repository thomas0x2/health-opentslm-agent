<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import InteractiveChart from './InteractiveChart.svelte';
	import type { SeriesResult } from '$lib/widgets/types';

	let {
		title,
		description = '',
		type,
		result,
		color = 'green',
		unit = '',
		onClose
	}: {
		title: string;
		description?: string;
		type: 'line' | 'area' | 'bar' | 'scatter';
		result: SeriesResult;
		color?: string;
		unit?: string;
		onClose: () => void;
	} = $props();

	const points = $derived(
		(result?.series ?? []).filter((p) => typeof p.y === 'number' && Number.isFinite(p.y))
	);
	const yVals = $derived(points.map((p) => p.y));
	const stats = $derived.by(() => {
		if (yVals.length === 0) return null;
		const sum = yVals.reduce((a, b) => a + b, 0);
		const avg = sum / yVals.length;
		const min = Math.min(...yVals);
		const max = Math.max(...yVals);
		// Trend: first half avg vs second half avg
		const mid = Math.floor(yVals.length / 2);
		const firstHalf = yVals.slice(0, mid);
		const secondHalf = yVals.slice(mid);
		const firstAvg = firstHalf.length ? firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length : avg;
		const secondAvg = secondHalf.length ? secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length : avg;
		const trendDelta = secondAvg - firstAvg;
		const trendPct = firstAvg !== 0 ? (trendDelta / Math.abs(firstAvg)) * 100 : 0;
		return { sum, avg, min, max, trendDelta, trendPct, n: yVals.length };
	});

	function fmt(v: number): string {
		if (!Number.isFinite(v)) return '—';
		const abs = Math.abs(v);
		if (abs >= 10000) return (v / 1000).toFixed(1) + 'k';
		if (abs >= 1000) return Math.round(v).toLocaleString();
		if (abs >= 100) return v.toFixed(0);
		if (abs >= 10) return v.toFixed(1);
		return v.toFixed(2);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	onMount(() => {
		document.body.style.overflow = 'hidden';
		window.addEventListener('keydown', onKey);
	});
	onDestroy(() => {
		document.body.style.overflow = '';
		window.removeEventListener('keydown', onKey);
	});

	function backdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) onClose();
	}
</script>

<div
	class="backdrop"
	onclick={backdropClick}
	onkeydown={(e) => e.key === 'Escape' && onClose()}
	role="dialog"
	aria-modal="true"
	aria-label={title}
	tabindex="-1"
>
	<div class="modal">
		<header class="modal-head">
			<div class="head-text">
				<h2 class="title">{title}</h2>
				{#if description}
					<p class="desc">{description}</p>
				{/if}
			</div>
			<button class="close" onclick={onClose} aria-label="Close">
				<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
					<path d="M4 4l8 8M12 4l-8 8" />
				</svg>
			</button>
		</header>

		<div class="chart-area">
			<InteractiveChart {type} {result} {color} {title} compact={false} />
		</div>

		{#if stats}
			<div class="stats">
				<div class="stat">
					<div class="stat-label">Avg</div>
					<div class="stat-value">{fmt(stats.avg)}{#if unit} <span class="stat-unit">{unit}</span>{/if}</div>
				</div>
				<div class="stat">
					<div class="stat-label">Min</div>
					<div class="stat-value">{fmt(stats.min)}{#if unit} <span class="stat-unit">{unit}</span>{/if}</div>
				</div>
				<div class="stat">
					<div class="stat-label">Max</div>
					<div class="stat-value">{fmt(stats.max)}{#if unit} <span class="stat-unit">{unit}</span>{/if}</div>
				</div>
				<div class="stat">
					<div class="stat-label">Trend</div>
					<div class="stat-value" class:up={stats.trendDelta > 0} class:down={stats.trendDelta < 0}>
						{stats.trendDelta > 0 ? '↑' : stats.trendDelta < 0 ? '↓' : '→'}
						{Math.abs(stats.trendPct).toFixed(1)}<span class="stat-unit">%</span>
					</div>
				</div>
				<div class="stat">
					<div class="stat-label">Points</div>
					<div class="stat-value">{stats.n}</div>
				</div>
			</div>
		{/if}

		<div class="hint">
			<span>Drag to zoom · double-click reset · scroll for toolbar</span>
		</div>
	</div>
</div>

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		background: rgba(20, 20, 20, 0.55);
		backdrop-filter: blur(4px);
		-webkit-backdrop-filter: blur(4px);
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 16px;
		animation: fadeBackdrop 0.18s ease;
	}
	@keyframes fadeBackdrop {
		from { opacity: 0; }
		to { opacity: 1; }
	}
	.modal {
		background: var(--card);
		border-radius: var(--radius-lg);
		width: 100%;
		max-width: 480px;
		max-height: calc(100vh - 32px);
		display: flex;
		flex-direction: column;
		box-shadow: 0 20px 60px rgba(0,0,0,0.25);
		overflow: hidden;
		animation: slideUp 0.22s ease;
	}
	@keyframes slideUp {
		from { transform: translateY(12px); opacity: 0; }
		to { transform: translateY(0); opacity: 1; }
	}
	.modal-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		padding: 18px 20px 12px;
		border-bottom: 1px solid var(--bg);
		gap: 12px;
	}
	.head-text { flex: 1; min-width: 0; }
	.title {
		font-family: 'Instrument Serif', serif;
		font-size: 22px;
		line-height: 1.15;
		letter-spacing: -0.01em;
		color: var(--text-primary);
		margin: 0;
		font-weight: 400;
	}
	.desc {
		font-size: 12px;
		color: var(--text-secondary);
		margin: 4px 0 0;
		line-height: 1.4;
	}
	.close {
		flex-shrink: 0;
		width: 30px;
		height: 30px;
		border-radius: 50%;
		border: none;
		background: var(--bg);
		color: var(--text-secondary);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.15s, color 0.15s;
	}
	.close:hover { background: var(--bg-warm); color: var(--text-primary); }

	.chart-area {
		padding: 12px 8px 4px;
		flex: 1;
		min-height: 0;
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: 6px;
		padding: 12px 18px 8px;
		border-top: 1px solid var(--bg);
	}
	.stat {
		text-align: center;
		padding: 6px 4px;
	}
	.stat-label {
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-tertiary);
		font-weight: 600;
		margin-bottom: 3px;
	}
	.stat-value {
		font-family: 'Instrument Serif', serif;
		font-size: 18px;
		line-height: 1;
		color: var(--text-primary);
		letter-spacing: -0.01em;
	}
	.stat-value.up { color: var(--green); }
	.stat-value.down { color: var(--terracotta); }
	.stat-unit {
		font-family: 'DM Sans', sans-serif;
		font-size: 9px;
		color: var(--text-tertiary);
		font-weight: 500;
	}

	.hint {
		padding: 6px 18px 14px;
		text-align: center;
		font-size: 10px;
		color: var(--text-tertiary);
		letter-spacing: 0.02em;
	}

	@media (max-width: 500px) {
		.stats { grid-template-columns: repeat(3, 1fr); }
		.stat:nth-child(4), .stat:nth-child(5) { grid-column: span 1; }
	}
</style>
