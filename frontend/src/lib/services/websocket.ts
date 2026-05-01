import { authStore } from '../stores/auth';
import { notificationStore } from '../stores/notifications';
import { get } from 'svelte/store';
import { config } from '../config/env';

interface WebSocketMessage {
  type: string;
  job_uuid?: string;
  update_type?: string;
  data?: any;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: any = null;
  private isConnecting = false;
  private subscribedJobs = new Set<string>();

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    const auth = get(authStore);
    if (!auth.isAuthenticated || !auth.token) {
      console.log('WebSocket: Not authenticated, skipping connection');
      return;
    }

    this.isConnecting = true;

    try {
      // Get WebSocket URL from config
      const wsUrl = `${config.WS_BASE_URL}/api/v1/ws?token=${auth.token}`;

      console.log('WebSocket: Connecting to', wsUrl.replace(auth.token, 'TOKEN'));

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket: Connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.startHeartbeat();

        // Re-subscribe to all jobs
        this.subscribedJobs.forEach(jobUuid => {
          this.subscribeToJob(jobUuid);
        });

        notificationStore.add({
          type: 'info',
          title: 'Connected',
          message: 'Real-time updates enabled'
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('WebSocket: Failed to parse message', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket: Error', error);
        this.isConnecting = false;
      };

      this.ws.onclose = () => {
        console.log('WebSocket: Connection closed');
        this.isConnecting = false;
        this.stopHeartbeat();
        this.scheduleReconnect();
      };
    } catch (error) {
      console.error('WebSocket: Connection error', error);
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  private handleMessage(message: WebSocketMessage) {
    console.log('WebSocket: Message received', message);

    if (message.type === 'pong') {
      return; // Heartbeat response
    }

    if (message.type === 'job_update') {
      this.handleJobUpdate(message);
    }
  }

  private handleJobUpdate(message: WebSocketMessage) {
    const { job_uuid, update_type, data } = message;

    if (!update_type || !data) return;

    switch (update_type) {
      case 'status':
        this.handleStatusUpdate(job_uuid || '', data);
        break;
      case 'progress':
        this.handleProgressUpdate(job_uuid || '', data);
        break;
      case 'log':
        this.handleLogUpdate(job_uuid || '', data);
        break;
      case 'error':
        this.handleErrorUpdate(job_uuid || '', data);
        break;
    }
  }

  private handleStatusUpdate(jobUuid: string, data: any) {
    const status = data.status;
    let type: 'success' | 'error' | 'warning' | 'info' = 'info';
    let title = 'Job Status Update';
    let message = `Job status changed to ${status}`;

    if (status === 'completed') {
      type = 'success';
      title = 'Job Completed';
      message = `Job ${data.name || jobUuid.slice(0, 8)} has finished successfully`;
    } else if (status === 'failed') {
      type = 'error';
      title = 'Job Failed';
      message = `Job ${data.name || jobUuid.slice(0, 8)} has failed`;
    } else if (status === 'running') {
      type = 'info';
      title = 'Job Started';
      message = `Job ${data.name || jobUuid.slice(0, 8)} is now running`;
    } else if (status === 'paused') {
      type = 'warning';
      title = 'Job Paused';
      message = `Job ${data.name || jobUuid.slice(0, 8)} has been paused`;
    } else if (status === 'cancelled') {
      type = 'warning';
      title = 'Job Cancelled';
      message = `Job ${data.name || jobUuid.slice(0, 8)} has been cancelled`;
    }

    notificationStore.add({
      type,
      title,
      message,
      jobUuid
    });

    // Dispatch custom event for other components to listen
    window.dispatchEvent(new CustomEvent('job-status-change', {
      detail: { jobUuid, status, data }
    }));
  }

  private handleProgressUpdate(jobUuid: string, data: any) {
    const progress = data.progress || 0;
    const message = data.message || `Progress: ${progress}%`;

    // Only notify on significant progress milestones
    if (progress % 25 === 0 && progress > 0 && progress < 100) {
      notificationStore.add({
        type: 'info',
        title: 'Job Progress',
        message: `${data.name || jobUuid.slice(0, 8)}: ${message}`,
        jobUuid
      });
    }

    // Dispatch custom event
    window.dispatchEvent(new CustomEvent('job-progress', {
      detail: { jobUuid, progress, data }
    }));
  }

  private handleLogUpdate(jobUuid: string, data: any) {
    // Only create notifications for important logs
    if (data.level === 'error' || data.level === 'warning') {
      notificationStore.add({
        type: data.level === 'error' ? 'error' : 'warning',
        title: `Job ${data.level.toUpperCase()}`,
        message: data.message || 'Check logs for details',
        jobUuid
      });
    }

    // Dispatch custom event
    window.dispatchEvent(new CustomEvent('job-log', {
      detail: { jobUuid, data }
    }));
  }

  private handleErrorUpdate(jobUuid: string, data: any) {
    notificationStore.add({
      type: 'error',
      title: 'Job Error',
      message: data.message || 'An error occurred',
      jobUuid
    });

    // Dispatch custom event
    window.dispatchEvent(new CustomEvent('job-error', {
      detail: { jobUuid, data }
    }));
  }

  subscribeToJob(jobUuid: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.subscribedJobs.add(jobUuid);
      return;
    }

    this.subscribedJobs.add(jobUuid);
    this.ws.send(JSON.stringify({
      action: 'subscribe',
      job_uuid: jobUuid
    }));
  }

  unsubscribeFromJob(jobUuid: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.subscribedJobs.delete(jobUuid);
      return;
    }

    this.subscribedJobs.delete(jobUuid);
    this.ws.send(JSON.stringify({
      action: 'unsubscribe',
      job_uuid: jobUuid
    }));
  }

  private startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 30000); // Every 30 seconds
  }

  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('WebSocket: Max reconnection attempts reached');
      // Silently stop reconnecting without showing notification
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`WebSocket: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect() {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.subscribedJobs.clear();
    this.reconnectAttempts = 0;
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const websocketService = new WebSocketService();
