<script lang="ts">
  import { push } from 'svelte-spa-router';
  import { authAPI } from '../../lib/api/auth';
  import { authStore } from '../../lib/stores/auth';
  import Input from '../../components/common/Input.svelte';
  import Button from '../../components/common/Button.svelte';
  import Alert from '../../components/common/Alert.svelte';
  import { config } from '../../lib/config/env';
  import Logo from '../../assets/Logo (3).png';

  let email = '';
  let username = '';
  let password = '';
  let confirmPassword = '';
  let adminKey = '';
  let showPassword = false;
  let showConfirmPassword = false;
  let error = '';
  let loading = false;

  async function handleSubmit() {
    // Validation
    if (!email || !username || !password || !confirmPassword || !adminKey) {
      error = 'Please fill in all fields';
      return;
    }

    if (password !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }

    if (password.length < 8) {
      error = 'Password must be at least 8 characters';
      return;
    }

    loading = true;
    error = '';

    try {
      await authAPI.register({ username, email, password, admin_key: adminKey });
      // Redirect to login page after successful registration
      push('/');
    } catch (err: any) {
      error = err.response?.data?.detail || 'Registration failed. Please check your admin key and try again.';
      loading = false;
    }
  }

  function handleKeyPress(e: KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit();
  }
</script>

<div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 px-4 py-8">
  <div class="w-full max-w-md">
    <div class="bg-white rounded-2xl shadow-lg p-8">
      <!-- Logo -->
      <div class="flex justify-center mb-6">
        <img src="{Logo}" alt="Nicky Logo" class="h-16 w-auto" />
      </div>

      <!-- Title -->
      <h1 class="text-2xl font-bold text-center text-gray-900 mb-2">Create Account</h1>
      <p class="text-center text-gray-600 text-sm mb-6">Register with admin authorization</p>

      <!-- Error -->
      {#if error}
        <div class="mb-4">
          <Alert message={error} type="error" />
        </div>
      {/if}

      <!-- Form -->
      <form on:submit|preventDefault={handleSubmit} class="space-y-4">
        <Input
          id="email"
          label="Email"
          type="email"
          placeholder="your@email.com"
          bind:value={email}
          disabled={loading}
          required
          on:keypress={handleKeyPress}
        />

        <Input
          id="username"
          label="Username"
          type="text"
          placeholder="johndoe"
          bind:value={username}
          disabled={loading}
          required
          on:keypress={handleKeyPress}
        />

        <div>
          <label for="password" class="block text-sm font-medium text-gray-700 mb-2">
            Password <span class="text-red-500">*</span>
          </label>
          <div class="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              bind:value={password}
              disabled={loading}
              on:keypress={handleKeyPress}
              class="input-field pr-10"
            />
            <button
              type="button"
              on:click={() => (showPassword = !showPassword)}
              class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {#if showPassword}
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                {:else}
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"></path>
                {/if}
              </svg>
            </button>
          </div>
        </div>

        <div>
          <label for="confirmPassword" class="block text-sm font-medium text-gray-700 mb-2">
            Confirm Password <span class="text-red-500">*</span>
          </label>
          <div class="relative">
            <input
              id="confirmPassword"
              type={showConfirmPassword ? 'text' : 'password'}
              placeholder="••••••••"
              bind:value={confirmPassword}
              disabled={loading}
              on:keypress={handleKeyPress}
              class="input-field pr-10"
            />
            <button
              type="button"
              on:click={() => (showConfirmPassword = !showConfirmPassword)}
              class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {#if showConfirmPassword}
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                {:else}
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"></path>
                {/if}
              </svg>
            </button>
          </div>
        </div>

        <Input
          id="adminKey"
          label={config.ADMIN_SECRET_KEY_LABEL}
          type="password"
          placeholder="Enter admin authorization key"
          bind:value={adminKey}
          disabled={loading}
          required
          on:keypress={handleKeyPress}
        />
        <p class="text-xs text-gray-500 -mt-2">Required for registration. Contact your administrator.</p>

        <Button type="submit" fullWidth={true} loading={loading} disabled={loading}>
          {loading ? 'Creating account...' : 'Create Account'}
        </Button>
      </form>

      <p class="text-center text-gray-500 text-xs mt-6">
        Admin-managed accounts only. Contact your administrator for access.
      </p>

      <div class="text-center mt-4">
        <span class="text-gray-600 text-sm">Already have an account? </span>
        <a href="/#/" class="text-primary-600 hover:text-primary-700 font-medium text-sm cursor-pointer">
          Sign in
        </a>
      </div>
    </div>
  </div>
</div>
