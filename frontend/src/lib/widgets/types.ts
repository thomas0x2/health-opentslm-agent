export interface HealthRecord {
	date: string;
	heart_rate_mean: number;
	heart_rate_min: number;
	heart_rate_max: number;
	resting_hr: number | null;
	hrv_ms: number | null;
	spo2_mean: number;
	sleep_score: number | null;
	steps_total: number;
	calories_total: number | null;
	workout_minutes: number;
	weight_kg: number | null;
	bp_systolic: number | null;
	bp_diastolic: number | null;
}

export type VizType = 'single_value' | 'line' | 'bar' | 'scatter' | 'area' | 'stacked_bar' | 'heatmap';

export interface Widget {
	id: string;
	title: string;
	description: string;
	vizType: VizType;
	computeFn: string;
	createdAt: string;
}

export type ComputeResult = SingleValueResult | SeriesResult;

export interface SingleValueResult {
	kind: 'single_value';
	value: number;
	unit: string;
	label: string;
	trend?: 'up' | 'down' | 'flat';
	trendValue?: number;
}

export interface SeriesResult {
	kind: 'series';
	series: Array<{ x: string | number; y: number; label?: string }>;
	xLabel?: string;
	yLabel?: string;
	unit?: string;
}

export interface WidgetProps {
	widget: Widget;
	records: HealthRecord[];
}
