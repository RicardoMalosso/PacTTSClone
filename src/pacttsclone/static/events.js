'use strict';
// One EventSource per page. Coalesce pending renders by topic; REST is the
// recovery baseline, never a replay of commands, audio or integration actions.
window.StudioEventStream = class {
  constructor({handlers, synchronize, fallback, enabled = true, fallbackMs = 5000}) {
    this.handlers = handlers;
    this.synchronize = synchronize;
    this.fallback = fallback;
    this.enabled = enabled && typeof EventSource !== 'undefined';
    this.fallbackMs = fallbackMs;
    this.pending = new Map();
    this.lastEvent = 0;
    this.connected = false;
    this.stopped = false;
    this.timer = null;
    this.source = null;
    this.draining = false;
    this.retryAt = 0;
    this.onVisibility = () => { if (!document.hidden) this.resync(); };
    this.onOffline = () => {
      this.connected = false; this.source?.close(); this.source = null;
    };
    this.onOnline = () => { this.retryAt = 0; this.connect(); this.resync(); };
    document.addEventListener('visibilitychange', this.onVisibility);
    window.addEventListener('offline', this.onOffline);
    window.addEventListener('online', this.onOnline);
    window.addEventListener('pagehide', () => this.close(), {once: true});
    // A page restored from the back/forward cache needs a new stream and token.
    window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
  }
  get healthy() { return this.connected && Date.now() - this.lastEvent < 20000; }
  start() {
    this.connect();
    this.timer = setInterval(() => {
      if (!this.healthy) {
        if (this.source && Date.now() - this.lastEvent >= 20000) {
          this.source.close(); this.source = null; this.connected = false;
          this.retryAt = Date.now() + 30000;
        }
        this.poll();
      }
      if (!this.source && Date.now() >= this.retryAt) this.connect();
    }, this.fallbackMs);
  }
  connect() {
    if (!this.enabled || this.stopped || this.source || navigator.onLine === false) return;
    this.lastEvent = Date.now();
    const source = this.source = new EventSource('/api/events');
    source.onerror = () => { this.connected = false; };
    source.addEventListener('stream_health', event => {
      try { this.connected = JSON.parse(event.data).available; }
      catch { this.connected = false; }
    });
    source.addEventListener('sync', () => {
      this.lastEvent = Date.now(); this.connected = true;
      this.enqueue('sync', {});
    });
    source.addEventListener('heartbeat', () => { this.lastEvent = Date.now(); });
    for (const topic of Object.keys(this.handlers)) source.addEventListener(topic, event => {
      this.lastEvent = Date.now();
      try { this.enqueue(topic, JSON.parse(event.data)); }
      catch { this.connected = false; }
    });
  }
  enqueue(topic, value) {
    this.pending.set(topic, value);
    this.drain();
  }
  async drain() {
    if (this.draining) return;
    this.draining = true;
    try {
      while (this.pending.size && !this.stopped) {
        const [topic, value] = this.pending.entries().next().value;
        this.pending.delete(topic);
        try { await (topic === 'sync' ? this.synchronize() : topic === 'fallback' ? this.fallback() : this.handlers[topic](value)); }
        catch { this.connected = false; }
      }
    } finally { this.draining = false; }
  }
  async resync() { if (!this.stopped) this.enqueue('sync', {}); }
  poll() { if (!this.stopped && !this.draining) this.enqueue('fallback', {}); }
  close() {
    this.stopped = true; this.connected = false;
    clearInterval(this.timer); this.source?.close(); this.source = null;
    this.pending.clear(); document.removeEventListener('visibilitychange', this.onVisibility);
    window.removeEventListener('offline', this.onOffline);
    window.removeEventListener('online', this.onOnline);
  }
};
