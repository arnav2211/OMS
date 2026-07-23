package com.citspray.oms

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Foreground service that streams high-accuracy location fixes to the OMS
 * backend. Runs continuously while the (company) device is powered on.
 */
class LocationService : Service() {

    private lateinit var fused: FusedLocationProviderClient
    private val scope = CoroutineScope(Dispatchers.IO)

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let { postLocation(it.latitude, it.longitude, it.accuracy, it.altitude, it.speed, it.bearing) }
        }
    }

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
        startForegroundNotification()
        requestUpdates()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Restart if the system kills us.
        return START_STICKY
    }

    private fun startForegroundNotification() {
        val channelId = "citspray_location"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(
                channelId, getString(R.string.tracking_channel),
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(channel)
        }
        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.tracking_notice))
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(1, notification)
        }
    }

    private fun requestUpdates() {
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, Config.INTERVAL_MS)
            .setMinUpdateIntervalMillis(Config.FASTEST_MS)
            .setWaitForAccurateLocation(false)
            .build()
        try {
            fused.requestLocationUpdates(request, callback, Looper.getMainLooper())
        } catch (_: SecurityException) {
            stopSelf()
        }
    }

    private fun batteryLevel(): Int {
        val bm = getSystemService(BATTERY_SERVICE) as? BatteryManager
        return bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
    }

    private fun postLocation(
        lat: Double, lng: Double, accuracy: Float, altitude: Double, speed: Float, bearing: Float
    ) {
        val token = Config.token(this) ?: return  // wait until user has logged in
        scope.launch {
            try {
                val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }.format(Date())
                val body = JSONObject().apply {
                    put("lat", lat)
                    put("lng", lng)
                    put("accuracy", accuracy.toDouble())
                    put("altitude", altitude)
                    put("speed", speed.toDouble())
                    put("heading", bearing.toDouble())
                    put("battery", batteryLevel())
                    put("ts", iso)
                }
                val url = URL(Config.baseUrl() + "/api/location/ping")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Authorization", "Bearer $token")
                conn.doOutput = true
                conn.connectTimeout = 15000
                conn.readTimeout = 15000
                val os: OutputStream = conn.outputStream
                os.write(body.toString().toByteArray())
                os.flush()
                os.close()
                conn.responseCode  // fire the request
                conn.disconnect()
            } catch (_: Exception) {
                // network hiccup — next fix will retry
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try { fused.removeLocationUpdates(callback) } catch (_: Exception) {}
        // Ask the system to restart us.
        sendBroadcast(Intent(this, BootReceiver::class.java).apply { action = "com.citspray.oms.RESTART" })
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
