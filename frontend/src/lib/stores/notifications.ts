import { writable, derived } from 'svelte/store';

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: Date;
  read: boolean;
  jobUuid?: string;
  actionUrl?: string;
}

interface NotificationStore {
  notifications: Notification[];
  unreadCount: number;
}

function createNotificationStore() {
  const { subscribe, update } = writable<NotificationStore>({
    notifications: [],
    unreadCount: 0
  });

  // Load notifications from localStorage on init
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('notifications');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        const notifications = parsed.map((n: any) => ({
          ...n,
          timestamp: new Date(n.timestamp)
        }));
        update(state => ({
          notifications,
          unreadCount: notifications.filter((n: Notification) => !n.read).length
        }));
      } catch (e) {
        console.error('Failed to load notifications:', e);
      }
    }
  }

  function persist(notifications: Notification[]) {
    if (typeof window !== 'undefined') {
      localStorage.setItem('notifications', JSON.stringify(notifications));
    }
  }

  return {
    subscribe,

    add(notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) {
      const newNotification: Notification = {
        ...notification,
        id: `${Date.now()}-${Math.random()}`,
        timestamp: new Date(),
        read: false
      };

      update(state => {
        const notifications = [newNotification, ...state.notifications].slice(0, 100); // Keep last 100
        persist(notifications);
        return {
          notifications,
          unreadCount: notifications.filter(n => !n.read).length
        };
      });

      // Play notification sound
      playNotificationSound();

      return newNotification.id;
    },

    markAsRead(id: string) {
      update(state => {
        const notifications = state.notifications.map(n =>
          n.id === id ? { ...n, read: true } : n
        );
        persist(notifications);
        return {
          notifications,
          unreadCount: notifications.filter(n => !n.read).length
        };
      });
    },

    markAllAsRead() {
      update(state => {
        const notifications = state.notifications.map(n => ({ ...n, read: true }));
        persist(notifications);
        return {
          notifications,
          unreadCount: 0
        };
      });
    },

    clearRead() {
      update(state => {
        const notifications = state.notifications.filter(n => !n.read);
        persist(notifications);
        return {
          notifications,
          unreadCount: notifications.length
        };
      });
    },

    clear() {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('notifications');
      }
      update(() => ({
        notifications: [],
        unreadCount: 0
      }));
    },

    remove(id: string) {
      update(state => {
        const notifications = state.notifications.filter(n => n.id !== id);
        persist(notifications);
        return {
          notifications,
          unreadCount: notifications.filter(n => !n.read).length
        };
      });
    }
  };
}

function playNotificationSound() {
  try {
    // Using a louder, longer notification sound - triple bell chime
    const audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
    audio.volume = 1.0; // Maximum volume
    audio.play().catch(err => console.log('Sound play failed:', err));
  } catch (e) {
    // Silently fail
  }
}

export const notificationStore = createNotificationStore();

// Derived store for easy access to just notifications array
export const notifications = derived(
  notificationStore,
  $store => $store.notifications
);

// Derived store for unread count
export const unreadCount = derived(
  notificationStore,
  $store => $store.unreadCount
);
