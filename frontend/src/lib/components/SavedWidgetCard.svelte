<script lang="ts">
	import type { SavedWidget } from '$lib/data/vitals';
	interface Props { widget: SavedWidget | { id?: string; title?: string; name?: string; description?: string; type?: string; vizType?: string; icon?: string; color?: string } }
	let { widget }: Props = $props();

	let displayName = $derived((widget as any).title || (widget as any).name || 'Widget');
	let displayType = $derived((widget as any).type || (widget as any).vizType || (widget as any).description || '');
	let displayIcon = $derived((widget as any).icon ?? 'chart');
	let displayColor = $derived(((widget as any).color ?? 'green').replace(/^--/, ''));

	const colorMap: Record<string, { bg: string; fg: string }> = {
		green:      { bg: 'var(--green-light)',      fg: 'var(--green)' },
		blue:       { bg: 'var(--blue-light)',       fg: 'var(--blue)' },
		terracotta: { bg: 'var(--terracotta-light)', fg: 'var(--terracotta)' },
		gold:       { bg: 'var(--gold-light)',       fg: 'var(--gold)' },
		purple:     { bg: 'var(--purple-light)',     fg: 'var(--purple)' }
	};
	const c = $derived(colorMap[displayColor] ?? { bg: 'var(--bg-warm)', fg: 'var(--text-secondary)' });
</script>

<div class="saved-card">
	<div class="icon" style="background: {c.bg}; color: {c.fg}">
		{#if displayIcon === 'chart'}
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
				<rect x="3" y="3" width="18" height="18" rx="2"/>
				<path d="M7 17l4-8 3 5 2-3 4 6"/>
			</svg>
		{:else if displayIcon === 'clock'}
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
				<circle cx="12" cy="12" r="9"/>
				<path d="M12 3v9l6 3"/>
			</svg>
		{:else}
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M3 20h18M5 20V10M9 20V4M13 20v-8M17 20V8M21 20V2"/>
			</svg>
		{/if}
	</div>
	<div>
		<div class="name">{displayName}</div>
		<div class="type">{displayType}</div>
	</div>
</div>

<style>
	.saved-card {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 14px;
		background: var(--card);
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
		transition: box-shadow 0.2s;
	}
	.saved-card:active { box-shadow: var(--shadow-md); }
	.icon {
		width: 34px;
		height: 34px;
		border-radius: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
	.type { font-size: 11px; color: var(--text-tertiary); margin-top: 1px; }
</style>
