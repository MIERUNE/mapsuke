import unittest

from geotaro.core.processing_catalog import processing_catalog


class Algorithm:
    def __init__(self, algorithm_id, name, help_text):
        self.algorithm_id = algorithm_id
        self.name = name
        self.help_text = help_text

    def id(self):
        return self.algorithm_id

    def displayName(self):
        return self.name

    def shortHelpString(self):
        return self.help_text


class Provider:
    def __init__(self, provider_id, algorithms):
        self.provider_id = provider_id
        self.available = algorithms

    def id(self):
        return self.provider_id

    def algorithms(self):
        return self.available


class Registry:
    def __init__(self, providers):
        self.available = providers

    def providers(self):
        return self.available


class ProcessingCatalogTests(unittest.TestCase):
    def test_includes_every_tool_with_short_descriptions(self):
        native = Provider("native", [Algorithm(f"native:tool_{i}", "Generic operation", "Long native help")
                                     for i in range(30)])
        script = Provider("script", [Algorithm("script:local_tool", "Local tool", "<p>Useful for roads.</p>")])
        catalog = processing_catalog(Registry([native, script]))
        self.assertEqual(list(catalog), ["native", "script"])
        self.assertEqual(len(catalog["native"]), 30)
        self.assertEqual(catalog["native"][0], ["tool_0", "Generic operation", "Long native help"])
        self.assertEqual(catalog["script"], [["local_tool", "Local tool", "Useful for roads."]])

    def test_reads_registry_fresh_and_bounds_each_description(self):
        script = Provider("script", [])
        registry = Registry([script])
        self.assertEqual(processing_catalog(registry)["script"], [])
        script.available.append(Algorithm("script:new", "New tool", "A" * 500))
        catalog = processing_catalog(registry)
        self.assertEqual(len(catalog["script"][0][2]), 160)
        native = Provider("native", [Algorithm("native:long", "Long tool", "B" * 500)])
        registry.available.append(native)
        self.assertEqual(len(processing_catalog(registry)["native"][0][2]), 48)

if __name__ == "__main__":
    unittest.main()
