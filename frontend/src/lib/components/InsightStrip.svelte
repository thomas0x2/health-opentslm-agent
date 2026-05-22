<script lang="ts">
	interface Props { icon?: string; html: string }
	let { icon = '◈', html }: Props = $props();
</script>

<div class="insight-strip">
	<div class="insight-icon">{icon}</div>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	<p>{@html html}</p>
</div>

<style>
	.insight-strip {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		padding: 14px 16px;
		background: var(--card-alt);
		border-left: 3px solid var(--green);
		margin: 0 16px 12px;
		border-radius: var(--radius-md);
	}
	.insight-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
	p { font-size: 12.5px; line-height: 1.5; color: var(--text-secondary); }
	p :global(strong) { color: var(--text-primary); }
</style>
