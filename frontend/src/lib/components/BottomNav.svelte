<script lang="ts">
	import { page } from '$app/stores';

	const items = [
		{ href: '/',        label: 'Dashboard', icon: 'dashboard' },
		{ href: '/builder', label: 'Build',      icon: 'build' },
		{ href: '/agent',   label: 'Agent',      icon: 'agent' }
	];

	function isActive(href: string, pathname: string) {
		return href === '/' ? pathname === '/' : pathname.startsWith(href);
	}
</script>

<nav class="bottom-nav">
	{#each items as item}
		<a href={item.href} class="nav-item" class:active={isActive(item.href, $page.url.pathname)}>
			{#if item.icon === 'dashboard'}
				<svg viewBox="0 0 24 24">
					<rect x="3" y="3" width="7" height="7" rx="1.5"/>
					<rect x="14" y="3" width="7" height="4" rx="1.5"/>
					<rect x="3" y="14" width="7" height="4" rx="1.5"/>
					<rect x="14" y="11" width="7" height="7" rx="1.5"/>
				</svg>
			{:else if item.icon === 'build'}
				<svg viewBox="0 0 24 24">
					<path d="M12 5v14M5 12h14" stroke-linecap="round" stroke-linejoin="round"/>
					<rect x="3" y="3" width="18" height="18" rx="3"/>
				</svg>
			{:else}
				<svg viewBox="0 0 24 24">
					<path d="M12 3c-4.97 0-9 3.13-9 7 0 2.38 1.5 4.5 3.8 5.8L6 20l3.7-2.1c.74.14 1.5.1 2.3.1 4.97 0 9-3.13 9-7s-4.03-7-9-7z"/>
				</svg>
			{/if}
			<span>{item.label}</span>
		</a>
	{/each}
</nav>

<style>
	.bottom-nav {
		position: fixed;
		bottom: 0;
		left: 50%;
		transform: translateX(-50%);
		width: 100%;
		max-width: 430px;
		background: rgba(244, 240, 235, 0.85);
		backdrop-filter: blur(20px);
		-webkit-backdrop-filter: blur(20px);
		border-top: 1px solid var(--border);
		display: flex;
		padding: 8px 0;
		padding-bottom: max(8px, env(safe-area-inset-bottom));
		z-index: 100;
	}
	.nav-item {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 3px;
		padding: 6px 0;
		cursor: pointer;
		transition: all 0.2s;
		border: none;
		background: none;
		font-family: inherit;
		text-decoration: none;
	}
	.nav-item svg {
		width: 22px;
		height: 22px;
		stroke: var(--text-tertiary);
		fill: none;
		stroke-width: 1.8;
		transition: all 0.2s;
	}
	.nav-item span {
		font-size: 10px;
		color: var(--text-tertiary);
		font-weight: 500;
		letter-spacing: 0.03em;
		transition: color 0.2s;
	}
	.nav-item.active svg { stroke: var(--green); }
	.nav-item.active span { color: var(--green); font-weight: 600; }
</style>
