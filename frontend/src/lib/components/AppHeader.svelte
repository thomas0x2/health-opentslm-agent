<script lang="ts">
	interface Props {
		date?: string;
		title: string;
		subtitle?: string;
		avatarInitial?: string;
		titleSize?: string;
	}
	let { date, title, subtitle, avatarInitial, titleSize = '34px' }: Props = $props();
</script>

<div class="header">
	<div class="top">
		<div>
			{#if date}<div class="date">{date}</div>{/if}
			<h1 class="title" style="font-size: {titleSize}">{title}</h1>
			{#if subtitle}<div class="subtitle">{subtitle}</div>{/if}
		</div>
		{#if avatarInitial}
			<div class="avatar">{avatarInitial}</div>
		{/if}
	</div>
</div>

<style>
	.header { padding: 6px 24px 20px; }
	.top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 4px;
	}
	.date {
		font-size: 12px;
		color: var(--text-tertiary);
		letter-spacing: 0.08em;
		text-transform: uppercase;
		font-weight: 500;
		margin-bottom: 2px;
	}
	.title {
		font-family: 'Instrument Serif', serif;
		line-height: 1.05;
		letter-spacing: -0.02em;
		color: var(--text-primary);
	}
	.subtitle {
		font-size: 13px;
		color: var(--text-secondary);
		margin-top: 4px;
		line-height: 1.4;
	}
	.avatar {
		width: 38px;
		height: 38px;
		border-radius: 50%;
		background: var(--green);
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		font-size: 14px;
		font-weight: 600;
		margin-top: 4px;
		flex-shrink: 0;
	}
</style>
