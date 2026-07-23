package com.citspray.oms

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Loads the full OMS web app in a WebView and keeps the background location
 * service running. When the field executive logs in, the JWT stored in the
 * web app's localStorage is handed to the native service so it can authenticate
 * its location pings.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val handler = Handler(Looper.getMainLooper())

    // The OMS is a single-page app, so login doesn't reload the page. Poll
    // localStorage so the token is captured shortly after the user signs in.
    private val tokenPoll = object : Runnable {
        override fun run() {
            webView.evaluateJavascript(
                "(function(){try{var t=localStorage.getItem('token');" +
                    "if(t&&window.AndroidBridge){AndroidBridge.setAuthToken(t);}}catch(e){}})();",
                null
            )
            handler.postDelayed(this, 10_000)
        }
    }

    private val requestPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
            // After foreground location is granted, ask for background separately.
            maybeRequestBackground()
            startTracking()
        }

    private val requestBackground =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {
            startTracking()
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
        }
        webView.addJavascriptInterface(Bridge(), "AndroidBridge")
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                // Pull the auth token out of the web app after each navigation.
                view?.evaluateJavascript(
                    "(function(){try{var t=localStorage.getItem('token');" +
                        "if(t&&window.AndroidBridge){AndroidBridge.setAuthToken(t);}}catch(e){}})();",
                    null
                )
            }
        }
        webView.loadUrl(Config.baseUrl())

        requestLocationPermissions()
        handler.postDelayed(tokenPoll, 10_000)
    }

    override fun onDestroy() {
        handler.removeCallbacks(tokenPoll)
        super.onDestroy()
    }

    inner class Bridge {
        @JavascriptInterface
        fun setAuthToken(token: String?) {
            if (!token.isNullOrBlank()) {
                Config.saveToken(this@MainActivity, token)
                startTracking()
            }
        }
    }

    private fun hasFineLocation() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun requestLocationPermissions() {
        val perms = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (hasFineLocation()) {
            maybeRequestBackground()
            startTracking()
        } else {
            requestPermissions.launch(perms.toTypedArray())
        }
        requestIgnoreBatteryOptimizations()
    }

    private fun maybeRequestBackground() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && hasFineLocation()) {
            val granted = ContextCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_BACKGROUND_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) requestBackground.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }

    @SuppressLint("BatteryLife")
    private fun requestIgnoreBatteryOptimizations() {
        try {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.data = Uri.parse("package:$packageName")
            startActivity(intent)
        } catch (_: Exception) { /* device may not support it */ }
    }

    private fun startTracking() {
        if (!hasFineLocation()) return
        val intent = Intent(this, LocationService::class.java)
        ContextCompat.startForegroundService(this, intent)
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }
}
