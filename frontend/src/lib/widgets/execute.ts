import type { Widget, HealthRecord, ComputeResult } from './types';

export function executeWidget(widget: Widget, records: HealthRecord[]): ComputeResult {
	try {
		const fn = new Function('records', widget.computeFn);
		return fn(records) as ComputeResult;
	} catch (e: any) {
		throw new Error(`Widget "${widget.title}" failed: ${e.message || String(e)}`);
	}
}
