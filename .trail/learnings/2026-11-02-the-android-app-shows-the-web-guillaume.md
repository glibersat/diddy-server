---
title: The Android app shows the web app in a WebView and shares sign-in with it both ways
author: Guillaume
date: 2026-11-02
branch: main
cost: { minutes: 1, tokens: 1750 }
id: l-9cdcc5d4
scope: repo
status: active
src: agent
---

## Decided
- The Android companion is a full-screen WebView of the Diddy web app (https://diddy.iocraft.org), with only a watch status pill and a "Phone and watch" sheet native. Signing in happens in the web app, so the native UI has no server URL / API key fields.
- App -> page: a WebViewCompat document-start script writes the stored API key into localStorage ('diddy_api_key'), so the router guard sees it before the first route and the user lands on Today. Old WebViews without that feature: set it after load and reload once.
- Page -> app: the web app posts {type:'signed-in', apiKey} / {type:'signed-out'} to window.DiddyAndroid (a web message listener). Both channels are locked to the Diddy origin so other sites never see the key.
- Signing out in the web app also disconnects the phone's watch bridge from the server. Otherwise the next page load would sign the user straight back in.
- The web app is a PWA with a hand-written service worker (no vite-plugin-pwa).

## Watch out
- Only announce sign-in after the server accepted the key (LoginView sets the key before checking it).
- The service worker answers every page load with '/' (index.html). Keep it that way: nginx proxies /schedules, /notifications etc. to the API, so a refresh on those paths would otherwise get JSON. Never let it cache API responses.
- Routine rows put the time above the text below the sm breakpoint; side by side, the text was squeezed to a word per line at 360px. Leaflet maps need an isolated stacking context (relative z-0 isolate) or they cover the phone nav bar.

In the code: frontend/src/native.ts, frontend/public/sw.js, frontend/public/manifest.webmanifest, companion-android ui/MainActivity.kt (installSignInScript, onPageMessage), BridgeService.storedApiKeyFor.
