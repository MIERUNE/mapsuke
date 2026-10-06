"""API keys live encrypted in the QGIS authentication database, never in QSettings."""
from qgis.core import QgsApplication

# The variables each CLI reads for API-key billing; codex exec accepts CODEX_API_KEY.
API_KEY_ENV = {"claude": "ANTHROPIC_API_KEY", "codex": "CODEX_API_KEY"}


def _key(provider):
    return "geotaro/" + provider + "_api_key"


def has_api_key(provider):
    """Check without decrypting, so no master password prompt appears."""
    return bool(QgsApplication.authManager().existsAuthSetting(_key(provider)))


def api_key(provider):
    """Return the stored key, or "" if none is stored or the master password was not entered."""
    manager = QgsApplication.authManager()
    if not manager.existsAuthSetting(_key(provider)):
        return ""
    value = manager.authSetting(_key(provider), "", True)
    return value.strip() if isinstance(value, str) else ""


def store_api_key(provider, value):
    """QGIS asks for its master password first; returns False if it could not store the key."""
    return bool(QgsApplication.authManager().storeAuthSetting(_key(provider), value.strip(), True))


def remove_api_key(provider):
    manager = QgsApplication.authManager()
    return not manager.existsAuthSetting(_key(provider)) or bool(manager.removeAuthSetting(_key(provider)))
