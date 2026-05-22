<script lang="ts">
	import { onMount } from 'svelte';
	import { getAgentAdvice, getHealthCoachAgents, type AdviceResponse, type AgentDomain } from '$lib/api';

	let domains = $state<AgentDomain[]>([]);
	let selectedDomain = $state<string | null>(null);
	let expandedDomain = $state<string | null>(null);
	let adviceByDomain = $state<Record<string, string>>({});
	let loadingByDomain = $state<Record<string, boolean>>({});
	let loading = $state(false);
	let statusText = $state('Connecting to local agents');
	let includeOpenTslm = $state(true);

	onMount(async () => {
		try {
			domains = await getHealthCoachAgents();
			selectedDomain = domains.find((d) => d.name === 'sleep')?.name ?? domains[0]?.name ?? null;
			statusText = domains.length ? 'Agents ready' : 'No agents returned';
		} catch (error) {
			statusText = error instanceof Error ? error.message : 'Agent backend unavailable';
		}
	});

	function formatAdvice(res: AdviceResponse) {
		const parts = [res.advice.summary];
		if (res.advice.advice?.length) {
			parts.push(
				...res.advice.advice.slice(0, 3).map((item) =>
					`${item.headline}: ${item.actionable_step}`
				)
			);
		}
		if (res.advice.flags?.length) {
			parts.push(
				...res.advice.flags.slice(0, 3).map((flag) =>
					`${flag.name} (${flag.severity}/${flag.urgency}): ${flag.recommended_action}`
				)
			);
		}
		const caveats = res.advice.caveats?.length ? `\n\nCaveats: ${res.advice.caveats.join(', ')}.` : '';
		return `${parts.filter(Boolean).join('\n\n')}${caveats}`;
	}

	function domainTitle(name: string) {
		return domains.find((d) => d.name === name)?.title ?? name;
	}

	async function runDomain(domain: string, openDetail = false) {
		if (!domain || loadingByDomain[domain]) return;
		loadingByDomain = { ...loadingByDomain, [domain]: true };
		statusText = `Running ${domainTitle(domain)}`;
		if (openDetail) selectedDomain = domain;
		try {
			const response = await getAgentAdvice(domain, { tone: 'coach', includeOpenTslm });
			const text = formatAdvice(response);
			adviceByDomain = { ...adviceByDomain, [domain]: text };
			statusText = `${domainTitle(domain)} complete`;
		} catch (error) {
			const text = error instanceof Error ? error.message : 'Agent request failed';
			adviceByDomain = { ...adviceByDomain, [domain]: text };
			statusText = text;
		} finally {
			loadingByDomain = { ...loadingByDomain, [domain]: false };
		}
	}

	async function runAllAdvice() {
		if (loading || domains.length === 0) return;
		loading = true;
		for (const domain of domains) {
			await runDomain(domain.name);
		}
		loading = false;
		statusText = 'All agent advice complete';
	}

	function runSelectedDetail() {
		if (!selectedDomain) return;
		void runDomain(selectedDomain, true);
	}

	function expandDomain(domain: string) {
		selectedDomain = domain;
		expandedDomain = domain;
	}

	function runExpandedDomain() {
		if (!expandedDomain) return;
		void runDomain(expandedDomain, true);
	}
</script>

<div class="agent-header">
	<div class="header-date">Health Agent</div>
	<h1 class="header-title">Health Coach</h1>
	<div class="agent-status">
		<div class="status-dot" class:loading></div>
		<span class="status-text">{statusText}</span>
	</div>
</div>

<section class="toolbar">
	<label class="toggle">
		<input type="checkbox" bind:checked={includeOpenTslm} disabled={loading} />
		<span>OpenTSLM</span>
	</label>
	<button class="run-all" onclick={runAllAdvice} disabled={loading || domains.length === 0}>
		{loading ? 'Running agents...' : 'Run all advice'}
	</button>
</section>

