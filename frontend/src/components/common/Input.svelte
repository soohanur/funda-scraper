<script lang="ts">
  export let value: string = '';
  export let type: string = 'text';
  export let placeholder: string = '';
  export let disabled: boolean = false;
  export let label: string = '';
  export let error: string = '';
  export let id: string = '';
  export let required: boolean = false;
</script>

<div class="w-full">
  {#if label}
    <label for={id} class="block text-sm font-medium text-gray-700 mb-2">
      {label}
      {#if required}<span class="text-red-500">*</span>{/if}
    </label>
  {/if}
  
  <input
    {id}
    {type}
    {placeholder}
    {disabled}
    bind:value
    class="input-field {error ? 'border-red-500 focus:ring-red-500' : ''}"
    on:input
    on:blur
    on:keypress
  />
  
  {#if error}
    <p class="mt-1 text-sm text-red-600">{error}</p>
  {/if}
</div>
