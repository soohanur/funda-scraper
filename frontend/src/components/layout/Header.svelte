<script lang="ts">
  import { authStore } from '../../lib/stores/auth';
  import { push } from 'svelte-spa-router';
  import { config } from '../../lib/config/env';
  import Logo from '../../assets/Logo (3).png';

  $: user = $authStore.user;
  $: console.log('Header - User data:', user);
  $: console.log('Header - Full auth store:', $authStore);

  function handleLogout() {
    authStore.logout();
    push('/');
  }
</script>

<header class="bg-white border-b border-gray-200 sticky top-0 z-50">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
    <div class="flex items-center justify-between">
      <!-- Logo & Title -->
      <a href="/#/home" class="flex items-center space-x-3 hover:opacity-80 transition-opacity cursor-pointer">
        <img src="{Logo}" alt="Nicky Logo" class="h-8 sm:h-12 w-auto" />
      </a>

      <!-- User Section -->
      <div class="flex items-center space-x-2 sm:space-x-4">
        <div class="flex items-center space-x-2 sm:space-x-3">
          <div class="text-right hidden sm:block">
            <p class="text-sm font-medium text-gray-900">
              {user?.username || 'User'}
            </p>
            <p class="text-xs text-gray-500">
              {user?.email || ''}
            </p>
          </div>
          <button
            on:click={handleLogout}
            class="text-gray-600 hover:text-gray-900 transition-colors cursor-pointer p-1"
            title="Logout"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</header>
