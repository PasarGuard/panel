/*
 * PasarGuard plugin UI SDK (served at /api/plugins/sdk.js).
 *
 * The dashboard shows a plugin page in an iframe. The iframe cannot send the Authorization header, so:
 *   1. this script posts {type: "pasarguard:ready"} to the parent window;
 *   2. the dashboard answers with {type: "pasarguard:context", token, theme, lang, cssVars};
 *   3. PasarGuard.ready() resolves with that context and PasarGuard.api() adds the token to requests.
 * Messages are accepted only from the parent window and only from this page's origin (or the origin of the
 * page that embedded it). Theme CSS variables (--background, --foreground, --primary, ...) are copied to
 * this document, values are "H S% L%" triplets: use them as hsl(var(--background)).
 */
(function () {
  "use strict";

  var allowedOrigins = [window.location.origin];
  try {
    if (document.referrer) allowedOrigins.push(new URL(document.referrer).origin);
  } catch (e) {
    /* no referrer */
  }

  var context = null;
  var waiters = [];
  var listeners = [];

  function applyTheme(ctx) {
    var root = document.documentElement;
    var vars = ctx.cssVars || {};
    Object.keys(vars).forEach(function (name) {
      if (name.indexOf("--") === 0) root.style.setProperty(name, String(vars[name]));
    });
    root.classList.toggle("dark", ctx.theme === "dark");
    root.style.colorScheme = ctx.theme === "dark" ? "dark" : "light";
    if (ctx.lang) {
      root.lang = ctx.lang;
      root.dir = ctx.lang === "fa" ? "rtl" : "ltr";
    }
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent || allowedOrigins.indexOf(event.origin) === -1) return;
    var data = event.data;
    if (!data || data.type !== "pasarguard:context" || typeof data.token !== "string") return;
    context = { token: data.token, theme: data.theme, lang: data.lang, cssVars: data.cssVars || {} };
    applyTheme(context);
    waiters.splice(0).forEach(function (resolve) {
      resolve(context);
    });
    listeners.forEach(function (fn) {
      try {
        fn(context);
      } catch (e) {
        console.error(e);
      }
    });
  });

  function ready() {
    if (context) return Promise.resolve(context);
    return new Promise(function (resolve) {
      waiters.push(resolve);
    });
  }

  function api(path, opts) {
    opts = opts || {};
    return ready().then(function (ctx) {
      var headers = new Headers(opts.headers || {});
      headers.set("Authorization", "Bearer " + ctx.token);
      var body = opts.body;
      if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob)) {
        body = JSON.stringify(body);
        if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      }
      var init = Object.assign({}, opts, { headers: headers, body: body });
      return fetch(path, init).then(function (res) {
        var type = res.headers.get("content-type") || "";
        var parsed = type.indexOf("application/json") !== -1 ? res.json() : res.text();
        return parsed.then(function (data) {
          if (!res.ok) {
            var err = new Error((data && data.detail) || res.statusText || "Request failed");
            err.status = res.status;
            err.data = data;
            throw err;
          }
          return data;
        });
      });
    });
  }

  function onContext(fn) {
    listeners.push(fn);
    if (context) fn(context);
  }

  window.PasarGuard = { ready: ready, api: api, onContext: onContext };

  // The parent may not know our origin in advance; the ready message carries no secret.
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({ type: "pasarguard:ready" }, "*");
  }
})();
