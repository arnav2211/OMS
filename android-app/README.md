# CitSpray OMS — Android field app

A native Android app that (1) opens the full OMS in a WebView and (2) runs a
foreground service that reports device location to the backend 24/7 while the
phone is on. Intended for **company-owned** devices given to field executives.

## What it does
- Loads your OMS web app. A `field_executive` login shows only the on-duty
  screen (the backend blocks that role from all order/customer data).
- A foreground service uses Google's Fused Location Provider (GPS + wifi + cell)
  for best accuracy and posts a fix every ~15s to `POST /api/location/ping`.
- Restarts automatically after reboot (`BootReceiver`).
- Android shows its normal permanent "using location" notification and status-bar
  indicator — this is required by the OS and cannot be removed.

## Before you build — set your server URL
Edit `app/build.gradle` and change:
```
buildConfigField "String", "OMS_BASE_URL", "\"https://your-oms-domain.com\""
```
to your actual VPS/OMS URL. If your server is plain HTTP (not HTTPS), it will
work because `usesCleartextTraffic` is enabled, but HTTPS is strongly preferred.

## Build the APK
1. Install **Android Studio** (free).
2. **File → Open** → select this `android-app` folder. Let Gradle sync (it
   downloads the Gradle wrapper and dependencies automatically).
3. **Build → Build Bundle(s)/APK(s) → Build APK(s)**.
4. The APK appears at `app/build/outputs/apk/debug/app-debug.apk`.
5. Send that file over WhatsApp. On the phone, open it and allow
   "Install from unknown sources".

## On the phone (one-time)
Grant when prompted (you said you'll do this):
- Location → **Allow all the time** (this is the background-location grant).
- Notifications → Allow.
- Battery → **Don't optimize / Unrestricted** for CitSpray OMS (critical, or
  Android will suspend the service after a while).
- Then log in once as the field_executive user. The app hands that login to the
  tracking service and starts reporting.

## Watch the data
Log in to the OMS on desktop as **admin → Field Tracking**: live map, the day's
route, distance, and where they stayed longest.

## Notes / limits
- Accuracy is best outdoors with a clear sky; indoors it falls back to wifi/cell.
- If a device has no SIM/data, fixes are dropped (this build posts one fix at a
  time; ask if you want offline buffering + `POST /api/location/batch`, which the
  backend already supports).
- Tune the reporting frequency in `Config.kt` (`INTERVAL_MS`). Faster = more
  battery + data.
