# Cloudflare Setup - FORMYLA

Checklist for connecting domain formyla.com to Cloudflare (Free plan) before routing to Render.

## 1. Add site and switch nameservers

1. Create account at https://dash.cloudflare.com.
2. Add a site -> enter formyla.com -> Free Plan.
3. At your registrar replace NS records with the pair Cloudflare provides (e.g. anna.ns.cloudflare.com, bob.ns.cloudflare.com).
4. Wait 5-30 min for DNS propagation.

## 2. DNS records for Render

In DNS - Records add:

  CNAME @   -> formyla.onrender.com   (Proxied)
  CNAME www -> formyla.onrender.com   (Proxied)

## 3. SSL / TLS

- SSL/TLS - Overview -> Full (strict). Do NOT use Flexible.
- SSL/TLS - Edge Certificates:
  - Always Use HTTPS: ON
  - Automatic HTTPS Rewrites: ON
  - Minimum TLS Version: 1.2
  - HSTS: enable only after Flask sends Strict-Transport-Security (already configured in app.py).

## 4. Speed / Cache

- Speed - Optimization: Auto Minify HTML/CSS/JS, Brotli ON.
- Caching: Browser TTL 4 hours, Caching Level Standard.
- Page Rules (3 free):
  - formyla.com/static/* -> Cache Everything, Edge TTL 1 month
  - formyla.com/api/*    -> Bypass cache
  - formyla.com/login*   -> Bypass cache

## 5. Security

- Security Level: Medium, Bot Fight Mode ON.
- WAF: keep Free-plan defaults.
- Add custom rule: block (http.request.uri.path eq "/debug-sentry").

## 6. Network

- HTTP/3 (QUIC): ON
- 0-RTT: ON
- IP Geolocation: ON
- True-Client-IP Header: ON

Flask reads X-Forwarded-For via ProxyFix(x_for=2): we account for CF -> Render -> Gunicorn chain. The real client IP ends up in request.remote_addr.

## 7. What is already done in code (app.py)

- ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)
- Strict-Transport-Security (HSTS) set in production / over HTTPS
- X-Content-Type-Options: nosniff
- X-Frame-Options: SAMEORIGIN
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
- Vary: Cookie (prevents CDN cross-user cache leaks)
- SESSION_COOKIE_SECURE = True when behind HTTPS / RENDER env

## 8. Smoke check after switch

  curl -I https://formyla.com/health

Expect headers:
  server: cloudflare
  cf-ray: ...
  strict-transport-security: max-age=31536000; includeSubDomains
  x-content-type-options: nosniff
  x-frame-options: SAMEORIGIN

If any header is missing - check the corresponding section above.
