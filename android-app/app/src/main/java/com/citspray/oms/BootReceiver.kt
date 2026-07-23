package com.citspray.oms

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/** Restarts the location service after device reboot or if the service is killed. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        // Only start if a field executive has logged in at least once.
        if (Config.token(context).isNullOrBlank()) return
        val svc = Intent(context, LocationService::class.java)
        ContextCompat.startForegroundService(context, svc)
    }
}
