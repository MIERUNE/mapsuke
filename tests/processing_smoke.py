"""Real QGIS registration, execution and reload; all files stay in a temp profile."""
import os
import importlib.util
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import Qgis, QgsApplication, QgsProcessingException, QgsProcessingAlgorithm
import qgis
sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / 'plugins'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('qgis_agent_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)

with tempfile.TemporaryDirectory() as directory:
    app = QgsApplication([], False, directory)
    app.initQgis()
    sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / 'python/plugins'))
    from processing.script import ScriptUtils
    # Never read or write the user's existing scripts in this test.
    ScriptUtils.defaultScriptsFolder = lambda: directory
    ScriptUtils.scriptsFolders = lambda: [directory]
    from processing.script.ScriptAlgorithmProvider import ScriptAlgorithmProvider
    from qgis_agent_test.processing_provider import AgentProcessingProvider
    import processing
    registry = app.processingRegistry()
    script_provider = ScriptAlgorithmProvider()
    registry.addProvider(script_provider)
    agent_provider = AgentProcessingProvider()
    registry.addProvider(agent_provider)
    assert registry.algorithmById('qgis_agent:add_tool').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    assert registry.algorithmById('qgis_agent:project_state').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    import json
    state = json.loads(processing.run('qgis_agent:project_state', {})['STATE'])
    assert state['layers'] == [] and state['active_layer_id'] is None and 'canvas' not in state

    # view_image queues bounded copies for the bridge; large or noisy images shrink.
    from qgis.PyQt.QtGui import QImage, QColor
    from qgis_agent_test.processing_provider import pending_images
    assert registry.algorithmById('qgis_agent:view_image').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    small = Path(directory) / 'small.png'
    image = QImage(40, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor('red'))
    assert image.save(str(small))
    copy = processing.run('qgis_agent:view_image', {'INPUT': str(small)})['IMAGE']
    assert pending_images == [copy] and copy != str(small) and QImage(copy).size() == image.size()
    noisy = QImage(os.urandom(3000 * 1500 * 4), 3000, 1500, 3000 * 4, QImage.Format.Format_RGB32).copy()
    large = Path(directory) / 'large.png'
    assert noisy.save(str(large))
    copy = processing.run('qgis_agent:view_image', {'INPUT': str(large)})['IMAGE']
    assert copy.endswith('.jpg') and QImage(copy).width() == 1568 and QImage(copy).height() == 784
    for _ in range(2):
        processing.run('qgis_agent:view_image', {'INPUT': str(small)})
    for path in (str(small), str(Path(directory) / 'missing.png')):
        try:
            processing.run('qgis_agent:view_image', {'INPUT': path})
        except QgsProcessingException:
            pass
        else:
            raise AssertionError('Expected rejection: ' + path)
    assert len(pending_images) == 4
    pending_images.clear()
    try:
        processing.run('qgis_agent:view_image', {'INPUT': str(Path(directory) / 'not-image.png')})
    except QgsProcessingException:
        pass
    else:
        raise AssertionError('Expected rejection of an unreadable image')
    assert pending_images == []

    source = '''from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterNumber,
                       QgsProcessingOutputNumber)
class DoubleValue(QgsProcessingAlgorithm):
    def name(self): return 'double_value'
    def displayName(self): return '値を2倍にする'
    def shortHelpString(self): return '入力値VALUEを2倍にしてRESULTに返します。'
    def createInstance(self): return DoubleValue()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterNumber('VALUE', '入力値'))
        self.addOutput(QgsProcessingOutputNumber('RESULT', '計算結果'))
    def processAlgorithm(self, parameters, context, feedback):
        return {'RESULT': self.parameterAsDouble(parameters, 'VALUE', context) * 2}
'''
    def register(name, code):
        return processing.run('qgis_agent:add_tool', {'NAME': name, 'SOURCE': code})
    def rejected(name, code):
        before = sorted(Path(directory).glob('*.py'))
        try:
            register(name, code)
        except QgsProcessingException:
            pass
        else:
            raise AssertionError('Expected rejection: ' + name)
        assert sorted(Path(directory).glob('*.py')) == before

    result = register('double_value', source)
    assert result['ALGORITHM_ID'] == 'script:double_value'
    assert Path(result['FILE']).read_text() == source
    assert processing.run(result['ALGORITHM_ID'], {'VALUE': 21})['RESULT'] == 42
    assert ScriptUtils.findAlgorithmSource('double_value') == result['FILE']
    updated = source.replace('* 2', '* 3')
    assert register('double_value', updated) == result
    assert Path(result['FILE']).read_text() == updated
    assert processing.run(result['ALGORITHM_ID'], {'VALUE': 21})['RESULT'] == 63
    rejected('double_value', 'invalid syntax :')
    rejected('double_value', updated.replace("self.addOutput(QgsProcessingOutputNumber('RESULT', '計算結果'))", "raise ValueError('bad update')"))
    assert Path(result['FILE']).read_text() == updated
    assert processing.run(result['ALGORITHM_ID'], {'VALUE': 21})['RESULT'] == 63

    # Roll back both the saved definition and registry when refresh fails.
    refresh = script_provider.refreshAlgorithms
    attempts = []
    def fail_once():
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError('simulated registration failure')
        refresh()
    script_provider.refreshAlgorithms = fail_once
    try:
        rejected('double_value', source)
    finally:
        script_provider.refreshAlgorithms = refresh
    assert Path(result['FILE']).read_text() == updated
    assert processing.run(result['ALGORITHM_ID'], {'VALUE': 21})['RESULT'] == 63

    # Existing tools may have filenames different from their algorithm name.
    renamed = Path(directory) / 'different_filename.py'
    Path(result['FILE']).rename(renamed)
    script_provider.refreshAlgorithms()
    result = register('double_value', source)
    assert Path(result['FILE']).resolve() == renamed.resolve()
    assert not (Path(directory) / 'double_value.py').exists()
    assert processing.run(result['ALGORITHM_ID'], {'VALUE': 21})['RESULT'] == 42
    assert len([a for a in script_provider.algorithms() if a.name() == 'double_value']) == 1
    rejected('../outside', source)
    rejected('broken', 'not python :')
    rejected('missing', 'x = 1')
    rejected('wrong_name', source)
    rejected('no_help', source.replace('double_value', 'no_help').replace("return '入力値VALUEを2倍にしてRESULTに返します。'", "return ''"))
    rejected('bad_init', source.replace('double_value', 'bad_init').replace("self.addOutput(QgsProcessingOutputNumber('RESULT', '計算結果'))", "raise ValueError('bad initialization')"))
    rejected('exit', 'raise SystemExit(1)')
    existing = Path(directory) / 'existing.py'
    existing.write_text('# preserved')
    register('existing', source.replace('double_value', 'existing'))
    assert processing.run('script:existing', {'VALUE': 5})['RESULT'] == 10

    # A new provider reloads from disk without the agent plugin present.
    registry.removeProvider(agent_provider)
    registry.removeProvider(script_provider)
    script_provider = ScriptAlgorithmProvider()
    registry.addProvider(script_provider)
    assert registry.algorithmById('qgis_agent:add_tool') is None
    assert processing.run('script:double_value', {'VALUE': 9})['RESULT'] == 18
    registry.removeProvider(script_provider)
    registry.addProvider(AgentProcessingProvider())
    rejected('unavailable', source.replace('double_value', 'unavailable'))
    print('PASS: registration, parameterized execution, updates, failed-update rollback, invalid definitions, persistence and provider lifecycle', flush=True)
    registry.removeProvider(registry.providerById('qgis_agent'))
# Avoid macOS QGIS teardown ordering issues at interpreter shutdown.
os._exit(0)
