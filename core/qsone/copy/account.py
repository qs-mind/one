"""The QS Mind account: signing in."""

# The QS Mind account.
ACCOUNT_OFFLINE = {
    "en": "Could not reach the QS Mind account. Check the internet connection, then try again.",
    "ar": "مقدرناش نوصل لحساب QS Mind. اتأكد إن النت شغال وجرّب تاني.",
}
ACCOUNT_REFUSED = {
    "en": "The QS Mind account did not accept this sign-in. Sign in again.",
    "ar": "حساب QS Mind ماقبلش الدخول ده. سجّل دخولك تاني.",
}
ACCOUNT_DENIED = {
    "en": "Sign-in was cancelled in the browser. Sign in again when you are ready.",
    "ar": "الدخول اتلغى من المتصفح. سجّل دخولك تاني لما تكون جاهز.",
}
ACCOUNT_EXPIRED = {
    "en": "The sign-in ran out of time. Sign in again.",
    "ar": "وقت الدخول خلص. سجّل دخولك تاني.",
}
ACCOUNT_KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so ONE cannot keep you signed in. "
        "Unlock it or turn it on, then sign in again."
    ),
    "ar": (
        "مخزن المفاتيح في الجهاز مش متاح، فـ ONE مش هيقدر يفضّل دخولك متسجّل. "
        "افتحه أو شغّله وسجّل دخولك تاني."
    ),
}
ACCOUNT_UNAVAILABLE = {  # a build without One's client id at the account (O1)
    "en": "Signing in to the QS Mind account is not ready in this version of ONE yet.",
    "ar": "تسجيل الدخول لحساب QS Mind لسه مش جاهز في النسخة دي من ONE.",
}
ACCOUNT_SIGNED_IN = {  # the loopback page in the browser, after the sign-in
    "en": "Signed in. Go back to ONE.",
    "ar": "دخولك اتسجّل. ارجع لـ ONE.",
}
