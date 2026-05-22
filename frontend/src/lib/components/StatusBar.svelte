<script lang="ts">
	const time = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: false });
</script>

<div class="status-bar">
	<span>{time}</span>
	<div class="icons">
		<!-- Signal -->
		<svg viewBox="0 0 16 12"><path d="M1 8.5h1.5v3H1zM4 6h1.5v5.5H4zM7 3.5h1.5v8H7zM10 1h1.5v10.5H10z" fill="currentColor" stroke="none"/></svg>
		<!-- WiFi -->
		<svg viewBox="0 0 16 12">
			<path d="M8 3C5.5 3 3.3 4 1.8 5.7l1.1 1.1C4.2 5.3 6 4.5 8 4.5s3.8.8 5.1 2.3l1.1-1.1C12.7 4 10.5 3 8 3zm0 3.5c-1.4 0-2.6.6-3.5 1.5l1.1 1.1c.6-.6 1.4-1.1 2.4-1.1s1.8.4 2.4 1.1l1.1-1.1c-.9-1-2.1-1.5-3.5-1.5zM8 10a1.25 1.25 0 110 2.5A1.25 1.25 0 018 10z" fill="currentColor" stroke="none"/>
		</svg>
		<!-- Battery -->
		<svg viewBox="0 0 28 14">
			<rect x="0.5" y="0.5" width="23" height="13" rx="3" stroke="currentColor" fill="none" stroke-width="1"/>
			<rect x="25" y="4" width="2" height="6" rx="1" fill="currentColor"/>
			<rect x="2" y="2" width="18" height="9" rx="1.5" fill="currentColor"/>
		</svg>
	</div>
</div>

<style>
	.status-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 24px;
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-primary);
	}
	.icons {
		display: flex;
		gap: 5px;
		align-items: center;
	}
	.icons svg {
		width: 16px;
		height: 12px;
	}
</style>
