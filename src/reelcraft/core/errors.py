class ReelcraftError(Exception):
    """An expected failure whose message is shown to the user as-is (CLI: exit 1, API: 400)."""


class NotFound(ReelcraftError):
    """API: 404."""
