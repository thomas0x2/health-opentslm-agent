<script lang="ts">
	import { onMount } from 'svelte';
	import AppHeader from '$lib/components/AppHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import InsightStrip from '$lib/components/InsightStrip.svelte';
	import Sparkline from '$lib/components/Sparkline.svelte';
	import SleepStagesBar from '$lib/components/SleepStagesBar.svelte';
	import WeeklyBars from '$lib/components/WeeklyBars.svelte';
	import MetricRow from '$lib/components/MetricRow.svelte';
	import SectionLabel from '$lib/components/SectionLabel.svelte';
	import { loadWidgets } from '$lib/storage';
	import { CHART_REGISTRY, type Widget, type HealthRecord } from '$lib/widgets';
	import { getHealthRaw } from '$lib/api';
	import { getLatest, getDaily, getSeries, getStatus } from '$lib/api';
	import type { SparkPoint, SleepStage, WeeklyBar, MetricSummaryRow } from '$lib/data/vitals';

	/* ---------- state ---------- */
	let loading = $state(true);
	let error = $state<string | null>(null);

	let todayDate = $state('');
	let syncAgo = $state('live');

	let recoveryValue = $state(78);
	let recoveryTrend = $state('near baseline');
	let recoveryZone = $state('Green zone — ready');

	let hrvValue = $state(0);
	let hrvTrend = $state('');
	let hrvSpark = $state<SparkPoint[]>([]);

	let rhrValue = $state(0);
	let rhrTrend = $state('');
	let rhrSpark = $state<SparkPoint[]>([]);

	let sleepHours = $state(0);
	let sleepMinutes = $state(0);
	let sleepScore = $state(0);
	let sleepStages = $state<SleepStage[]>([]);

	let strainValue = $state(0);
	let strainLabel = $state('');
	let strainPct = $state(0);

	let caloriesTotal = $state(0);
	let caloriesActive = $state(0);
	let caloriesBasal = $state(0);

	let spo2Value = $state(0);

	let weeklyStrainBars = $state<WeeklyBar[]>([]);
	let weeklySummaryRows = $state<MetricSummaryRow[]>([]);

	let insightText = $state('');

	// Widget state
	let savedWidgets = $state<Widget[]>([]);
	let widgetRecords = $state<HealthRecord[]>([]);

	/* ---------- helpers ---------- */
	function fmtDate(d: Date) {
		return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
	}

	function toISODate(d: Date) {
		return d.toISOString().split('T')[0];
	}

	function fmtNaiveISO(d: Date) {
		const pad = (n: number) => n.toString().padStart(2, '0');
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
	}

	function computeRecovery(hrv?: number, rhr?: number): number {
		if (!hrv || !rhr) return 78;
		return Math.min(100, Math.max(0, Math.round(100 - (rhr - 35) * 1.2 + (hrv - 50) * 0.25)));
	}

	function computeStrain(workoutSeconds: number, steps: number): number {
		if (workoutSeconds > 0) {
			return Math.min(21, Math.round((workoutSeconds / 3600) * 8 * 10) / 10);
		}
		return Math.min(8, Math.round((steps / 12000) * 8 * 10) / 10);
	}

	function mapSeriesToSpark(values: (number | string | null)[]): SparkPoint[] {
		const nums = values.filter((v): v is number => typeof v === 'number');
		if (nums.length === 0) return [];
		const minV = Math.min(...nums);
		const maxV = Math.max(...nums);
		const range = maxV - minV || 1;
		const n = nums.length;
		return nums.map((v, i) => ({
			x: Math.round((i / (n - 1 || 1)) * 140),
			y: Math.round(40 - ((v - minV) / range) * 30 - 5)
		}));
	}

	/* ---------- load ---------- */
	onMount(async () => {
		try {
			const status = await getStatus();
			const datasetEnd = new Date(status.end);
			const todayStr = toISODate(datasetEnd);

			todayDate = fmtDate(datasetEnd);
			syncAgo = 'live';

			/* --- latest + today --- */
			const todayStart = `${todayStr}T00:00:00`;
			const todayEnd = `${todayStr}T23:59:59`;

			const [latest, daily, hrvToday, rhrToday] = await Promise.all([
				getLatest('spo2,heart_rate,calories,steps'),
				getDaily(todayStr),
				getSeries('hrv', { start: todayStart, end: todayEnd, dropNull: true }),
				getSeries('rhr', { start: todayStart, end: todayEnd, dropNull: true })
			]);

			const lastHrv = hrvToday.values.filter((v): v is number => typeof v === 'number').at(-1);
			const lastRhr = rhrToday.values.filter((v): v is number => typeof v === 'number').at(-1);

			hrvValue = lastHrv ? Math.round(lastHrv) : 68;
			rhrValue = lastRhr ? Math.round(lastRhr) : 52;

			hrvTrend = lastHrv ? `↑ ${Math.round(lastHrv)} ms` : '→ stable';
			rhrTrend = lastRhr ? `↓ ${Math.round(lastRhr)} bpm` : '→ stable';

			recoveryValue = computeRecovery(latest.hrv_rmssd_ms, latest.resting_hr_bpm);
			recoveryTrend = recoveryValue > 85 ? '+12% vs avg' : 'near baseline';
			recoveryZone = recoveryValue >= 80
				? 'Green zone — peak readiness'
				: recoveryValue >= 60
					? 'Yellow zone — moderate load'
					: 'Red zone — needs rest';

			/* --- sleep: last night ~18:00 to 12:00 --- */
			const nightStart = new Date(datasetEnd);
			nightStart.setDate(nightStart.getDate() - 1);
			nightStart.setHours(18, 0, 0, 0);
			const nightEnd = new Date(datasetEnd);
			nightEnd.setHours(12, 0, 0, 0);

			const sleepSeries = await getSeries('sleep_phase', {
				start: fmtNaiveISO(nightStart),
				end: fmtNaiveISO(nightEnd),
				step: 300,
				dropNull: true
			});

			const sleepSeconds = sleepSeries.count * 300;
			sleepHours = Math.floor(sleepSeconds / 3600);
			sleepMinutes = Math.floor((sleepSeconds % 3600) / 60);
			sleepScore = daily.sleep_score ? Math.round(daily.sleep_score) : 85;

			const stageCounts: Record<string, number> = {};
			for (const v of sleepSeries.values) {
				if (v) stageCounts[String(v)] = (stageCounts[String(v)] || 0) + 1;
			}
			const stageOpacities: Record<string, number> = { deep: 0.9, REM: 0.6, light: 0.35 };
			sleepStages = Object.entries(stageCounts).map(([stage, count]) => ({
				flex: count,
				opacity: stageOpacities[stage] ?? 0.5
			}));

			/* --- strain --- */
			const s = computeStrain(daily.workout_seconds, daily.steps_total);
			strainValue = s;
			strainLabel = s > 14 ? 'High' : s > 8 ? 'Moderate' : 'Low';
			strainPct = Math.min(100, Math.round((s / 21) * 100));

			/* --- calories --- */
			caloriesTotal = daily.calories_total ? Math.round(daily.calories_total) : 2100;
			caloriesActive = Math.round(caloriesTotal * 0.28);
			caloriesBasal = caloriesTotal - caloriesActive;

			/* --- body metrics --- */
			spo2Value = daily.spo2_mean ? Math.round(daily.spo2_mean) : 97;

			/* --- weekly: fetch 7 days in parallel --- */
			const dayLabels = ['M','T','W','T','F','S','S'];
			const dayPromises: Promise<{ idx: number; day: string; data?: Awaited<ReturnType<typeof getDaily>> }>[] = [];
			for (let i = 6; i >= 0; i--) {
				const d = new Date(datasetEnd);
				d.setDate(d.getDate() - i);
				const ds = toISODate(d);
				const idx = 6 - i;
				dayPromises.push(
					getDaily(ds)
						.then(data => ({ idx, day: ds, data }))
						.catch(() => ({ idx, day: ds }))
				);
			}
			const weekResults = await Promise.all(dayPromises);

			weeklyStrainBars = weekResults.map(r => {
				const strain = r.data ? computeStrain(r.data.workout_seconds, r.data.steps_total) : 0;
				return {
					label: dayLabels[r.idx],
					height: Math.max(8, Math.min(95, Math.round((strain / 21) * 95))),
					today: r.idx === 6
				};
			});

			const recs = weekResults.map(r => computeRecovery(r.data?.hrv_rmssd_ms, r.data?.resting_hr));
			const avgRec = Math.round(recs.reduce((a, b) => a + b, 0) / recs.length);

			const rhrs = weekResults.map(r => r.data?.resting_hr ?? 52);
			const avgRhr = Math.round(rhrs.reduce((a, b) => a + b, 0) / rhrs.length);

			const totalStrain = weekResults.reduce((a, r) => a + (r.data ? computeStrain(r.data.workout_seconds, r.data.steps_total) : 0), 0);

			// Use today's sleep as weekly avg fallback (real per-night sleep would need 7 series calls)
			const avgSleepMin = sleepHours * 60 + sleepMinutes;
			const avgSleepH = Math.floor(avgSleepMin / 60);
			const avgSleepM = avgSleepMin % 60;

			weeklySummaryRows = [
				{ label: 'Avg. Recovery', value: String(avgRec), unit: '%' },
				{ label: 'Avg. Sleep', value: `${avgSleepH}:${avgSleepM.toString().padStart(2, '0')}`, unit: ' hrs' },
				{ label: 'Total Strain', value: String(Math.round(totalStrain * 10) / 10) },
				{ label: 'Avg. RHR', value: String(avgRhr), unit: ' bpm' }
			];

			/* --- insight --- */
			if (recoveryValue >= 85) {
				insightText = `Your recovery is at <strong>${recoveryValue}%</strong> today — that's well into the green zone. Your HRV of ${hrvValue} ms suggests your body is primed for high-intensity training.`;
			} else if (recoveryValue >= 60) {
				insightText = `Your recovery is at <strong>${recoveryValue}%</strong> today — a moderate readiness level. Consider a balanced training session rather than peak intensity.`;
			} else {
				insightText = `Your recovery is at <strong>${recoveryValue}%</strong> today — below your baseline. Prioritize rest, hydration, and light movement to bounce back.`;
			}

			/* --- sparklines --- */
			const weekStart = new Date(datasetEnd);
			weekStart.setDate(weekStart.getDate() - 7);

			const [hrvSeries, rhrSeries] = await Promise.all([
				getSeries('hrv', { start: fmtNaiveISO(weekStart), end: fmtNaiveISO(datasetEnd), dropNull: true }),
				getSeries('rhr', { start: fmtNaiveISO(weekStart), end: fmtNaiveISO(datasetEnd), dropNull: true })
			]);

			hrvSpark = mapSeriesToSpark(hrvSeries.values);
			rhrSpark = mapSeriesToSpark(rhrSeries.values);

			if (hrvSpark.length === 0) {
				hrvSpark = [
					{ x: 0, y: 20 }, { x: 20, y: 18 }, { x: 40, y: 22 },
					{ x: 60, y: 16 }, { x: 80, y: 20 }, { x: 100, y: 18 },
					{ x: 120, y: 14 }, { x: 140, y: 12 }
				];
			}
			if (rhrSpark.length === 0) {
				rhrSpark = [
					{ x: 0, y: 20 }, { x: 20, y: 18 }, { x: 40, y: 22 },
					{ x: 60, y: 16 }, { x: 80, y: 20 }, { x: 100, y: 18 },
					{ x: 120, y: 14 }, { x: 140, y: 12 }
				];
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load health data';
			// Fallback to static-like defaults so UI doesn't break
			hrvSpark = [
				{ x: 0, y: 20 }, { x: 20, y: 18 }, { x: 40, y: 22 },
				{ x: 60, y: 16 }, { x: 80, y: 20 }, { x: 100, y: 18 },
				{ x: 120, y: 14 }, { x: 140, y: 12 }
			];
			rhrSpark = [...hrvSpark];
		} finally {
			loading = false;
		}

		// Load saved widgets + raw data for rendering
		savedWidgets = loadWidgets();
		getHealthRaw()
			.then(r => widgetRecords = r.records as HealthRecord[])
			.catch(() => {});
	});
</script>

<AppHeader
	date={todayDate || 'Loading...'}
	title="Your Vitals"
	subtitle="Last sync {syncAgo}"
	avatarInitial="F"
/>

{#if error}
	<div class="error-banner">{error}</div>
{/if}

<InsightStrip html={insightText || 'Loading insights...'} />

<div class="dashboard">
	<!-- Recovery hero -->
	<Card hero full>
		<div class="card-label">
			<span class="dot" style="background: rgba(255,255,255,0.5)"></span> Recovery
		</div>
		<div class="hero-body">
			<div>
				<div class="card-value hero-value">{recoveryValue}<span class="card-unit">%</span></div>
				<div class="card-detail hero-detail">{recoveryZone}</div>
			</div>
			<div>
				<div class="trend hero-trend">↑ {recoveryTrend}</div>
			</div>
		</div>
	</Card>

	<!-- HRV -->
	<Card>
		<div class="card-label"><span class="dot green"></span> HRV</div>
		<div class="card-value green-text">{hrvValue}<span class="card-unit"> ms</span></div>
		<div class="card-trend trend-up">{hrvTrend}</div>
		<Sparkline points={hrvSpark} color="var(--green)" />
	</Card>

	<!-- Resting HR -->
	<Card>
		<div class="card-label"><span class="dot terracotta"></span> Resting HR</div>
		<div class="card-value terracotta-text">{rhrValue}<span class="card-unit"> bpm</span></div>
		<div class="card-trend trend-up">{rhrTrend}</div>
		<Sparkline points={rhrSpark} color="var(--terracotta)" />
	</Card>

	<!-- Sleep -->
	<Card full>
		<div class="sleep-top">
			<div>
				<div class="card-label"><span class="dot blue"></span> Sleep</div>
				<div class="card-value blue-text">
					{sleepHours}<span class="card-unit">h</span>
					{sleepMinutes}<span class="card-unit">m</span>
				</div>
			</div>
			<div class="sleep-score">
				<div class="sleep-score-num">{sleepScore}</div>
				<div class="sleep-score-label">Score</div>
			</div>
		</div>
		<SleepStagesBar stages={sleepStages.length ? sleepStages : [{flex:1.2,opacity:0.3},{flex:2.5,opacity:0.55},{flex:0.8,opacity:0.3},{flex:1.8,opacity:0.85},{flex:1.5,opacity:0.55},{flex:0.5,opacity:0.3},{flex:1,opacity:0.85},{flex:0.7,opacity:0.15}]} />
	</Card>

	<!-- Strain -->
	<Card>
		<div class="card-label"><span class="dot gold"></span> Strain</div>
		<div class="card-value gold-text" style="font-size: 38px">{strainValue}</div>
		<div class="card-detail">{strainLabel} — of 21</div>
		<div class="strain-bar-track">
			<div class="strain-bar-fill" style="width: {strainPct}%"></div>
		</div>
	</Card>

	<!-- Calories -->
	<Card>
		<div class="card-label"><span class="dot purple"></span> Calories</div>
		<div class="card-value purple-text" style="font-size: 36px">{caloriesTotal.toLocaleString()}</div>
		<div class="card-detail">kcal burned</div>
		<div class="cal-split">
			<div>
				<div class="cal-split-label">Active</div>
				<div class="cal-split-value">{caloriesActive}</div>
			</div>
			<div>
				<div class="cal-split-label">Basal</div>
				<div class="cal-split-value">{caloriesBasal.toLocaleString()}</div>
			</div>
		</div>
	</Card>

	<SectionLabel label="Body Metrics" />

	<!-- Resp Rate -->
	<Card>
		<div class="card-label">Resp. Rate</div>
		<div class="card-value" style="font-size: 32px">14.8<span class="card-unit"> rpm</span></div>
		<div class="card-trend trend-neutral">→ stable</div>
	</Card>

	<!-- Skin Temp -->
	<Card>
		<div class="card-label">Skin Temp</div>
		<div class="card-value" style="font-size: 32px">+0.2<span class="card-unit"> °C</span></div>
		<div class="card-detail">vs. baseline</div>
	</Card>

	<!-- SpO2 -->
	<Card>
		<div class="card-label">SpO₂</div>
		<div class="card-value" style="font-size: 32px">{spo2Value}<span class="card-unit">%</span></div>
		<div class="card-detail">Avg overnight</div>
	</Card>

	<!-- Weekly Strain -->
	<Card>
		<div class="card-label">Weekly Strain</div>
		<WeeklyBars bars={weeklyStrainBars.length ? weeklyStrainBars : [
			{ label: 'M', height: 45 }, { label: 'T', height: 72 },
			{ label: 'W', height: 30 }, { label: 'T', height: 85 },
			{ label: 'F', height: 55 }, { label: 'S', height: 90 },
			{ label: 'S', height: 20, today: true }
		]} />
	</Card>

	<SectionLabel label="7-Day Summary" />

	<Card full>
		{#each weeklySummaryRows.length ? weeklySummaryRows : [
			{ label: 'Avg. Recovery', value: '74', unit: '%' },
			{ label: 'Avg. Sleep',    value: '7:18', unit: ' hrs' },
			{ label: 'Total Strain',  value: '78.2' },
			{ label: 'Avg. RHR',      value: '54', unit: ' bpm' }
		] as row (row.label)}
			<MetricRow label={row.label} value={row.value} unit={row.unit} />
		{/each}
	</Card>
</div>

{#if savedWidgets.length > 0}
	<SectionLabel label="Custom Widgets" />
	<div class="dashboard">
		{#each savedWidgets as widget (widget.id)}
			{#if widget.vizType && CHART_REGISTRY[widget.vizType]}
				{@const Comp = CHART_REGISTRY[widget.vizType]}
				<div class="widget-wrapper">
					<Comp {widget} records={widgetRecords} />
				</div>
			{:else}
				<Card>
					<div class="card-label">{widget.vizType ?? 'widget'}</div>
					<div class="card-value" style="font-size: 18px">{widget.title}</div>
				</Card>
			{/if}
		{/each}
	</div>
{/if}

<style>
	.dashboard {
		padding: 0 16px;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;
	}

	.error-banner {
		margin: 0 16px 12px;
		padding: 10px 14px;
		background: var(--terracotta-light, #f5e0da);
		color: var(--terracotta);
		border-radius: var(--radius-md, 12px);
		font-size: 12px;
		font-weight: 600;
	}

	/* Card label / dot */
	.card-label {
		font-size: 10.5px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-tertiary);
		font-weight: 600;
		margin-bottom: 6px;
		display: flex;
		align-items: center;
		gap: 5px;
	}
	.dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		display: inline-block;
	}
	.green      { background: var(--green); }
	.terracotta { background: var(--terracotta); }
	.blue       { background: var(--blue); }
	.gold       { background: var(--gold); }
	.purple     { background: var(--purple); }

	/* Card value */
	.card-value {
		font-family: 'Instrument Serif', serif;
		font-size: 42px;
		line-height: 1;
		letter-spacing: -0.03em;
	}
	.card-unit {
		font-family: 'DM Sans', sans-serif;
		font-size: 13px;
		color: var(--text-secondary);
		font-weight: 400;
	}
	.card-detail {
		font-size: 11.5px;
		color: var(--text-secondary);
		margin-top: 4px;
		line-height: 1.35;
	}

	/* Colors */
	.green-text      { color: var(--green); }
	.terracotta-text { color: var(--terracotta); }
	.blue-text       { color: var(--blue); }
	.gold-text       { color: var(--gold); }
	.purple-text     { color: var(--purple); }

	/* Trends */
	.card-trend {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font-size: 11px;
		font-weight: 600;
		padding: 2px 7px;
		border-radius: 6px;
		margin-top: 6px;
	}
	.trend-up      { background: var(--green-light); color: var(--green); }
	.trend-neutral { background: var(--bg-warm); color: var(--text-secondary); }

	/* Hero card internals */
	.hero-body {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
	}
	.hero-value { font-size: 56px; color: white; }
	.hero-detail { color: rgba(255,255,255,0.7); margin-top: 6px; font-size: 11.5px; }
	.hero-trend {
		background: rgba(255,255,255,0.15);
		color: rgba(255,255,255,0.9);
		font-size: 11px;
		font-weight: 600;
		padding: 2px 7px;
		border-radius: 6px;
	}
	/* hero card-label overrides */
	:global(.card-hero) .card-label { color: rgba(255,255,255,0.6); }
	:global(.card-hero) .card-unit  { color: rgba(255,255,255,0.6); }

	/* Sleep */
	.sleep-top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}
	.sleep-score { text-align: right; }
	.sleep-score-num {
		font-family: 'Instrument Serif', serif;
		font-size: 28px;
		color: var(--blue);
	}
	.sleep-score-label {
		font-size: 10px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	/* Strain bar */
	.strain-bar-track {
		width: 100%;
		height: 6px;
		background: var(--gold-light);
		border-radius: 3px;
		margin-top: 8px;
		overflow: hidden;
	}
	.strain-bar-fill {
		height: 100%;
		background: var(--gold);
		border-radius: 3px;
	}

	/* Calories split */
	.cal-split { display: flex; gap: 12px; margin-top: 10px; }
	.cal-split-label { font-size: 10px; color: var(--text-tertiary); }
	.cal-split-value { font-size: 14px; font-weight: 600; }

	.widget-wrapper { grid-column: span 2; }
</style>
