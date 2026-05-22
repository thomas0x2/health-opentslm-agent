<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props { hero?: boolean; full?: boolean; children: Snippet }
	let { hero = false, full = false, children }: Props = $props();
</script>

<div class="card" class:card-hero={hero} class:full={full}>
	{@render children()}
</div>

<style>
	.card {
		background: var(--card);
		border-radius: var(--radius-md);
		padding: 16px;
		box-shadow: var(--shadow-sm);
		position: relative;
		overflow: hidden;
	}
	.card-hero {
		background: var(--green);
		color: white;
		padding: 20px;
	}
	.full { grid-column: 1 / -1; }
</style>
