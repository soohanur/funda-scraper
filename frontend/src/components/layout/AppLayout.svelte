<script lang="ts">
  import Header from './Header.svelte';
</script>

<div class="min-h-screen bg-gray-50 flex flex-col">
  <Header />
  <main class="flex-1">
    <slot />
  </main>
</div>
