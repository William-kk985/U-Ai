// Service Worker for Portable AI Assistant
const CACHE_NAME = 'ai-assistant-v3';
const urlsToCache = [
  '/',
  '/index.html'
];

// 安装阶段：缓存核心资源
self.addEventListener('install', event => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching app shell');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting())
  );
});

// 激活阶段：清理旧缓存
self.addEventListener('activate', event => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 拦截请求：优先使用缓存，否则从网络获取
self.addEventListener('fetch', event => {
  // 只处理 GET 请求
  if (event.request.method !== 'GET') {
    return;
  }

  // API 请求不走缓存，直接访问网络
  if (event.request.url.includes('/api/')) {
    return;
  }

  // CDN 资源不走缓存，直接访问网络（避免缓存外部依赖）
  if (event.request.url.includes('cdn.jsdelivr.net') || 
      event.request.url.includes('cdnjs.cloudflare.com')) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // 缓存命中
        if (response) {
          console.log('[SW] Serving from cache:', event.request.url);
          return response;
        }

        // 缓存未命中，从网络获取
        console.log('[SW] Fetching from network:', event.request.url);
        return fetch(event.request).then(networkResponse => {
          // 检查是否是有效响应
          if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
            return networkResponse;
          }

          // 克隆响应（因为响应流只能读取一次）
          const responseToCache = networkResponse.clone();

          // 添加到缓存
          caches.open(CACHE_NAME)
            .then(cache => {
              cache.put(event.request, responseToCache);
            });

          return networkResponse;
        });
      })
      .catch(error => {
        console.error('[SW] Fetch failed:', error);
        // 如果网络也失败，返回离线页面
        return caches.match('/index.html');
      })
  );
});
