<script lang="ts">
	import '../app.css';
	import StatusBar from '$lib/components/StatusBar.svelte';
	import BottomNav from '$lib/components/BottomNav.svelte';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
	<title>Vitals — Health Analytics</title>
	<link rel="manifest" href="/manifest.webmanifest" />
</svelte:head>

<StatusBar />
<main>
	{@render children()}
</main>
<BottomNav />

<style>
	main {
		padding-bottom: 90px;
		animation: fadeIn 0.3s ease;
	}
</style>
