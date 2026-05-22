<script lang="ts">
	import AppHeader from '$lib/components/AppHeader.svelte';
	import SavedWidgetCard from '$lib/components/SavedWidgetCard.svelte';
	import { builderSuggestions } from '$lib/data/vitals';
	import { sendAgentMessage } from '$lib/api';
	import { loadWidgets, addWidget, removeWidget } from '$lib/storage';
	import { executeWidget } from '$lib/widgets/execute';
	import { CHART_REGISTRY, type Widget } from '$lib/widgets';
	import { getHealthRaw } from '$lib/api';

	let builderInput = $state('');
	let generating = $state(false);
	let messages = $state<{ role: 'user' | 'agent'; text: string; widget?: Widget }[]>([]);
	let pendingWidget = $state<Widget | null>(null);
	let savedWidgets = $state<Widget[]>(loadWidgets());
	let dashboardRecords = $state<any[]>([]);
	let addMsg = $state('');

	// Preload raw data for widget previews
	getHealthRaw().then(r => dashboardRecords = r.records).catch(() => {});

	async function send() {
		const t = builderInput.trim();
		if (!t || generating) return;
		messages = [...messages, { role: 'user' as const, text: t }];
		builderInput = '';
		generating = true;
		try {
			const res = await sendAgentMessage(t);
			messages = [...messages, { role: 'agent' as const, text: res.reply, widget: res.widget as Widget }];
			if (res.widget) pendingWidget = res.widget as Widget;
		} catch (e: any) {
			messages = [...messages, { role: 'agent' as const, text: `Error: ${e.message || 'Unknown error'}` }];
		} finally {
			generating = false;
		}
	}

	function handleAddToDashboard() {
		if (!pendingWidget) return;
		addWidget(pendingWidget);
		savedWidgets = loadWidgets();
		addMsg = `"${pendingWidget.title}" added to dashboard`;
		pendingWidget = null;
		setTimeout(() => addMsg = '', 3000);
	}

	function handleDiscard() {
		pendingWidget = null;
	}

	function handleDelete(id: string) {
		removeWidget(id);
		savedWidgets = loadWidgets();
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function useChip(text: string) {
		builderInput = text;
	}
</script>

<AppHeader date="Widget Builder" title="Build" titleSize="30px" subtitle="Describe a chart or metric in plain English." />

<div class="page-container">
	<!-- Saved widgets -->
	<div class="saved-section">
		<div class="saved-header">
			<span class="saved-title">Your Custom Widgets</span>
			<span class="saved-count">{savedWidgets.length}</span>
		</div>
		{#if savedWidgets.length === 0}
			<div class="empty-hint">No widgets yet. Describe one below ↓</div>
		{:else}
			<div class="saved-grid">
				{#each savedWidgets as widget (widget.id)}
					<div class="saved-item">
						<SavedWidgetCard {widget} />
						<button class="delete-btn" onclick={() => handleDelete(widget.id)} title="Remove">
							<svg viewBox="0 0 12 12" width="10" height="10"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Builder chat card -->
	<div class="builder-card">
		<div class="builder-header">
			<div class="pulse-dot" class:active={generating}></div>
			<span class="builder-title">{generating ? 'Thinking...' : 'New Widget'}</span>
		</div>

		<!-- Conversation -->
		<div class="conversation">
			{#if messages.length === 0}
				<div class="empty-chat">Ask me to create a chart — like "Show my HRV trend over the week"</div>
			{/if}
			{#each messages as msg, i (i)}
				<div class="msg" class:user-msg={msg.role === 'user'} class:agent-msg={msg.role === 'agent'}>
					<span class="msg-label">{msg.role === 'user' ? 'You' : 'Builder'}</span>
					{msg.text}
				</div>
			{/each}
			{#if generating}
				<div class="msg agent-msg generating-msg">
					<span class="msg-label">Builder</span>
					<span class="dots"><i>.</i><i>.</i><i>.</i></span>
				</div>
			{/if}
		</div>

		<!-- Widget Preview -->
		{#if pendingWidget}
			<div class="preview">
				<div class="preview-badge">Preview</div>
				<div class="preview-chart-area">
					{#if dashboardRecords.length > 0}
						{#if CHART_REGISTRY[pendingWidget.vizType]}
							{@const Comp = CHART_REGISTRY[pendingWidget.vizType]}
							<Comp widget={pendingWidget} records={dashboardRecords} />
						{:else}
							<div class="preview-fallback">{pendingWidget.title} — {pendingWidget.vizType}</div>
						{/if}
					{:else}
						<div class="preview-loading">Loading data for preview...</div>
					{/if}
				</div>
				<div class="preview-actions">
					<button class="btn btn-primary" onclick={handleAddToDashboard}>Add to Dashboard</button>
					<button class="btn btn-secondary" onclick={handleDiscard}>Discard</button>
				</div>
			</div>
		{/if}

		{#if addMsg}
			<div class="add-confirm">{addMsg}</div>
		{/if}

		<!-- Suggestion chips -->
		<div class="chips">
			{#each builderSuggestions as s (s)}
				<button class="chip" onclick={() => useChip(s)}>{s}</button>
			{/each}
		</div>

		<!-- Input -->
		<div class="input-area">
			<input
				type="text"
				class="builder-input"
				placeholder={generating ? 'Waiting for response...' : 'Describe a widget...'}
				bind:value={builderInput}
				onkeydown={onKeydown}
				disabled={generating}
			/>
			<button class="send-btn" aria-label="Send" onclick={send} disabled={generating}>
				<svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round"/></svg>
			</button>
		</div>
	</div>
</div>

<style>
	.page-container { padding-bottom: 20px; }

	.saved-section { padding: 0 16px 16px; }
	.saved-header {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 10px;
	}
	.saved-title {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-tertiary);
		font-weight: 600;
	}
	.saved-count {
		font-size: 10px;
		font-weight: 700;
		color: var(--text-tertiary);
		background: var(--bg-warm);
		width: 18px;
		height: 18px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.empty-hint {
		font-size: 12px;
		color: var(--text-tertiary);
		padding: 8px 0;
	}
	.saved-grid { display: flex; flex-direction: column; gap: 6px; }
	.saved-item { position: relative; }
	.delete-btn {
		position: absolute;
		top: 8px;
		right: 8px;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		border: none;
		background: var(--bg);
		color: var(--text-tertiary);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0;
		transition: opacity 0.2s;
	}
	.saved-item:hover .delete-btn { opacity: 1; }

	.builder-card {
		background: var(--card);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-md);
		overflow: hidden;
		border: 1px solid var(--border);
		margin: 0 16px;
	}
	.builder-header {
		padding: 16px 18px 12px;
		border-bottom: 1px solid var(--bg);
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.pulse-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--text-primary);
		animation: pulse 2s ease-in-out infinite;
	}
	.pulse-dot.active {
		background: var(--green);
		animation: pulse 0.8s ease-in-out infinite;
	}
	.builder-title {
		font-family: 'Instrument Serif', serif;
		font-size: 20px;
		letter-spacing: -0.01em;
		color: var(--text-primary);
	}

	.conversation {
		padding: 14px 18px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		max-height: 260px;
		overflow-y: auto;
	}
	.empty-chat {
		font-size: 12px;
		color: var(--text-tertiary);
		text-align: center;
		padding: 20px 0;
	}
	.msg {
		font-size: 13px;
		line-height: 1.5;
		padding: 10px 14px;
		max-width: 88%;
	}
	.msg .msg-label {
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		font-weight: 700;
		margin-bottom: 3px;
		display: block;
	}
	.user-msg {
		align-self: flex-end;
		background: var(--text-primary);
		color: white;
		border-radius: var(--radius-sm) 3px var(--radius-sm) var(--radius-sm);
	}
	.user-msg .msg-label { color: rgba(255,255,255,0.45); }
	.agent-msg {
		align-self: flex-start;
		background: var(--bg);
		color: var(--text-primary);
		border-radius: 3px var(--radius-sm) var(--radius-sm) var(--radius-sm);
	}
	.agent-msg .msg-label { color: var(--text-tertiary); }

	.preview {
		margin: 0 18px 14px;
		background: var(--card-alt);
		border: 1px dashed var(--border);
		border-radius: var(--radius-md);
		padding: 14px;
		position: relative;
	}
	.preview-badge {
		position: absolute;
		top: 8px;
		right: 10px;
		font-size: 8.5px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		font-weight: 700;
		color: var(--green);
		background: var(--green-light);
		padding: 2px 7px;
		border-radius: 4px;
	}
	.preview-chart-area {
		min-height: 80px;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.preview-fallback {
		font-size: 12px;
		color: var(--text-secondary);
		padding: 16px;
		text-align: center;
	}
	.preview-loading {
		font-size: 11px;
		color: var(--text-tertiary);
		padding: 16px;
	}
	.preview-actions {
		display: flex;
		gap: 8px;
		margin-top: 10px;
	}
	.btn {
		flex: 1;
		padding: 10px;
		border-radius: var(--radius-sm);
		font-size: 12.5px;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		transition: all 0.15s;
		border: none;
	}
	.btn-primary { background: var(--green); color: white; }
	.btn-primary:active { transform: scale(0.97); }
	.btn-secondary { background: var(--bg); color: var(--text-secondary); border: 1px solid var(--border); }

	.add-confirm {
		margin: 0 18px 10px;
		padding: 8px 12px;
		background: var(--green-light);
		color: var(--green);
		border-radius: 8px;
		font-size: 12px;
		font-weight: 600;
		text-align: center;
	}

	.chips {
		display: flex;
		gap: 5px;
		flex-wrap: wrap;
		padding: 0 18px 12px;
	}
	.chip {
		padding: 6px 11px;
		border: 1px solid var(--border);
		border-radius: 16px;
		font-size: 11px;
		color: var(--text-secondary);
		background: var(--card);
		cursor: pointer;
		font-family: inherit;
		transition: all 0.2s;
		white-space: nowrap;
	}
	.chip:hover, .chip:active { border-color: var(--text-primary); color: var(--text-primary); }

	.input-area {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 18px 14px;
		border-top: 1px solid var(--bg);
	}
	.builder-input {
		flex: 1;
		padding: 11px 14px;
		border: 1px solid var(--border);
		border-radius: 22px;
		font-size: 13px;
		font-family: inherit;
		background: var(--bg);
		color: var(--text-primary);
		outline: none;
		transition: border-color 0.2s;
	}
	.builder-input::placeholder { color: var(--text-tertiary); }
	.builder-input:focus { border-color: var(--text-primary); background: var(--card); }
	.send-btn {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		background: var(--text-primary);
		border: none;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		flex-shrink: 0;
		transition: transform 0.15s;
	}
	.send-btn:active { transform: scale(0.9); }
	.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.send-btn svg {
		width: 15px;
		height: 15px;
		stroke: white;
		fill: none;
		stroke-width: 2.2;
	}

	.generating-msg { opacity: 0.6; }
	.dots i {
		display: inline-block;
		font-style: normal;
		animation: dotPulse 1.2s ease-in-out infinite;
	}
	.dots i:nth-child(2) { animation-delay: 0.2s; }
	.dots i:nth-child(3) { animation-delay: 0.4s; }
	@keyframes dotPulse {
		0%, 40% { opacity: 0.2; }
		60%, 100% { opacity: 1; }
	}
</style>
