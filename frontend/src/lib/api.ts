const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000';

async function api<T>(path: string, params?: Record<string, string | number | boolean | undefined>, init?: RequestInit): Promise<T> {
	const url = new URL(path, API_BASE);
	if (params) {
		for (const [k, v] of Object.entries(params)) {
			if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
		}
	}
	const res = await fetch(url, init);
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.error || `${res.status} ${res.statusText}`);
	}
	return res.json();
}

export interface LatestReading {
	timestamp: string;
	heart_rate_bpm?: number;
	resting_hr_bpm?: number;
	hrv_rmssd_ms?: number;
	spo2_pct?: number;
	steps_today?: number;
	calories_today?: number;
	workout_flag?: number;
	sleep_score?: number;
	weight_kg?: number;
	bp_systolic?: number;
	bp_diastolic?: number;
}

export interface DailySummary {
	day: string;
	steps_total: number;
	calories_total?: number;
	heart_rate: { mean: number; min: number; max: number };
	resting_hr?: number;
	hrv_rmssd_ms?: number;
	spo2_mean?: number;
	workout_seconds: number;
	sleep_score?: number;
	weight_kg?: number;
	blood_pressure?: string;
}

export interface SeriesResponse {
	column: string;
	count: number;
	timestamps: string[];
	values: (number | string | null)[];
}

export interface EventsResponse {
	workouts: { start: string; end: string; duration_s: number }[];
	weigh_ins: { timestamp: string; weight_kg: number }[];
	blood_pressure: { timestamp: string; systolic: number; diastolic: number }[];
	sleep_scores: { timestamp: string; score: number }[];
}

export interface StatusResponse {
	rows: number;
	start: string;
	end: string;
	columns: string[];
}

export const getStatus = () => api<StatusResponse>('/api/status');

export const getLatest = (columns?: string) =>
	api<LatestReading>('/api/latest', { columns });

export const getDaily = (day: string) =>
	api<DailySummary>('/api/daily', { day });

export const getSeries = (column: string, opts?: { start?: string; end?: string; step?: number; dropNull?: boolean }) =>
	api<SeriesResponse>(`/api/series/${column}`, {
		start: opts?.start,
		end: opts?.end,
		step: opts?.step,
		drop_null: opts?.dropNull ? '1' : undefined
	});

export const getEvents = (opts?: { start?: string; end?: string }) =>
	api<EventsResponse>('/api/events', {
		start: opts?.start,
		end: opts?.end
	});

export interface AgentResponse {
	reply: string;
	widget?: {
		id: string;
		title: string;
		description: string;
		vizType: string;
		computeFn: string;
		createdAt: string;
	};
	error?: string;
}

export const sendAgentMessage = (prompt: string) =>
	api<AgentResponse>('/api/agent', undefined, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ prompt }),
	});

export interface HealthRawResponse {
	records: Record<string, any>[];
}

export const getHealthRaw = () => api<HealthRawResponse>('/api/health/raw');
