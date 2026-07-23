package com.citspray.oms

import android.content.Context

/** Shared config + auth-token storage read by both the WebView and the service. */
object Config {
    const val PREFS = "citspray_prefs"
    const val KEY_TOKEN = "auth_token"

    // How often to request a location fix (milliseconds).
    const val INTERVAL_MS = 15_000L
    const val FASTEST_MS = 10_000L

    fun baseUrl(): String = BuildConfig.OMS_BASE_URL.trimEnd('/')

    fun saveToken(ctx: Context, token: String?) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_TOKEN, token).apply()
    }

    fun token(ctx: Context): String? =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_TOKEN, null)
}
