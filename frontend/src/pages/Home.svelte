<script lang="ts">
  import AppLayout from '../components/layout/AppLayout.svelte';
  import { push } from 'svelte-spa-router';

  interface Tool {
    id: string;
    name: string;
    description: string;
    icon: string;
    category: string;
    status: 'active' | 'coming-soon';
    route: string;
  }

  const tools: Tool[] = [
    {
      id: 'scraply',
      name: 'Company Info Scraper',
      description: 'Scrape phone numbers and emails from company.info for Dutch businesses',
      icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
      category: 'Data Scraper',
      status: 'active',
      route: '/tools/scraply',
    },
    {
      id: 'emailbot',
      name: 'Email Bot',
      description: 'Automated email campaigns and follow-ups',
      icon: 'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
      category: 'Email',
      status: 'coming-soon',
      route: '#',
    },
    {
      id: 'leadgen',
      name: 'Lead Generator',
      description: 'Find and verify potential leads from multiple sources',
      icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
      category: 'Lead Gen',
      status: 'coming-soon',
      route: '#',
    },
    {
      id: 'dataparser',
      name: 'Data Parser',
      description: 'Transform and clean data from multiple sources',
      icon: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2',
      category: 'Data Scraper',
      status: 'coming-soon',
      route: '#',
    },
    {
      id: 'scheduler',
      name: 'Task Scheduler',
      description: 'Schedule and automate recurring tasks',
      icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
      category: 'Automation',
      status: 'coming-soon',
      route: '#',
    },
    {
      id: 'workflow',
      name: 'Workflow Builder',
      description: 'Create custom automation workflows visually',
      icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
      category: 'Automation',
      status: 'coming-soon',
      route: '#',
    },
  ];

  let searchQuery = '';
  let activeFilter = 'all';
  let activeCategory = 'All Tools';

  const categories = ['All Tools', 'Data Scraper', 'Email', 'Lead Gen', 'Automation'];
  const filters = [
    { id: 'all', label: 'All', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z' },
    { id: 'favorites', label: 'Favorites', icon: 'M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z' },
    { id: 'recent', label: 'Recent', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
    { id: 'most-used', label: 'Most Used', icon: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6' },
  ];

  $: filteredTools = tools.filter(tool => {
    const matchesSearch = tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         tool.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = activeCategory === 'All Tools' || tool.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  function handleToolClick(tool: Tool) {
    if (tool.status === 'active') {
      push(tool.route);
    }
  }
</script>

<AppLayout>
  <div class="min-h-screen bg-[#f5f5f5]">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- Search and Filters Bar -->
      <div class="flex flex-col gap-4 mb-6">
        <!-- Search -->
        <div class="relative w-full sm:max-w-md">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <input
            type="text"
            placeholder="Search tools..."
            bind:value={searchQuery}
            class="w-full pl-10 pr-4 py-2.5 bg-transparent border border-gray-300 text-sm text-gray-900 placeholder-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Filter Buttons -->
        <div class="flex items-center gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0">
          <button class="p-2 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path>
            </svg>
          </button>
          {#each filters as filter}
            <button
              on:click={() => activeFilter = filter.id}
              class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer {activeFilter === filter.id ? 'bg-primary-500 text-white border border-primary-600' : 'bg-gray-50 text-gray-700 hover:bg-gray-100 border border-transparent'}"
            >
              <svg class="w-4 h-4" fill={activeFilter === filter.id ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={filter.icon}></path>
              </svg>
              <span>{filter.label}</span>
            </button>
          {/each}
        </div>
      </div>

      <!-- Category Tabs -->
      <div class="flex items-center gap-3 sm:gap-4 mb-5 overflow-x-auto pb-2 -mx-4 px-4 sm:mx-0 sm:px-0">
        {#each categories as category}
          <button
            on:click={() => activeCategory = category}
            class="flex items-center gap-2 px-4 py-2 text-sm font-medium whitespace-nowrap rounded-lg transition-colors cursor-pointer {activeCategory === category ? 'bg-primary-50 text-primary-600 border border-primary-200' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50 border border-transparent'}"
          >
            {#if category === 'All Tools'}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path>
              </svg>
            {:else if category === 'Data Scraper'}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
              </svg>
            {:else if category === 'Email'}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
              </svg>
            {:else if category === 'Lead Gen'}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
              </svg>
            {:else}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
              </svg>
            {/if}
            <span>{category}</span>
          </button>
        {/each}
      </div>

      <!-- Separator -->
      <div class="border-t border-gray-300 mb-5"></div>

      <!-- Tools Grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {#each filteredTools as tool}
          <button
            on:click={() => handleToolClick(tool)}
            class="group relative bg-white rounded-lg p-6 text-left shadow-sm transition-all {tool.status === 'coming-soon' ? 'opacity-40 cursor-not-allowed' : 'hover:shadow-md cursor-pointer'}"
          >
            <!-- Icon -->
            <div class="w-12 h-12 bg-primary-50 rounded-lg flex items-center justify-center mb-4 {tool.status === 'active' ? 'group-hover:bg-primary-100' : ''} transition-colors">
              <svg class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={tool.icon}></path>
              </svg>
            </div>

            <!-- Content -->
            <div class="mb-3">
              <h3 class="text-base font-semibold text-gray-900 mb-1 {tool.status === 'active' ? 'group-hover:text-primary-600' : ''} transition-colors">
                {tool.name}
              </h3>
              <p class="text-sm text-gray-600 line-clamp-2">
                {tool.description}
              </p>
            </div>

            <!-- Status Badge -->
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-500">{tool.category}</span>
              {#if tool.status === 'coming-soon'}
                <span class="text-xs font-medium text-gray-400">Coming Soon</span>
              {:else}
                <svg class="w-4 h-4 text-primary-600 {tool.status === 'active' ? 'group-hover:translate-x-1' : ''} transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                </svg>
              {/if}
            </div>
          </button>
        {/each}
      </div>

      <!-- Info Card -->
      {#if filteredTools.length === 0}
        <div class="mt-12 bg-white rounded-lg p-8 text-center">
          <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <p class="text-gray-600">No tools found matching your search.</p>
        </div>
      {/if}
    </div>
  </div>
</AppLayout>
