<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { jobsAPI } from '../../../lib/api/jobs';
  import { filesAPI } from '../../../lib/api/files';
  import { websocketService } from '../../../lib/services/websocket';
  import CsvColumnMapperModal from '../../../components/common/CsvColumnMapperModal.svelte';
  import { push } from 'svelte-spa-router';

  // ── Types ────────────────────────────────────────────────────
  type ViewState = 'list' | 'active';
  interface ColumnMap { col_company: string; col_street: string; col_house_number: string; col_city: string; }

  // ── State ────────────────────────────────────────────────────
  let view: ViewState = 'list';
  let jobs: any[] = [];
  let activeJob: any = null;
  let totalJobs = 0;

  let uploading = false;
  let uploadError = '';
  let actionError = '';
  let loadingAction = false;

  let showMapper = false;
  let csvColumns: string[] = [];
  let pendingJobUuid = '';
  let pendingUploadFilename = '';

  let fileInput: HTMLInputElement;
  let pollInterval: any = null;

  // ── Lifecycle ────────────────────────────────────────────────
  onMount(async () => {
    await loadJobs();
    // Auto-open most recent running/paused job
    const live = jobs.find(j => j.status === 'running' || j.status === 'paused' || j.status === 'queued');
    if (live) openJob(live);
    startPolling();
    listenWebSocket();
  });

  onDestroy(() => {
    stopPolling();
    window.removeEventListener('job-status-change', onWsStatusChange);
    window.removeEventListener('job-progress', onWsProgress);
  });

  // ── Polling ──────────────────────────────────────────────────
  function startPolling() {
    stopPolling();
    pollInterval = setInterval(async () => {
      await loadJobs();
      if (activeJob) {
        const updated = jobs.find(j => j.job_uuid === activeJob.job_uuid);
        if (updated) activeJob = updated;
      }
    }, 3000);
  }

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  }

  // ── WebSocket ────────────────────────────────────────────────
  function listenWebSocket() {
    window.addEventListener('job-status-change', onWsStatusChange as any);
    window.addEventListener('job-progress', onWsProgress as any);
  }

  function onWsStatusChange(e: CustomEvent) {
    if (activeJob && e.detail.jobUuid === activeJob.job_uuid) {
      activeJob = { ...activeJob, status: e.detail.status, ...e.detail.data };
    }
    loadJobs();
  }

  function onWsProgress(e: CustomEvent) {
    if (activeJob && e.detail.jobUuid === activeJob.job_uuid) {
      activeJob = { ...activeJob, progress: e.detail.progress, ...e.detail.data };
    }
  }

  // ── Data ─────────────────────────────────────────────────────
  async function loadJobs() {
    try {
      const res = await jobsAPI.listJobs({ page: 1, page_size: 50 });
      jobs = res.jobs;
      totalJobs = res.total;
    } catch (e) { /* silent */ }
  }

  // ── Upload flow ──────────────────────────────────────────────
  function triggerUpload() {
    uploadError = '';
    fileInput.click();
  }

  async function handleFileSelected(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    (e.target as HTMLInputElement).value = '';

    uploading = true;
    uploadError = '';

    try {
      // 1. Create job
      const jobName = `Scraply - ${file.name}`;
      const job = await jobsAPI.createJob({
        tool_type: 'scraply',
        name: jobName,
        config: {}
      });
      pendingJobUuid = job.job_uuid;

      // 2. Upload file
      const uploaded = await filesAPI.uploadFile(file, job.job_uuid);
      pendingUploadFilename = uploaded.filename;

      // 3. Get CSV headers
      csvColumns = await filesAPI.getCsvHeaders(uploaded.filename);

      // 4. Open column mapper
      showMapper = true;
    } catch (err: any) {
      uploadError = err.response?.data?.detail || 'Upload failed. Please try again.';
    } finally {
      uploading = false;
    }
  }

  async function handleMapComplete(e: CustomEvent) {
    const colMap: ColumnMap = e.detail;
    showMapper = false;

    try {
      // 5. Update job config with column mapping
      await jobsAPI.updateJob(pendingJobUuid, { config: colMap });

      // 6. Start job
      const started = await jobsAPI.startJob(pendingJobUuid);
      websocketService.subscribeToJob(started.job_uuid);
      await loadJobs();
      const fresh = jobs.find(j => j.job_uuid === started.job_uuid) || started;
      openJob(fresh);
    } catch (err: any) {
      uploadError = err.response?.data?.detail || 'Failed to start job.';
    }
  }

  function handleMapCancel() {
    showMapper = false;
    // Delete the pending job since user cancelled
    if (pendingJobUuid) jobsAPI.deleteJob(pendingJobUuid).catch(() => {});
    pendingJobUuid = '';
  }

  // ── Job controls ─────────────────────────────────────────────
  function openJob(job: any) {
    activeJob = job;
    view = 'active';
    websocketService.subscribeToJob(job.job_uuid);
  }

  function backToList() {
    view = 'list';
    if (activeJob) {
      websocketService.unsubscribeFromJob(activeJob.job_uuid);
      activeJob = null;
    }
    loadJobs();
  }

  async function pauseJob() {
    if (!activeJob) return;
    loadingAction = true; actionError = '';
    try { activeJob = await jobsAPI.pauseJob(activeJob.job_uuid); } catch (e: any) { actionError = e.response?.data?.detail || 'Failed to pause'; } finally { loadingAction = false; }
  }

  async function resumeJob() {
    if (!activeJob) return;
    loadingAction = true; actionError = '';
    try { activeJob = await jobsAPI.resumeJob(activeJob.job_uuid); } catch (e: any) { actionError = e.response?.data?.detail || 'Failed to resume'; } finally { loadingAction = false; }
  }

  async function cancelJob() {
    if (!activeJob) return;
    loadingAction = true; actionError = '';
    try { activeJob = await jobsAPI.cancelJob(activeJob.job_uuid); await loadJobs(); } catch (e: any) { actionError = e.response?.data?.detail || 'Failed to cancel'; } finally { loadingAction = false; }
  }

  async function downloadResult() {
    if (!activeJob) return;
    try {
      const blob = await jobsAPI.downloadJobResult(activeJob.job_uuid);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = activeJob.display_filename || 'result.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) { actionError = e.response?.data?.detail || 'Download failed'; }
  }

  async function retryJob() {
    if (!activeJob) return;
    loadingAction = true; actionError = '';
    try { activeJob = await jobsAPI.retryJob(activeJob.job_uuid); } catch (e: any) { actionError = e.response?.data?.detail || 'Failed to retry'; } finally { loadingAction = false; }
  }

  // ── Helpers ──────────────────────────────────────────────────
  function statusColor(s: string) {
    switch (s) {
      case 'running': return 'bg-green-100 text-green-700';
      case 'paused': return 'bg-yellow-100 text-yellow-700';
      case 'completed': return 'bg-blue-100 text-blue-700';
      case 'failed': return 'bg-red-100 text-red-700';
      case 'cancelled': return 'bg-gray-100 text-gray-500';
      case 'queued': return 'bg-purple-100 text-purple-700';
      default: return 'bg-gray-100 text-gray-500';
    }
  }

  function formatDate(d: string) {
    if (!d) return '—';
    return new Date(d).toLocaleString('nl-NL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function formatDuration(started: string, completed: string) {
    if (!started) return '—';
    const end = completed ? new Date(completed) : new Date();
    const secs = Math.floor((end.getTime() - new Date(started).getTime()) / 1000);
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs/60)}m ${secs%60}s`;
    return `${Math.floor(secs/3600)}h ${Math.floor((secs%3600)/60)}m`;
  }

  $: isLive = activeJob && (activeJob.status === 'running' || activeJob.status === 'queued');
  $: isPaused = activeJob?.status === 'paused';
  $: isDone = activeJob && (activeJob.status === 'completed' || activeJob.status === 'failed' || activeJob.status === 'cancelled');
  $: successRate = activeJob?.processed_rows > 0
    ? Math.round((activeJob.successful_rows / activeJob.processed_rows) * 100)
    : 0;
</script>

<!-- Hidden file input -->
<input bind:this={fileInput} type="file" accept=".csv,.xlsx,.xls" class="hidden" on:change={handleFileSelected} />

<!-- Column mapper modal -->
<CsvColumnMapperModal bind:show={showMapper} columns={csvColumns} on:complete={handleMapComplete} on:cancel={handleMapCancel} />

<div class="min-h-screen flex flex-col lg:flex-row" style="background-color: #F2EFE7;">

  <!-- Sidebar -->
  <div class="w-full lg:w-64 bg-white flex flex-col lg:min-h-screen shadow-sm">
    <div class="flex items-center justify-between lg:flex-col lg:items-stretch">
      <!-- Back button -->
      <button on:click={() => push('/home')} class="flex items-center gap-2 px-4 py-3 lg:px-6 lg:py-4 text-sm text-gray-600 hover:text-gray-900 border-b border-gray-200 cursor-pointer">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
        <span>Back to Tools</span>
      </button>

      <!-- Logo -->
      <div class="px-4 py-3 lg:px-6 lg:py-6 lg:border-b border-gray-200">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 lg:w-12 lg:h-12 bg-blue-600 rounded-xl flex items-center justify-center shrink-0">
            <svg class="w-5 h-5 lg:w-6 lg:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
          </div>
          <div>
            <h2 class="text-base lg:text-lg font-semibold text-gray-900">Scraply</h2>
            <p class="text-xs text-gray-500 hidden lg:block">Company Info Scraper</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Stats (desktop sidebar) -->
    <div class="hidden lg:block flex-1 px-4 py-6 space-y-3">
      <div class="bg-gray-50 rounded-lg p-4">
        <p class="text-xs text-gray-500 mb-1">Total Jobs</p>
        <p class="text-2xl font-bold text-gray-900">{totalJobs}</p>
      </div>
      <div class="bg-blue-50 rounded-lg p-4">
        <p class="text-xs text-blue-600 mb-1">Completed</p>
        <p class="text-2xl font-bold text-blue-700">{jobs.filter(j => j.status === 'completed').length}</p>
      </div>
      <div class="bg-green-50 rounded-lg p-4">
        <p class="text-xs text-green-600 mb-1">Running</p>
        <p class="text-2xl font-bold text-green-700">{jobs.filter(j => j.status === 'running' || j.status === 'queued').length}</p>
      </div>
    </div>
  </div>

  <!-- Main content -->
  <div class="flex-1 p-4 sm:p-6 lg:p-8">

    <!-- Upload error -->
    {#if uploadError}
      <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4 flex items-center justify-between">
        <span class="text-sm text-red-800">{uploadError}</span>
        <button on:click={() => uploadError = ''} aria-label="Dismiss" class="text-red-500 hover:text-red-700 cursor-pointer ml-3">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
    {/if}

    <!-- ── ACTIVE JOB VIEW ── -->
    {#if view === 'active' && activeJob}

      <!-- Header row -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div class="flex items-center gap-3">
          <button on:click={backToList} class="text-gray-500 hover:text-gray-800 cursor-pointer" aria-label="Back to list">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h2 class="text-base sm:text-lg font-semibold text-gray-900 truncate max-w-xs sm:max-w-sm">{activeJob.name}</h2>
            <p class="text-xs text-gray-500">{formatDate(activeJob.created_at)}</p>
          </div>
          <span class="px-2.5 py-1 rounded-full text-xs font-medium {statusColor(activeJob.status)}">{activeJob.status.toUpperCase()}</span>
        </div>

        <!-- Action error -->
        {#if actionError}
          <p class="text-sm text-red-600">{actionError}</p>
        {/if}
      </div>

      <!-- Progress card -->
      <div class="bg-white rounded-xl shadow-sm p-4 sm:p-6 mb-4">
        <div class="flex items-center justify-between mb-3">
          <span class="text-sm font-medium text-gray-700">Progress</span>
          <span class="text-2xl sm:text-3xl font-bold text-blue-600">{Math.round(activeJob.progress ?? 0)}%</span>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-3 mb-2">
          <div class="bg-blue-600 h-3 rounded-full transition-all duration-500" style="width: {activeJob.progress ?? 0}%"></div>
        </div>
        <div class="flex justify-between text-xs text-gray-500">
          <span>{activeJob.processed_rows ?? 0} / {activeJob.total_rows ?? 0} rows</span>
          <span>Duration: {formatDuration(activeJob.started_at, activeJob.completed_at)}</span>
        </div>
      </div>

      <!-- Stats grid -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div class="bg-white rounded-xl p-4 shadow-sm text-center">
          <p class="text-xs text-gray-500 mb-1">Total Rows</p>
          <p class="text-xl sm:text-2xl font-bold text-gray-900">{(activeJob.total_rows ?? 0).toLocaleString()}</p>
        </div>
        <div class="bg-blue-50 rounded-xl p-4 shadow-sm text-center">
          <p class="text-xs text-blue-600 mb-1">Processed</p>
          <p class="text-xl sm:text-2xl font-bold text-blue-700">{(activeJob.processed_rows ?? 0).toLocaleString()}</p>
        </div>
        <div class="bg-green-50 rounded-xl p-4 shadow-sm text-center">
          <p class="text-xs text-green-600 mb-1">Successful</p>
          <p class="text-xl sm:text-2xl font-bold text-green-700">{(activeJob.successful_rows ?? 0).toLocaleString()}</p>
          {#if activeJob.processed_rows > 0}
            <p class="text-xs text-green-500">{successRate}% rate</p>
          {/if}
        </div>
        <div class="bg-red-50 rounded-xl p-4 shadow-sm text-center">
          <p class="text-xs text-red-500 mb-1">Failed</p>
          <p class="text-xl sm:text-2xl font-bold text-red-600">{(activeJob.failed_rows ?? 0).toLocaleString()}</p>
        </div>
      </div>

      <!-- Controls -->
      <div class="bg-white rounded-xl shadow-sm p-4 sm:p-6">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Controls</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">

          {#if isLive}
            <button on:click={pauseJob} disabled={loadingAction} class="flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 bg-white text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
              Pause
            </button>
            <button on:click={cancelJob} disabled={loadingAction} class="flex items-center justify-center gap-2 px-4 py-3 bg-red-500 text-white text-sm font-medium rounded-lg hover:bg-red-600 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
              Cancel
            </button>
          {/if}

          {#if isPaused}
            <button on:click={resumeJob} disabled={loadingAction} class="flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              Resume
            </button>
            <button on:click={cancelJob} disabled={loadingAction} class="flex items-center justify-center gap-2 px-4 py-3 bg-red-500 text-white text-sm font-medium rounded-lg hover:bg-red-600 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
              Cancel
            </button>
          {/if}

          {#if isDone}
            {#if activeJob.status === 'completed'}
              <button on:click={downloadResult} class="flex items-center justify-center gap-2 px-4 py-3 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 cursor-pointer transition-all shadow-sm">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                Download Results
              </button>
            {/if}
            {#if activeJob.status === 'failed'}
              <button on:click={retryJob} disabled={loadingAction} class="flex items-center justify-center gap-2 px-4 py-3 bg-orange-500 text-white text-sm font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                Retry Job
              </button>
            {/if}
            <button on:click={triggerUpload} disabled={uploading} class="flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 bg-white text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 cursor-pointer transition-all shadow-sm">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
              New Upload
            </button>
          {/if}

        </div>
      </div>

    {:else}
      <!-- ── LIST VIEW ── -->

      <!-- Top bar: title + upload button -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 class="text-lg sm:text-xl font-semibold text-gray-900">Company Info Scraper</h1>
          <p class="text-sm text-gray-500">Upload a CSV to extract phone & email from company.info</p>
        </div>
        <button on:click={triggerUpload} disabled={uploading} class="flex items-center justify-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-60 cursor-pointer shadow-sm transition-all shrink-0">
          {#if uploading}
            <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Uploading...
          {:else}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
            Upload CSV
          {/if}
        </button>
      </div>

      <!-- Mobile stats -->
      <div class="grid grid-cols-3 gap-3 mb-5 lg:hidden">
        <div class="bg-white rounded-lg p-3 text-center shadow-sm">
          <p class="text-xs text-gray-500">Total</p>
          <p class="text-xl font-bold text-gray-900">{totalJobs}</p>
        </div>
        <div class="bg-white rounded-lg p-3 text-center shadow-sm">
          <p class="text-xs text-blue-600">Done</p>
          <p class="text-xl font-bold text-blue-700">{jobs.filter(j => j.status === 'completed').length}</p>
        </div>
        <div class="bg-white rounded-lg p-3 text-center shadow-sm">
          <p class="text-xs text-green-600">Running</p>
          <p class="text-xl font-bold text-green-700">{jobs.filter(j => j.status === 'running' || j.status === 'queued').length}</p>
        </div>
      </div>

      <!-- Jobs list -->
      {#if jobs.length === 0}
        <div class="bg-white rounded-xl shadow-sm p-10 text-center">
          <svg class="w-12 h-12 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          <p class="text-gray-500 text-sm mb-4">No jobs yet. Upload a CSV file to get started.</p>
          <button on:click={triggerUpload} class="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 cursor-pointer">
            Upload CSV
          </button>
        </div>
      {:else}
        <div class="bg-white rounded-xl shadow-sm overflow-hidden">
          <!-- Table header (desktop) -->
          <div class="hidden sm:grid grid-cols-12 gap-2 px-4 py-3 bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wide">
            <div class="col-span-4">File</div>
            <div class="col-span-2 text-center">Status</div>
            <div class="col-span-2 text-center">Rows</div>
            <div class="col-span-2 text-center">Success</div>
            <div class="col-span-2 text-right">Date</div>
          </div>

          <!-- Rows -->
          {#each jobs as job}
            <button
              on:click={() => openJob(job)}
              class="w-full text-left px-4 py-3.5 border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer last:border-0"
            >
              <!-- Mobile layout -->
              <div class="sm:hidden flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="text-sm font-medium text-gray-900 truncate">{job.display_filename || job.name}</p>
                  <p class="text-xs text-gray-500 mt-0.5">{formatDate(job.created_at)}</p>
                  <div class="flex items-center gap-2 mt-1">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium {statusColor(job.status)}">{job.status}</span>
                    {#if job.total_rows > 0}
                      <span class="text-xs text-gray-500">{job.processed_rows}/{job.total_rows} rows</span>
                    {/if}
                  </div>
                </div>
                <svg class="w-4 h-4 text-gray-400 shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
              </div>

              <!-- Desktop layout -->
              <div class="hidden sm:grid grid-cols-12 gap-2 items-center">
                <div class="col-span-4 min-w-0">
                  <p class="text-sm font-medium text-gray-900 truncate">{job.display_filename || job.name}</p>
                </div>
                <div class="col-span-2 text-center">
                  <span class="px-2.5 py-1 rounded-full text-xs font-medium {statusColor(job.status)}">{job.status}</span>
                </div>
                <div class="col-span-2 text-center text-sm text-gray-700">
                  {job.total_rows > 0 ? `${job.processed_rows}/${job.total_rows}` : '—'}
                </div>
                <div class="col-span-2 text-center text-sm text-gray-700">
                  {job.successful_rows > 0 ? `${job.successful_rows} ✓` : '—'}
                </div>
                <div class="col-span-2 text-right text-xs text-gray-500">
                  {formatDate(job.created_at)}
                </div>
              </div>

              <!-- Progress bar for running jobs -->
              {#if job.status === 'running' || job.status === 'paused'}
                <div class="mt-2 w-full bg-gray-100 rounded-full h-1">
                  <div class="bg-blue-500 h-1 rounded-full transition-all" style="width: {job.progress ?? 0}%"></div>
                </div>
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    {/if}

  </div>
</div>
