import type { Widget } from '$lib/widgets/types';

const STORAGE_KEY = 'vibedash_widgets';

export function loadWidgets(): Widget[] {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		if (!Array.isArray(parsed)) return [];
		return parsed.filter(w => w && w.id && w.vizType && w.computeFn);
	} catch {
		return [];
	}
}

export function saveWidgets(widgets: Widget[]): void {
	localStorage.setItem(STORAGE_KEY, JSON.stringify(widgets));
}

export function addWidget(widget: Widget): Widget[] {
	const widgets = loadWidgets();
	const updated = [...widgets, widget];
	saveWidgets(updated);
	return updated;
}

export function removeWidget(id: string): Widget[] {
	const widgets = loadWidgets().filter(w => w.id !== id);
	saveWidgets(widgets);
	return widgets;
}
