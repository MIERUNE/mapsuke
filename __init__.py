def classFactory(iface):
    from .plugin import MapsukePlugin
    return MapsukePlugin(iface)
