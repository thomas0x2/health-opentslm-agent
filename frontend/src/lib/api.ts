function localApiBase(port: number) {
	if (typeof window === 'undefined') return `http://127.0.0.1:${port}`;
	return `${window.location.protocol}//${window.location.hostname}:${port}`;
}

const API_BASE = import.meta.env.VITE_API_BASE || localApiBase(5000);
const AGENT_API_BASE = import.meta.env.VITE_AGENT_API_BASE || localApiBase(5001);

async function api<T>(path: string, params?: Record<string, string | number | boolean | undefined>, init?: RequestInit): Promise<T> {
	return request<T>(API_BASE, path, params, init);
}

async function agentApi<T>(path: string, params?: Record<string, string | number | boolean | undefined>, init?: RequestInit): Promise<T> {
	return request<T>(AGENT_API_BASE, path, params, init);
}

async function request<T>(base: string, path: string, params?: Record<string, string | number | boolean | undefined>, init?: RequestInit): Promise<T> {
	const url = new URL(path, base);
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

export interface AgentDomain {
	name: string;
	title: string;
	description: string;
	advice_categories: string[];
	score_fields: string[];
	accepts_cross_domain_evidence: boolean;
}

export interface AdviceItem {
	category: string;
	headline: string;
	rationale: string;
	actionable_step: string;
	citations?: { paper: string; page: number }[];
	applies_to?: string | null;
}

export interface AdviceResponse {
	domain: string;
	agent_backend: string;
	features: Record<string, any>;
	narration?: Record<string, any> | null;
	queries: string[];
	retrieved_papers: { paper: string; page: number; snippet: string; score: number }[];
	advice: {
		summary: string;
		advice?: AdviceItem[];
		scores?: Record<string, number>;
		flags?: {
			name: string;
			severity: string;
			recommended_action: string;
			urgency: string;
		}[];
		overall_severity?: number;
		escalation_recommended?: boolean;
		red_flags?: string[];
		medical_disclaimer?: string;
		caveats?: string[];
	};
	latency_ms: Record<string, number>;
	window: { start: string; end: string };
}

export const getAgentDomains = () => agentApi<AgentDomain[]>('/api/agents');
export const getHealthCoachAgents = () => agentApi<AgentDomain[]>('/api/agents');

export const getAgentAdvice = (domain: string, opts?: { tone?: 'clinical' | 'coach'; includeOpenTslm?: boolean }) =>
	agentApi<AdviceResponse>(`/api/agents/${domain}`, {
		tone: opts?.tone,
		include_opentslm: opts?.includeOpenTslm === false ? '0' : '1'
	});

export interface HealthRawResponse {
	records: Record<string, any>[];
}

export const getHealthRaw = () => api<HealthRawResponse>('/api/health/raw');
