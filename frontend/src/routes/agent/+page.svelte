<script lang="ts">
	import ChatBubble from '$lib/components/ChatBubble.svelte';
	import ChatInput from '$lib/components/ChatInput.svelte';
	import { agentMessages, agentSuggestions } from '$lib/data/vitals';

	let messages = $state([...agentMessages]);

	function handleSend(text: string) {
		messages = [...messages, { role: 'user' as const, text }];
	}

	function useSuggestion(text: string) {
		messages = [...messages, { role: 'user' as const, text }];
	}
</script>

<div class="agent-header">
	<div class="header-date">Health Agent</div>
	<h1 class="header-title">Vitals Coach</h1>
	<div class="agent-status">
		<div class="status-dot"></div>
		<span class="status-text">Analyzing your latest data</span>
	</div>
</div>

<div class="chat-container">
	<div class="chat-messages">
		{#each messages as msg, i (i)}
			<ChatBubble role={msg.role} text={msg.text} />
		{/each}
	</div>

	<div class="suggestions">
		{#each agentSuggestions as s (s)}
			<button class="suggestion" onclick={() => useSuggestion(s)}>{s}</button>
		{/each}
	</div>

	<ChatInput onSend={handleSend} />
</div>

<style>
	.agent-header { padding: 6px 24px 16px; }
	.header-date {
		font-size: 12px;
		color: var(--text-tertiary);
		letter-spacing: 0.08em;
		text-transform: uppercase;
		font-weight: 500;
	}
	.header-title {
		font-family: 'Instrument Serif', serif;
		font-size: 30px;
		line-height: 1.05;
		letter-spacing: -0.02em;
		color: var(--text-primary);
	}
	.agent-status {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 8px;
	}
	.status-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--green);
		animation: pulse 2s ease-in-out infinite;
	}
	.status-text { font-size: 12px; color: var(--text-secondary); }

	.chat-container {
		display: flex;
		flex-direction: column;
		height: calc(100vh - 200px);
		padding: 0 16px;
	}
	.chat-messages {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 10px 0 16px;
	}
	.suggestions {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		padding: 4px 0 10px;
	}
	.suggestion {
		padding: 8px 14px;
		border: 1px solid var(--border);
		border-radius: 20px;
		font-size: 12px;
		color: var(--text-secondary);
		background: var(--card);
		cursor: pointer;
		transition: all 0.2s;
		font-family: inherit;
	}
	.suggestion:hover { border-color: var(--green); color: var(--green); }
</style>
