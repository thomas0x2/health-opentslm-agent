export { default as SingleValueWidget } from './SingleValueWidget.svelte';
export { default as LineWidget } from './LineWidget.svelte';
export { default as BarWidget } from './BarWidget.svelte';
export { default as ScatterWidget } from './ScatterWidget.svelte';
export { default as AreaWidget } from './AreaWidget.svelte';
export { default as StackedBarWidget } from './StackedBarWidget.svelte';
export { default as HeatmapWidget } from './HeatmapWidget.svelte';
export { executeWidget } from './execute';
export type * from './types';

import type { VizType, Widget, HealthRecord } from './types';
import SingleValueWidget from './SingleValueWidget.svelte';
import LineWidget from './LineWidget.svelte';
import BarWidget from './BarWidget.svelte';
import ScatterWidget from './ScatterWidget.svelte';
import AreaWidget from './AreaWidget.svelte';
import StackedBarWidget from './StackedBarWidget.svelte';
import HeatmapWidget from './HeatmapWidget.svelte';

export const CHART_REGISTRY: Record<VizType, any> = {
	single_value: SingleValueWidget,
	line: LineWidget,
	bar: BarWidget,
	scatter: ScatterWidget,
	area: AreaWidget,
	stacked_bar: StackedBarWidget,
	heatmap: HeatmapWidget,
};

export function renderWidget(widget: Widget, records: HealthRecord[]) {
	const Component = CHART_REGISTRY[widget.vizType];
	if (!Component) return null;
	return { Component, props: { widget, records } };
}
