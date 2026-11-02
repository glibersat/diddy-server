/**
 * Bridge to the Diddy Android companion app, when this page runs inside its WebView.
 *
 * The app exposes `window.DiddyAndroid` (a WebViewCompat web message listener, only for the
 * Diddy origin). We tell it when the user signs in or out so the phone's watch bridge uses
 * the same account. In a normal browser the object is missing and these calls do nothing.
 * The other direction (app -> page) needs no code here: the app writes the stored key into
 * localStorage before the page's scripts run, so the user is signed in on first load.
 */

interface NativeBridge {
  postMessage(message: string): void
}

function bridge(): NativeBridge | undefined {
  return (window as unknown as { DiddyAndroid?: NativeBridge }).DiddyAndroid
}

export function inAndroidApp(): boolean {
  return bridge() !== undefined
}

/** Call only with a key the server accepted. */
export function announceSignIn(apiKey: string) {
  bridge()?.postMessage(JSON.stringify({ type: 'signed-in', apiKey }))
}

export function announceSignOut() {
  bridge()?.postMessage(JSON.stringify({ type: 'signed-out' }))
}
