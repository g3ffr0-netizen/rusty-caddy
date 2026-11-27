# Rusty Caddy — Offline GPS PWA

A standalone, zero-dependency, offline-first Progressive Web App (PWA) for using **Rusty Caddy** on your phone out on **Mangrove Mountain** with live GPS (`navigator.geolocation.watchPosition()`).

## Features
- **Live Phone GPS** with 5-fix median smoothing & accuracy badge (`±m`)
- **Offline Service Worker (`sw.js`)** — works with zero mobile reception once loaded
- **Mangrove Mountain 18-hole card** preloaded + **Set Green Pin Here** (saves exact green GPS pins to `localStorage` on your phone)
- **Front / Middle / Back** raw & **Plays-Like** distances (slope elevation, wind, and Mangrove Mountain sloping/tight lies)
- **3-Club Challenge (`3W / 7I / 60°`)** & Full Bag club calls
- **Mark Ball / Measure Shot** to track real carry/total distances on the course

## How to Run / Install on Your Phone
> **Note:** Phone browsers require **HTTPS** (or `localhost`) for live GPS (`geolocation.watchPosition`).
1. **Quick local test on PC:**
   ```powershell
   cd C:\Users\Owner\Desktop\rusty_caddy\pwa
   py -m http.server 8080
   ```
   Then open `http://localhost:8080` in your browser.
2. **Use on your phone over HTTPS:** Push the `pwa/` folder to GitHub Pages (free HTTPS), open the URL on your phone, and tap **Add to Home Screen** (Safari on iPhone or Chrome on Android). Once opened once, it runs 100% offline.
