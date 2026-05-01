<script lang="ts">
  export let onClick: () => void = () => {};
  export let type: 'button' | 'submit' | 'reset' = 'button';
  export let disabled: boolean = false;
  export let variant: 'primary' | 'secondary' | 'danger' = 'primary';
  export let size: 'sm' | 'md' | 'lg' = 'md';
  export let fullWidth: boolean = false;
  export let loading: boolean = false;

  const variantClasses = {
    primary: 'bg-primary-600 hover:bg-primary-700 text-white',
    secondary: 'bg-gray-200 hover:bg-gray-300 text-gray-800',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
  };

  const sizeClasses = {
    sm: 'py-2 px-3 text-sm',
    md: 'py-2.5 px-4 text-base',
    lg: 'py-3 px-6 text-lg',
  };
</script>

<button
  {type}
  {disabled}
  on:click={onClick}
  class="font-medium rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer {variantClasses[variant]} {sizeClasses[size]} {fullWidth ? 'w-full' : ''}"
>
  {#if loading}
    <svg class="animate-spin h-5 w-5 mx-auto" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  {:else}
    <slot />
  {/if}
</button>