<section class="agent-grid" aria-label="Health agents">
	{#each domains as domain (domain.name)}
		<div
			class="agent-card"
			class:selected={selectedDomain === domain.name}
			onclick={() => (selectedDomain = domain.name)}
			onkeydown={(event) => {
				if (event.key === 'Enter' || event.key === ' ') selectedDomain = domain.name;
			}}
			role="button"
			tabindex="0"
		>
			<div class="card-top">
				<div>
					<div class="agent-name">{domain.title}</div>
					<div class="agent-kind">{domain.name}</div>
				</div>
				<span class="card-state">{loadingByDomain[domain.name] ? 'Running' : adviceByDomain[domain.name] ? 'Ready' : 'Idle'}</span>
			</div>
			<p class="agent-description">{domain.description}</p>
			<div class="advice-preview">
				{#if adviceByDomain[domain.name]}
					{adviceByDomain[domain.name]}
				{:else}
					No advice generated yet.
				{/if}
			</div>
			<div class="card-actions">
				<button
					class="more-options"
					onclick={(event) => {
						event.stopPropagation();
						expandDomain(domain.name);
					}}
				>
					More options
				</button>
				<button
					class="run-one"
					onclick={(event) => {
						event.stopPropagation();
						void runDomain(domain.name, true);
					}}
					disabled={loadingByDomain[domain.name]}
				>
					{loadingByDomain[domain.name] ? 'Running...' : 'Run'}
				</button>
			</div>
		</div>
	{/each}
</section>

{#if selectedDomain}
	<section class="detail-panel">
		<div class="detail-header">
			<div>
				<div class="detail-eyebrow">Selected agent</div>
				<h2>{domainTitle(selectedDomain)}</h2>
			</div>
			<button class="run-detail" onclick={runSelectedDetail} disabled={loadingByDomain[selectedDomain]}>
				{loadingByDomain[selectedDomain] ? 'Running...' : 'Run advice'}
			</button>
		</div>

		<div class="detail-advice">
			{#if adviceByDomain[selectedDomain]}
				{adviceByDomain[selectedDomain]}
			{:else}
				Run this agent to generate advice. Follow-up chat appears here after the first run.
			{/if}
		</div>

	</section>
{/if}

{#if expandedDomain}
	<div class="agent-modal" role="dialog" aria-modal="true">
		<div class="modal-top">
			<div>
				<div class="detail-eyebrow">Expanded agent</div>
				<h2>{domainTitle(expandedDomain)}</h2>
			</div>
			<button class="close-modal" onclick={() => (expandedDomain = null)} aria-label="Close">Close</button>
		</div>
		<div class="modal-body">
			<div class="modal-advice">
				{#if adviceByDomain[expandedDomain]}
					{adviceByDomain[expandedDomain]}
				{:else}
					Run this agent to generate full-screen advice.
				{/if}
			</div>
			<button class="run-detail modal-run" onclick={runExpandedDomain} disabled={loadingByDomain[expandedDomain]}>
				{loadingByDomain[expandedDomain] ? 'Running...' : 'Run advice'}
			</button>
		</div>
	</div>
{/if}

<style>
	.agent-header { padding: 6px 24px 14px; }
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
	.status-dot.loading { background: var(--terracotta); }
	.status-text { font-size: 12px; color: var(--text-secondary); }
	.toolbar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 16px 12px;
	}
	.toggle {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 12px;
		color: var(--text-secondary);
	}
	.toggle input { accent-color: var(--green); }
	.run-all,
	.run-detail,
	.run-one,
	.more-options,
	.close-modal {
		border: none;
		border-radius: 8px;
		background: var(--green);
		color: white;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
	}
	.run-all {
		flex: 1;
		min-height: 38px;
	}
	button:disabled {
		opacity: 0.65;
		cursor: wait;
	}
	.agent-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
		gap: 12px;
		padding: 0 16px 14px;
	}
	.agent-card {
		text-align: left;
		border: 1px solid color-mix(in srgb, var(--green) 38%, var(--border));
		border-radius: 8px;
		background: var(--card);
		padding: 14px;
		box-shadow: var(--shadow-sm);
		color: inherit;
		font: inherit;
		cursor: pointer;
	}
	.agent-card.selected {
		border-color: var(--green);
		box-shadow: 0 0 0 2px color-mix(in srgb, var(--green) 16%, transparent);
	}
	.card-top,
	.card-actions,
	.detail-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
	}
	.agent-name {
		font-size: 15px;
		font-weight: 650;
		color: var(--text-primary);
	}
	.agent-kind,
	.detail-eyebrow {
		margin-top: 2px;
		font-size: 10.5px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-tertiary);
	}
	.card-state {
		font-size: 11px;
		color: var(--green);
	}
	.agent-description {
		min-height: 38px;
		margin: 10px 0;
		font-size: 12.5px;
		line-height: 1.45;
		color: var(--text-secondary);
	}
	.advice-preview,
	.detail-advice {
		white-space: pre-line;
		font-size: 13px;
		line-height: 1.5;
		color: var(--text-primary);
	}
	.advice-preview {
		max-height: 140px;
		min-height: 72px;
		overflow: hidden;
		color: var(--text-secondary);
	}
	.card-actions {
		margin-top: 12px;
		font-size: 12px;
		color: var(--text-tertiary);
	}
	.more-options {
		min-height: 32px;
		padding: 0 10px;
		background: color-mix(in srgb, var(--green) 18%, var(--card));
		color: var(--green);
	}
	.run-one {
		min-width: 74px;
		min-height: 32px;
		background: var(--green);
	}
	.detail-panel {
		margin: 0 16px 20px;
		padding: 14px;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--card);
		box-shadow: var(--shadow-sm);
	}
	.detail-header h2 {
		margin: 2px 0 0;
		font-size: 18px;
		color: var(--text-primary);
	}
	.run-detail {
		min-height: 36px;
		padding: 0 12px;
	}
	.detail-advice {
		margin-top: 14px;
		padding-top: 12px;
		border-top: 1px solid var(--border);
	}
	.agent-modal {
		position: fixed;
		inset: 0;
		z-index: 20;
		padding: 24px;
		background: var(--background);
		overflow-y: auto;
	}
	.modal-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}
	.modal-top h2 {
		margin: 2px 0 0;
		font-family: 'Instrument Serif', serif;
		font-size: 34px;
		color: var(--text-primary);
	}
	.close-modal {
		min-height: 36px;
		padding: 0 12px;
		background: var(--text-primary);
	}
	.modal-body {
		margin-top: 20px;
		border: 1px solid color-mix(in srgb, var(--green) 36%, var(--border));
		border-radius: 8px;
		background: var(--card);
		padding: 18px;
		box-shadow: var(--shadow-sm);
	}
	.modal-advice {
		white-space: pre-line;
		font-size: 15px;
		line-height: 1.65;
		color: var(--text-primary);
	}
	.modal-run {
		margin-top: 18px;
		width: 100%;
	}
</style>
