<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import Router from 'svelte-spa-router';
  import { wrap } from 'svelte-spa-router/wrap';
  import { authStore } from './lib/stores/auth';
  import { websocketService } from './lib/services/websocket';
  import { get } from 'svelte/store';
  import Login from './pages/auth/Login.svelte';
  import Register from './pages/auth/Register.svelte';
  import Home from './pages/Home.svelte';
  import ScraplyDashboard from './pages/tools/scraply/Dashboard.svelte';

  let unsubscribe: () => void;

  onMount(() => {
    // Listen to auth changes to connect/disconnect WebSocket
    unsubscribe = authStore.subscribe((auth) => {
      if (auth.isAuthenticated && auth.token) {
        // Connect WebSocket when user is authenticated
        websocketService.connect();
      } else {
        // Disconnect WebSocket when user logs out
        websocketService.disconnect();
      }
    });
  });

  onDestroy(() => {
    if (unsubscribe) unsubscribe();
    websocketService.disconnect();
  });

  // Protected route wrapper
  function protectedRoute(component: any) {
    return wrap({
      component,
      conditions: [
        () => {
          const auth = get(authStore);
          if (!auth.isAuthenticated) {
            // Redirect to login if not authenticated
            setTimeout(() => {
              window.location.hash = '#/';
            }, 0);
            return false;
          }
          return true;
        }
      ],
      loadingComponent: null,
      loadingParams: null,
    });
  }

  const routes = {
    '/': Login,
    '/register': Register,
    '/home': protectedRoute(Home),
    '/tools/scraply': protectedRoute(ScraplyDashboard),
    '*': Login, // Fallback to login
  };
</script>

<Router {routes} restoreScrollState={true} />
