def classFactory(iface):
    from .plugin import GeotaroPlugin
    return GeotaroPlugin(iface)
