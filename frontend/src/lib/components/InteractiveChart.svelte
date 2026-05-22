<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { browser } from '$app/environment';
	import type { SeriesResult } from '$lib/widgets/types';

	type ChartType = 'line' | 'area' | 'bar' | 'scatter';

	let {
		type,
		result,
		color = 'green',
		title,
		compact = true,
		onExpandClick = undefined as undefined | (() => void)
	}: {
		type: ChartType;
		result: SeriesResult;
		color?: string;
		title: string;
		compact?: boolean;
		onExpandClick?: () => void;
	} = $props();

	const COLOR_HEX: Record<string, string> = {
		green: '#2d5a3d',
		terracotta: '#c45c3e',
		blue: '#3a5ba0',
		gold: '#8b6914',
		purple: '#6b4c8a'
	};

	let chartEl: HTMLDivElement | undefined = $state();
	let chart: any = null;

	const cleanPoints = $derived(
		(result?.series ?? []).filter(
			(p) => typeof p.y === 'number' && Number.isFinite(p.y)
		)
	);

	function formatX(x: string | number): string {
		const s = String(x);
		if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(5, 10);
		return s.length > 10 ? s.slice(0, 10) : s;
	}

	function formatY(v: number): string {
		if (!Number.isFinite(v)) return '—';
		const abs = Math.abs(v);
		if (abs >= 10000) return (v / 1000).toFixed(1) + 'k';
		if (abs >= 1000) return Math.round(v).toLocaleString();
		if (abs >= 100) return v.toFixed(0);
		if (abs >= 10) return v.toFixed(1);
		return v.toFixed(2);
	}

	function buildOptions(): any {
		const accent = COLOR_HEX[color] ?? COLOR_HEX.green;
		const points = cleanPoints;
		const isScatter = type === 'scatter';
		const apexType = isScatter ? 'scatter' : type === 'area' ? 'area' : type === 'bar' ? 'bar' : 'line';

		const categories = isScatter ? [] : points.map((p) => formatX(p.x));
		const seriesData = isScatter
			? points.map((p) => [Number(p.x), Number(p.y)])
			: points.map((p) => Number(p.y));

		// X-axis: scatter is numeric, else category. Build conditionally so we never
		// emit `title: undefined` (ApexCharts dereferences `.text` and crashes).
		const xaxis: any = isScatter
			? {
					type: 'numeric',
					labels: {
						style: { colors: '#a8a29e', fontSize: compact ? '9px' : '11px' },
						formatter: (v: any) => formatY(Number(v))
					},
					axisBorder: { show: false },
					axisTicks: { show: false }
				}
			: {
					categories,
					labels: {
						rotate: 0,
						rotateAlways: false,
						hideOverlappingLabels: true,
						style: { colors: '#a8a29e', fontSize: compact ? '9px' : '11px' }
					},
					axisBorder: { show: false },
					axisTicks: { show: false }
				};
		if (!compact && result?.xLabel) {
			xaxis.title = { text: result.xLabel, style: { fontSize: '11px', color: '#7a7570', fontWeight: 500 } };
		}
		if (compact && !isScatter && categories.length > 1) {
			xaxis.tickAmount = Math.min(5, categories.length - 1);
		}

		const yaxis: any = {
			labels: {
				style: { colors: '#a8a29e', fontSize: compact ? '9px' : '11px' },
				formatter: (v: number) => formatY(v)
			},
			forceNiceScale: true
		};
		if (!compact && result?.yLabel) {
			yaxis.title = {
				text: `${result.yLabel}${result.unit ? ` (${result.unit})` : ''}`,
				style: { fontSize: '11px', color: '#7a7570', fontWeight: 500 }
			};
		}

		return {
			chart: {
				type: apexType,
				height: compact ? 160 : 380,
				width: '100%',
				redrawOnParentResize: true,
				redrawOnWindowResize: true,
				toolbar: {
					show: !compact,
					tools: {
						download: true,
						selection: true,
						zoom: true,
						zoomin: true,
						zoomout: true,
						pan: true,
						reset: true
					},
					autoSelected: 'zoom'
				},
				zoom: { enabled: !compact, type: 'x', autoScaleYaxis: true },
				animations: { enabled: true, speed: 280, animateGradually: { enabled: false } },
				fontFamily: 'DM Sans, sans-serif',
				background: 'transparent'
			},
			colors: [accent],
			stroke: {
				curve: type === 'bar' ? 'straight' : 'smooth',
				width: type === 'bar' || isScatter ? 0 : compact ? 2 : 2.5,
				lineCap: 'round'
			},
			fill:
				type === 'area'
					? {
							type: 'gradient',
							gradient: {
								shadeIntensity: 1,
								opacityFrom: 0.4,
								opacityTo: 0.02,
								stops: [0, 100]
							}
						}
					: { type: 'solid', opacity: type === 'bar' ? 0.85 : 1 },
			plotOptions: {
				bar: {
					borderRadius: 3,
					columnWidth: '60%',
					dataLabels: { position: 'top' }
				}
			},
			markers: isScatter
				? { size: compact ? 3.5 : 5, strokeWidth: 0, hover: { size: 6 } }
				: { size: 0, hover: { size: compact ? 4 : 6 } },
			grid: {
				borderColor: '#e8e2db',
				strokeDashArray: 3,
				padding: { left: 4, right: 4, top: 0, bottom: 0 },
				yaxis: { lines: { show: true } },
				xaxis: { lines: { show: false } }
			},
			dataLabels: { enabled: false },
			xaxis,
			yaxis,
			tooltip: {
				theme: 'light',
				style: { fontSize: '12px', fontFamily: 'DM Sans, sans-serif' },
				x: isScatter
					? { formatter: (v: any) => formatY(Number(v)) }
					: { formatter: (_v: any, opts: any) => categories[opts.dataPointIndex] ?? '' },
				y: {
					formatter: (v: number) => `${formatY(v)}${result?.unit ? ' ' + result.unit : ''}`,
					title: { formatter: () => result?.yLabel ?? title }
				},
				marker: { show: !isScatter }
			},
			series: [{ name: result?.yLabel ?? title, data: seriesData }],
			noData: {
				text: 'No data',
				align: 'center',
				verticalAlign: 'middle',
				style: { color: '#a8a29e', fontSize: '12px', fontFamily: 'DM Sans, sans-serif' }
			}
		};
	}

	onMount(async () => {
		if (!browser || !chartEl) return;
		const ApexCharts = (await import('apexcharts')).default;
		chart = new ApexCharts(chartEl, buildOptions());
		await chart.render();
	});

	$effect(() => {
		// Track reactive deps explicitly
		void cleanPoints;
		void type;
		void color;
		void compact;
		untrack(() => {
			if (chart) {
				chart.updateOptions(buildOptions(), false, true);
			}
		});
	});

	onDestroy(() => {
		try {
			chart?.destroy();
		} catch {
			/* ignore */
		}
		chart = null;
	});

	function handleExpand(e: MouseEvent) {
		e.stopPropagation();
		onExpandClick?.();
	}
