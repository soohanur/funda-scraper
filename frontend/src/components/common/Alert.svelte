<script lang="ts">
  export let message: string = '';
  export let type: 'success' | 'error' | 'warning' | 'info' = 'info';

  const styles = {
    success: 'bg-green-50 border-green-200 text-green-700',
    error: 'bg-red-50 border-red-200 text-red-700',
    warning: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    info: 'bg-blue-50 border-blue-200 text-blue-700',
  };
</script>

{#if message}
  <div class="p-3 border rounded-lg text-sm {styles[type]}">
    {message}
  </div>
{/if}
