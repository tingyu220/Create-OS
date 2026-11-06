/* 路由在页面生存期固定，所有模块 API 请求绑定同一项目。 */
(() => {
  const match = window.location.pathname.match(/^\/p\/([^/]+)\//);
  if (!match) return;
  const prefix = `/p/${match[1]}`;
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    const globalQuery = typeof input === "string" && /^\/api\/projects(?:\?|\/|$)/.test(input);
    return originalFetch(typeof input === "string" && input.startsWith("/api/") && !globalQuery ? prefix + input : input, options);
  };
  window.writerProjectPrefix = prefix;
})();
