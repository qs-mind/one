"""The engineer's profile (Phase 1): what PUT /engineer/profile refuses."""

# A name longer than 80 characters, a position or company longer than 120, a line break, or a
# currency that is not three capitals. The refusal names the field and gives an example that fits.
PROFILE_BAD_VALUE = {
    "en": "This is too long, or not in the form ONE keeps. The example shows what fits.",
    "ar": "ده طويل أوي، أو مش بالشكل اللي ONE بيحفظه. المثال بيوضح اللي ينفع.",
}
