<script lang="ts">
	interface Props { role: 'agent' | 'user'; text: string }
	let { role, text }: Props = $props();
</script>

<div class="bubble" class:agent={role === 'agent'} class:user={role === 'user'}>
	<span class="label">{role === 'agent' ? 'Agent' : 'You'}</span>
	{text}
</div>

<style>
	.bubble {
		max-width: 82%;
		padding: 12px 16px;
		font-size: 13.5px;
		line-height: 1.55;
		color: var(--text-primary);
	}
	.bubble.agent {
		background: var(--card);
		border-radius: 2px var(--radius-md) var(--radius-md) var(--radius-md);
		box-shadow: var(--shadow-sm);
		align-self: flex-start;
	}
	.bubble.user {
		background: var(--green);
		color: white;
		border-radius: var(--radius-md) 2px var(--radius-md) var(--radius-md);
		align-self: flex-end;
	}
	.label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		font-weight: 600;
		margin-bottom: 4px;
		display: block;
	}
	.agent .label { color: var(--green); }
	.user .label  { color: rgba(255,255,255,0.6); }
</style>
