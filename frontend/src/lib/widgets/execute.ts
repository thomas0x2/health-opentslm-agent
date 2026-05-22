import type { Widget, HealthRecord, ComputeResult, SeriesResult } from './types';

const NUMERIC_REGEX = /^-?\d+(\.\d+)?$/;

/**
 * Run the widget's computeFn and post-process the result so the chart layer
 * gets clean, well-formed data even when the AI produced something quirky.
 *
 * - Coerce numeric strings to numbers
 * - Drop entries with non-finite y values
 * - Sort by x when x is date-like or fully numeric
 * - Dedupe identical x values (keep last)
 */
export function executeWidget(widget: Widget, records: HealthRecord[]): ComputeResult {
	let raw: ComputeResult;
	try {
		const fn = new Function('records', widget.computeFn);
		raw = fn(records) as ComputeResult;
	} catch (e: any) {
		throw new Error(`Widget "${widget.title}" failed: ${e.message || String(e)}`);
	}

	if (!raw || typeof raw !== 'object' || !('kind' in raw)) {
		throw new Error(`Widget "${widget.title}" returned invalid shape (missing "kind" field)`);
	}

	if (raw.kind === 'single_value') {
		const v = (raw as any).value;
		const value = typeof v === 'string' && NUMERIC_REGEX.test(v) ? Number(v) : v;
		if (typeof value !== 'number' || !Number.isFinite(value)) {
			throw new Error(`Widget "${widget.title}" single_value must be a finite number`);
		}
		return {
			kind: 'single_value',
			value,
			unit: String((raw as any).unit ?? ''),
			label: String((raw as any).label ?? widget.title),
			trend: (raw as any).trend,
			trendValue: (raw as any).trendValue
		};
	}

	if (raw.kind === 'series') {
		const s = raw as SeriesResult;
		if (!Array.isArray(s.series)) {
			throw new Error(`Widget "${widget.title}" series must be an array`);
		}
		return sanitizeSeries(s);
	}

	throw new Error(`Widget "${widget.title}" unknown kind: ${(raw as any).kind}`);
}

function sanitizeSeries(s: SeriesResult): SeriesResult {
	// Step 1: coerce + filter
	const cleaned = s.series
		.map((p) => {
			let y = p.y as any;
			if (typeof y === 'string' && NUMERIC_REGEX.test(y)) y = Number(y);
			let x = p.x as any;
			if (typeof x === 'string' && NUMERIC_REGEX.test(x)) {
				// Only convert if it's not a date — i.e. no dash separators
				if (!/^\d{4}-\d{2}/.test(x)) x = Number(x);
			}
			return { x, y, label: p.label };
		})
		.filter((p) => typeof p.y === 'number' && Number.isFinite(p.y));

	// Step 2: sort by x when sensible
	const allDateLike = cleaned.every(
		(p) => typeof p.x === 'string' && /^\d{4}-\d{2}-\d{2}/.test(p.x)
	);
	const allNumeric = cleaned.every((p) => typeof p.x === 'number' && Number.isFinite(p.x));
	if (allDateLike) {
		cleaned.sort((a, b) => String(a.x).localeCompare(String(b.x)));
	} else if (allNumeric) {
		cleaned.sort((a, b) => (a.x as number) - (b.x as number));
	}

	// Step 3: dedupe consecutive identical x (keep last)
	const deduped: typeof cleaned = [];
	for (const p of cleaned) {
		if (deduped.length && deduped[deduped.length - 1].x === p.x) {
			deduped[deduped.length - 1] = p;
		} else {
			deduped.push(p);
		}
	}

	return {
		kind: 'series',
		series: deduped,
		xLabel: s.xLabel,
		yLabel: s.yLabel,
		unit: s.unit
	};
}
