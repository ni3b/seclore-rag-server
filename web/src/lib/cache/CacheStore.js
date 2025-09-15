class CacheStore {
  constructor() {
    // Check if we're in a browser environment
    this.isBrowser = typeof window !== 'undefined';
    // Only check for caches if we're in a browser
    this.hasCacheAPI = this.isBrowser && typeof window !== 'undefined' && typeof window.caches !== 'undefined';
    this.memoryCache = new Map();
  }

  async set(key, value) {
    if (this.hasCacheAPI && window && window.caches) {
      try {
        const cache = await window.caches.open('seclore-cache');
        await cache.put(key, new Response(JSON.stringify(value)));
      } catch (error) {
        console.warn('Failed to use Cache API, falling back to memory cache:', error);
        this.memoryCache.set(key, value);
      }
    } else {
      this.memoryCache.set(key, value);
    }
  }

  async get(key) {
    if (this.hasCacheAPI && window && window.caches) {
      try {
        const cache = await window.caches.open('seclore-cache');
        const response = await cache.match(key);
        if (response) {
          return JSON.parse(await response.text());
        }
      } catch (error) {
        console.warn('Failed to use Cache API, falling back to memory cache:', error);
        return this.memoryCache.get(key);
      }
    }
    return this.memoryCache.get(key);
  }

  async setWithTTL(key, value, ttlMs) {
    const item = {
      value,
      expiry: Date.now() + ttlMs
    };
    await this.set(key, item);
  }

  async getWithTTL(key) {
    const item = await this.get(key);
    if (!item) return null;
    
    if (Date.now() > item.expiry) {
      await this.delete(key);
      return null;
    }
    
    return item.value;
  }

  async delete(key) {
    if (this.hasCacheAPI && window && window.caches) {
      try {
        const cache = await window.caches.open('seclore-cache');
        await cache.delete(key);
      } catch (error) {
        console.warn('Failed to use Cache API, falling back to memory cache:', error);
        this.memoryCache.delete(key);
      }
    } else {
      this.memoryCache.delete(key);
    }
  }
}

// Create a singleton instance
const cacheStore = new CacheStore();

// Export the singleton instance
export { cacheStore }; 