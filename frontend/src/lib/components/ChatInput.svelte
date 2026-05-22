<script lang="ts">
	interface Props { placeholder?: string; onSend?: (text: string) => void }
	let { placeholder = 'Ask your health agent...', onSend }: Props = $props();
	let inputValue = $state('');

	function send() {
		const t = inputValue.trim();
		if (!t) return;
		onSend?.(t);
		inputValue = '';
	}
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') send();
	}
</script>

<div class="input-area">
	<input
		type="text"
		class="chat-input"
		{placeholder}
		bind:value={inputValue}
		onkeydown={onKeydown}
	/>
	<button class="send" aria-label="Send" onclick={send}>
		<svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round"/></svg>
	</button>
</div>

<style>
	.input-area {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 0 6px;
		border-top: 1px solid var(--border);
	}
	.chat-input {
		flex: 1;
		padding: 12px 16px;
		border: 1px solid var(--border);
		border-radius: 24px;
		font-size: 13.5px;
		font-family: inherit;
		background: var(--card);
		color: var(--text-primary);
		outline: none;
		transition: border-color 0.2s;
	}
	.chat-input::placeholder { color: var(--text-tertiary); }
	.chat-input:focus { border-color: var(--green); }
	.send {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: var(--green);
		border: none;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		flex-shrink: 0;
		transition: transform 0.15s;
	}
	.send:active { transform: scale(0.92); }
	.send svg {
		width: 18px;
		height: 18px;
		stroke: white;
		fill: none;
		stroke-width: 2;
	}
</style>