</script>

<div class="chart-wrap" class:compact>
	{#if compact && onExpandClick}
		<button class="expand-btn" onclick={handleExpand} aria-label="Expand chart" title="Expand">
			<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
				<path d="M3 7V3h4M13 9v4h-4M3 3l5 5M13 13l-5-5" />
			</svg>
		</button>
	{/if}
	<div class="chart-host" bind:this={chartEl}></div>
</div>

<style>
	.chart-wrap {
		position: relative;
		width: 100%;
	}
	.chart-host {
		width: 100%;
		min-height: 160px;
	}
	.chart-wrap:not(.compact) .chart-host {
		min-height: 380px;
	}
	.chart-host :global(.apexcharts-canvas) {
		width: 100% !important;
	}
	.compact .chart-host :global(.apexcharts-toolbar) { display: none !important; }
	.compact .chart-host :global(.apexcharts-tooltip) { font-size: 11px; }

	.chart-host :global(.apexcharts-canvas) { background: transparent !important; }
	.chart-host :global(.apexcharts-text) { font-family: 'DM Sans', sans-serif !important; }
	.chart-host :global(.apexcharts-tooltip) {
		border-radius: 10px !important;
		border: 1px solid var(--border) !important;
		box-shadow: var(--shadow-md) !important;
		background: var(--card) !important;
	}
	.chart-host :global(.apexcharts-tooltip-title) {
		background: var(--card-alt) !important;
		border-bottom: 1px solid var(--border) !important;
		font-weight: 600 !important;
		font-size: 11px !important;
	}

	.expand-btn {
		position: absolute;
		top: -4px;
		right: 0;
		width: 22px;
		height: 22px;
		border-radius: 6px;
		border: 1px solid var(--border);
		background: var(--card);
		color: var(--text-tertiary);
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		z-index: 2;
		opacity: 0.6;
		transition: opacity 0.15s, color 0.15s, border-color 0.15s, transform 0.1s;
	}
	.chart-wrap:hover .expand-btn { opacity: 1; }
	.expand-btn:hover { color: var(--text-primary); border-color: var(--text-tertiary); }
	.expand-btn:active { transform: scale(0.92); }
	@media (hover: none) {
		.expand-btn { opacity: 0.85; }
	}
</style>
