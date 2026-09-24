def classFactory(iface):
    from .plugin import QgisAgentPlugin
    return QgisAgentPlugin(iface)
