export interface SparkPoint { x: number; y: number }
export interface SleepStage { flex: number; opacity: number }
export interface WeeklyBar { label: string; height: number; today?: boolean }
export interface MetricSummaryRow { label: string; value: string; unit?: string }
export interface SavedWidget { id: string; name: string; type: string; color: string; icon: 'chart' | 'clock' | 'bars' }
export interface ChatMessage { role: 'agent' | 'user'; text: string }

export const today = { date: 'Wednesday, May 21', syncAgo: '12 min ago' };

export const recovery = { value: 87, trend: '+12% vs avg', zone: 'Green zone — peak readiness' };

export const hrv = {
	value: 68, unit: 'ms', trend: '↑ 14%',
	spark: [
		{ x: 0, y: 28 }, { x: 20, y: 24 }, { x: 40, y: 30 },
		{ x: 60, y: 22 }, { x: 80, y: 18 }, { x: 100, y: 14 },
		{ x: 120, y: 16 }, { x: 140, y: 10 }
	] satisfies SparkPoint[],
	color: 'var(--green)'
};

export const restingHr = {
	value: 52, unit: 'bpm', trend: '↓ 3 bpm',
	spark: [
		{ x: 0, y: 20 }, { x: 20, y: 18 }, { x: 40, y: 22 },
		{ x: 60, y: 16 }, { x: 80, y: 20 }, { x: 100, y: 18 },
		{ x: 120, y: 14 }, { x: 140, y: 12 }
	] satisfies SparkPoint[],
	color: 'var(--terracotta)'
};

export const sleep = {
	hours: 7, minutes: 42, score: 92,
	stages: [
		{ flex: 1.2, opacity: 0.3 }, { flex: 2.5, opacity: 0.55 },
		{ flex: 0.8, opacity: 0.3 }, { flex: 1.8, opacity: 0.85 },
		{ flex: 1.5, opacity: 0.55 }, { flex: 0.5, opacity: 0.3 },
		{ flex: 1, opacity: 0.85 }, { flex: 0.7, opacity: 0.15 }
	] satisfies SleepStage[]
};

export const strain = { value: 12.4, max: 21, pct: 59, label: 'Moderate' };

export const calories = { total: 2340, active: 680, basal: 1660 };

export const bodyMetrics = {
	respRate: { value: '14.8', unit: 'rpm', trend: '→ stable' },
	skinTemp: { value: '+0.2', unit: '°C', detail: 'vs. baseline' },
	spo2: { value: 97, unit: '%', detail: 'Avg overnight' }
};

export const weeklyStrain: WeeklyBar[] = [
	{ label: 'M', height: 45 }, { label: 'T', height: 72 },
	{ label: 'W', height: 30 }, { label: 'T', height: 85 },
	{ label: 'F', height: 55 }, { label: 'S', height: 90 },
	{ label: 'S', height: 20, today: true }
];

export const weeklySummary: MetricSummaryRow[] = [
	{ label: 'Avg. Recovery', value: '74', unit: '%' },
	{ label: 'Avg. Sleep',    value: '7:18', unit: ' hrs' },
	{ label: 'Total Strain',  value: '78.2' },
	{ label: 'Avg. RHR',      value: '54', unit: ' bpm' }
];

export const insight = {
	icon: '◈',
	text: 'Your HRV is trending <strong>14% above baseline</strong> this week. Recovery patterns suggest you can handle a high-intensity session today.'
};

export const savedWidgets: SavedWidget[] = [
	{ id: '1', name: 'HRV by Weekday',     type: 'Bar chart',    color: '--green',     icon: 'chart' },
	{ id: '2', name: 'Sleep Consistency',  type: 'Radial chart', color: '--blue',      icon: 'clock' },
	{ id: '3', name: 'Strain vs Recovery', type: 'Scatter plot', color: '--terracotta',icon: 'bars' }
];

export const agentMessages: ChatMessage[] = [
	{ role: 'agent', text: 'Good morning. Your recovery is at 87% today — that\'s well into the green zone and 12 points above your 30-day average. Your HRV trend has been climbing steadily this week.' },
	{ role: 'agent', text: 'Based on your current readiness and strain history, today would be a good day for a high-intensity workout. You\'ve had two consecutive low-strain days, so your body is primed for it.' },
	{ role: 'user',  text: 'I\'ve been sleeping later than usual. Is that affecting anything?' },
	{ role: 'agent', text: 'Your sleep onset has shifted ~40 minutes later compared to your baseline over the past 5 days. Despite this, your total sleep time has remained consistent because you\'re waking later too. Your deep sleep percentage is slightly down (18% vs. your typical 22%), which could become an issue if the trend continues. I\'d suggest anchoring your wake time and letting your body adjust the onset naturally.' }
];

export const agentSuggestions = ['How\'s my HRV trend?', 'Optimize my sleep', 'Training plan', 'Weekly report'];

export const builderSuggestions = [
	'Sleep vs. strain correlation', 'HRV trend 30 days',
	'Recovery heatmap', 'HR zones breakdown'
];

export const builderPreviewBars = [
	{ label: 'Mon', height: 90, opacity: 1 },
	{ label: 'Tue', height: 62, opacity: 0.7 },
	{ label: 'Wed', height: 55, opacity: 0.6 },
	{ label: 'Thu', height: 48, opacity: 0.55 },
	{ label: 'Fri', height: 60, opacity: 0.65 },
	{ label: 'Sat', height: 72, opacity: 0.8 },
	{ label: 'Sun', height: 95, opacity: 1 }
];
