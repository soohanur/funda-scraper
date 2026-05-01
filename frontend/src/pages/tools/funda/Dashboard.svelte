<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { fundaAPI, type ScraperStatus, type PublicationDateOption } from '../../../lib/api';

  // ── State ─────────────────────────────────────────────────────
  let status: ScraperStatus = {
    status: 'IDLE',
    total_kvk_stored: 0,
    kvk_collected_this_session: 0,
    current_batch: 0,
    properties_scraped: 0,
    properties_filtered: 0,
    properties_failed: 0,
    current_page: 0,
    total_pages_scraped: 0,
    batch_progress: 0,
    total_search_results: 0,
    collection_status: '',
    collection_page: 0,
    ids_collected: 0,
    ids_queued: 0,
    duplicate_in_storage: 0,
    duplicate_in_retry_queue: 0,
    active_workers: 0,
    excel_files_created: 0,
    sheets_written: 0,
    valuations_written: 0,
    valuations_failed: 0,
    valuations_pending: 0,
    valuations_fallback: 0,
    elapsed_seconds: 0,
    last_error: '',
    browser_restarts: 0,
    consecutive_failures: 0,
  };

  let publicationDateOptions: PublicationDateOption[] = [
    { value: 5, label: '3-7 Days Ago' },
    { value: 10, label: '8-12 Days Ago' },
    { value: 15, label: '13-17 Days Ago' },
    { value: 30, label: '25-30 Days Ago' },
    { value: 31, label: '30+ Days Ago' },
  ];
  let selectedPublicationDate = 5;
  
  let error = '';
  let loading = false;
  let showClearConfirm = false;
  let pollInterval: any = null;
  let sheetsUrl = '';

  // ── Computed ──────────────────────────────────────────────────
  $: isRunning = status.status === 'RUNNING';
  $: isPaused = status.status === 'PAUSED';
  $: isStopping = status.status === 'STOPPING';
  $: isIdle = status.status === 'IDLE' || status.status === 'COMPLETED' || status.status === 'FAILED';
  $: canStart = isIdle && !loading;
  $: canStop = (isRunning || isPaused) && !loading;
  $: canPause = isRunning && !loading;
  $: canResume = isPaused && !loading;
  $: elapsedFormatted = formatDuration(status.elapsed_seconds);
  $: totalProcessed = status.properties_scraped + status.properties_filtered + status.properties_failed;

  // ── Lifecycle ─────────────────────────────────────────────────
  onMount(async () => {
    await loadStatus();
    await loadOptions();
    await loadSheetsUrl();
    startPolling();
  });

  onDestroy(() => {
    stopPolling();
  });

  // ── Functions ─────────────────────────────────────────────────
  function startPolling() {
    stopPolling();
    pollInterval = setInterval(loadStatus, 2000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  async function loadStatus() {
    try {
      status = await fundaAPI.getStatus();
      // Clear error on successful status fetch
      if (status.status !== 'FAILED') {
        error = '';
      }
    } catch (e: any) {
      console.error('Failed to load status:', e);
    }
  }

  async function loadOptions() {
    try {
      const options = await fundaAPI.getPublicationDateOptions();
      publicationDateOptions = options.options;
      selectedPublicationDate = options.default;
    } catch (e: any) {
      console.error('Failed to load options:', e);
    }
  }

  async function loadSheetsUrl() {
    try {
      const data = await fundaAPI.getSheetsUrl();
      sheetsUrl = data.url;
    } catch (e: any) {
      console.error('Failed to load sheets URL:', e);
    }
  }

  async function handleStart() {
    loading = true;
    error = '';
    try {
      await fundaAPI.startScraper(selectedPublicationDate);
      await loadStatus();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to start scraper';
    } finally {
      loading = false;
    }
  }

  async function handleStop() {
    loading = true;
    error = '';
    try {
      await fundaAPI.stopScraper();
      await loadStatus();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to stop scraper';
    } finally {
      loading = false;
    }
  }

  async function handlePause() {
    loading = true;
    error = '';
    try {
      await fundaAPI.pauseScraper();
      await loadStatus();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to pause scraper';
    } finally {
      loading = false;
    }
  }

  async function handleResume() {
    loading = true;
    error = '';
    try {
      await fundaAPI.resumeScraper();
      await loadStatus();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to resume scraper';
    } finally {
      loading = false;
    }
  }

  async function handleClearStorage() {
    loading = true;
    try {
      await fundaAPI.clearKvkStorage();
      await loadStatus();
      showClearConfirm = false;
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to clear storage';
    } finally {
      loading = false;
    }
  }

  function handleBack() {
    push('/home');
  }

  function formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins}m ${secs}s`;
    }
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  }

  function getStatusColor(s: string): string {
    switch (s) {
      case 'RUNNING': return 'bg-green-100 text-green-800';
      case 'PAUSED': return 'bg-yellow-100 text-yellow-800';
      case 'STOPPING': return 'bg-orange-100 text-orange-800';
      case 'COMPLETED': return 'bg-blue-100 text-blue-800';
      case 'FAILED': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  }
</script>

<div class="min-h-screen flex flex-col lg:flex-row" style="background-color: #F2EFE7;">
  <!-- Sidebar (top bar on mobile) -->
  <div class="w-full lg:w-64 bg-white flex flex-col lg:min-h-screen shadow-sm">
    <!-- Back Button + Logo Row (horizontal on mobile) -->
    <div class="flex items-center justify-between lg:flex-col lg:items-stretch">
      <button
        on:click={handleBack}
        class="flex items-center gap-2 px-4 py-3 lg:px-6 lg:py-4 text-sm text-gray-600 hover:text-gray-900 border-b border-gray-200 cursor-pointer"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
        </svg>
        <span>Back to Tools</span>
      </button>

      <!-- Logo Section -->
      <div class="px-4 py-3 lg:px-6 lg:py-6 lg:border-b border-gray-200">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 lg:w-12 lg:h-12 bg-blue-600 rounded-xl flex items-center justify-center">
            <svg class="w-5 h-5 lg:w-6 lg:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path>
            </svg>
          </div>
          <div>
            <h2 class="text-base lg:text-lg font-semibold text-gray-900">Funda Scraper</h2>
            <p class="text-xs text-gray-500 hidden lg:block">v1.0</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Storage Info -->
    <div class="hidden lg:block flex-1 px-4 py-6">
      <div class="bg-gray-50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-gray-700 mb-2">Storage</h3>
        <p class="text-2xl font-bold text-gray-900">{status.total_kvk_stored.toLocaleString()}</p>
        <p class="text-xs text-gray-500">Properties in permanent storage</p>
        {#if status.total_kvk_stored > 0}
          <button
            on:click={() => showClearConfirm = true}
            class="mt-2 text-xs text-red-600 hover:text-red-800 cursor-pointer"
          >
            Clear storage
          </button>
        {/if}
      </div>
    </div>
  </div>

  <!-- Main Content -->
  <div class="flex-1 p-4 sm:p-6 lg:p-8">
    <!-- Error Alert -->
    {#if error}
      <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span class="text-sm text-red-800">{error}</span>
        </div>
        <button on:click={() => error = ''} class="text-red-600 hover:text-red-800 cursor-pointer">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>
    {/if}

    <!-- Mobile Storage Card (visible only on small screens) -->
    <div class="lg:hidden bg-white rounded-lg p-4 mb-4 shadow-sm">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-500">Storage</p>
          <p class="text-xl font-bold text-gray-900">{status.total_kvk_stored.toLocaleString()}</p>
        </div>
        {#if status.total_kvk_stored > 0}
          <button
            on:click={() => showClearConfirm = true}
            class="text-xs text-red-600 hover:text-red-800 cursor-pointer"
          >
            Clear
          </button>
        {/if}
      </div>
    </div>

    <!-- Status Header -->
    <div class="bg-white rounded-lg p-4 sm:p-6 mb-4 sm:mb-6 shadow-sm">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2 sm:gap-3">
          <div class="w-8 h-8 sm:w-10 sm:h-10 bg-blue-50 rounded-lg flex items-center justify-center">
            <svg class="w-4 h-4 sm:w-5 sm:h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
            </svg>
          </div>
          <div>
            <h3 class="text-sm font-semibold text-gray-900">SCRAPER STATUS</h3>
            <p class="text-xs text-gray-500">Target: funda.nl</p>
          </div>
        </div>
        <span class="px-3 py-1 text-xs font-medium rounded-full {getStatusColor(status.status)}">
          {status.status}
        </span>
      </div>

      <!-- Progress Bar -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs sm:text-sm font-medium text-gray-700">Overall Progress</span>
          <span class="text-xl sm:text-2xl font-bold text-blue-600">{status.batch_progress}%</span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2.5">
          <div 
            class="bg-blue-600 h-2.5 rounded-full transition-all duration-500" 
            style="width: {status.batch_progress}%"
          ></div>
        </div>
        <div class="flex items-center justify-between mt-2 text-xs text-gray-600">
          <span>{status.active_workers > 0 ? `${status.active_workers} workers` : ''}{status.collection_status === 'collecting' ? ' · Collecting page ' + status.collection_page : ''}{status.collection_status === 'done' ? ' · Collection done' : ''}</span>
          <span>Elapsed: {elapsedFormatted}</span>
        </div>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 sm:gap-4 mb-4 sm:mb-6">
        <div class="bg-indigo-50 rounded-lg p-3 sm:p-4 text-center">
          <p class="text-xs text-indigo-600 mb-1">Collected</p>
          <p class="text-lg sm:text-2xl font-bold text-indigo-600">{status.ids_queued > 0 ? status.ids_queued.toLocaleString() : '—'}</p>
          <p class="text-xs text-indigo-500">new properties</p>
        </div>
        <div class="bg-orange-50 rounded-lg p-3 sm:p-4 text-center">
          <p class="text-xs text-orange-600 mb-1">Duplicate</p>
          <p class="text-lg sm:text-2xl font-bold text-orange-600">{status.duplicate_in_storage.toLocaleString()}</p>
          <p class="text-xs text-orange-500">already in storage</p>
        </div>
        <div class="bg-yellow-50 rounded-lg p-3 sm:p-4 text-center">
          <p class="text-xs text-yellow-600 mb-1">Filtered</p>
          <p class="text-lg sm:text-2xl font-bold text-yellow-600">{status.properties_filtered.toLocaleString()}</p>
          <p class="text-xs text-yellow-500">by price</p>
        </div>
        <div class="bg-blue-50 rounded-lg p-3 sm:p-4 text-center">
          <p class="text-xs text-blue-600 mb-1">Google Sheets</p>
          <p class="text-lg sm:text-2xl font-bold text-blue-600">{status.sheets_written}</p>
          <p class="text-xs text-blue-500">rows written</p>
        </div>
        <div class="bg-emerald-50 rounded-lg p-3 sm:p-4 text-center">
          <p class="text-xs text-emerald-600 mb-1">Bidding Calculated</p>
          <p class="text-lg sm:text-2xl font-bold text-emerald-600">{status.valuations_written}</p>
          <p class="text-xs text-emerald-500">{status.valuations_pending > 0 ? `${status.valuations_pending} pending` : 'suggested bids'}</p>
        </div>
      </div>

      {#if status.last_error}
        <div class="bg-red-50 rounded-lg p-3 text-sm text-red-700">
          <strong>Error:</strong> {status.last_error}
        </div>
      {/if}
    </div>

    <!-- Controls -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
      <!-- Publication Date Selector -->
      <div class="bg-white rounded-lg p-4 sm:p-6 shadow-sm">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Offered Since</h3>
        <p class="text-xs text-gray-500 mb-4">Select date range to scrape</p>
        
        <select
          bind:value={selectedPublicationDate}
          disabled={!isIdle}
          class="w-full px-4 py-3 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          {#each publicationDateOptions as option}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
        
        <p class="mt-3 text-xs text-gray-500">
          {#if selectedPublicationDate === 31}
            All properties listed 30+ days ago
          {:else if selectedPublicationDate === 30}
            Properties listed 25-30 days ago
          {:else if selectedPublicationDate === 15}
            Properties listed 13-17 days ago
          {:else if selectedPublicationDate === 10}
            Properties listed 8-12 days ago
          {:else}
            Properties listed 3-7 days ago
          {/if}
        </p>
      </div>

      <!-- Control Buttons -->
      <div class="bg-white rounded-lg p-4 sm:p-6 shadow-sm">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Controls</h3>
        <div class="space-y-3">
          <!-- Start Button -->
          <button
            on:click={handleStart}
            disabled={!canStart}
            class="w-full flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium rounded-lg transition-all cursor-pointer {!canStart ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'}"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z"></path>
            </svg>
            <span>Start</span>
          </button>

          <!-- Pause/Resume Button -->
          {#if isPaused}
            <button
              on:click={handleResume}
              disabled={!canResume}
              class="w-full flex items-center justify-center gap-2 px-6 py-3 bg-white text-gray-700 border border-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 transition-all shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"></path>
              </svg>
              <span>Resume</span>
            </button>
          {:else}
            <button
              on:click={handlePause}
              disabled={!canPause}
              class="w-full flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium rounded-lg transition-all cursor-pointer {!canPause ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 shadow-sm'}"
            >
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"></path>
              </svg>
              <span>Pause</span>
            </button>
          {/if}

          <!-- Stop Button -->
          <button
            on:click={handleStop}
            disabled={!canStop}
            class="w-full flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium rounded-lg transition-all cursor-pointer {!canStop ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-red-500 text-white hover:bg-red-600 shadow-sm'}"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 6h12v12H6z"></path>
            </svg>
            <span>Stop</span>
          </button>

          <!-- Export (Google Sheets Link) -->
          {#if sheetsUrl}
            <a
              href={sheetsUrl}
              target="_blank"
              rel="noopener noreferrer"
              class="w-full flex items-center justify-center gap-2 px-6 py-3 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-all shadow-sm cursor-pointer"
            >
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14zM7 10h2v7H7zm4-3h2v10h-2zm4 6h2v4h-2z"></path>
              </svg>
              <span>Open Google Sheets</span>
            </a>
          {/if}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Clear Storage Confirmation Modal -->
{#if showClearConfirm}
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
      <div class="text-center">
        <div class="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg class="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
          </svg>
        </div>
        <h3 class="text-xl font-semibold text-gray-900 mb-2">Clear Storage?</h3>
        <p class="text-gray-600 mb-6">
          This will delete all {status.total_kvk_stored.toLocaleString()} stored property IDs. 
          The scraper will start collecting from scratch.
        </p>
        <div class="flex gap-3">
          <button
            on:click={() => showClearConfirm = false}
            class="flex-1 px-4 py-2 bg-gray-200 text-gray-700 font-medium rounded-lg hover:bg-gray-300 cursor-pointer"
          >
            Cancel
          </button>
          <button
            on:click={handleClearStorage}
            disabled={loading}
            class="flex-1 px-4 py-2 bg-red-500 text-white font-medium rounded-lg hover:bg-red-600 cursor-pointer disabled:opacity-50"
          >
            {loading ? 'Clearing...' : 'Clear All'}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
