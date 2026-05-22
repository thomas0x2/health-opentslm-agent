<script lang="ts">
	interface Props { label: string }
	let { label }: Props = $props();
</script>

<div class="section-label">{label}</div>

<style>
	.section-label {
		grid-column: 1 / -1;
		padding: 14px 6px 2px;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--text-tertiary);
		font-weight: 600;
		border-top: 1px solid var(--border);
		margin-top: 4px;
	}
</style>
