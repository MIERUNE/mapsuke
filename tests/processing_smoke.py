"""Real QGIS registration, execution and reload; all files stay in a temp profile."""
import os
import importlib.util
from pathlib import Path
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic, sleep

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import Qgis, QgsApplication, QgsProcessing, QgsProcessingException, QgsProcessingAlgorithm
from qgis.analysis import QgsNativeAlgorithms
from qgis.PyQt.QtCore import QCoreApplication
import qgis
sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / 'plugins'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('mapsuke_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
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
    from mapsuke_test.core.processing_provider import AgentProcessingProvider
    import processing
    registry = app.processingRegistry()
    script_provider = ScriptAlgorithmProvider()
    registry.addProvider(script_provider)
    registry.addProvider(QgsNativeAlgorithms())
    agent_provider = AgentProcessingProvider()
    registry.addProvider(agent_provider)
    # The toolbox shows the plugin icon on the provider and each of its algorithms.
    assert not agent_provider.icon().pixmap(16).isNull()
    assert all(alg.icon().cacheKey() == agent_provider.icon().cacheKey() for alg in agent_provider.algorithms())
    assert registry.algorithmById('mapsuke:add_tool').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    assert registry.algorithmById('mapsuke:project_state').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    import json
    state = json.loads(processing.run('mapsuke:project_state', {})['STATE'])
    assert state['layers'] == [] and state['active_layer_id'] is None and 'canvas' not in state

    # view_image queues bounded copies for the bridge; large or noisy images shrink.
    from qgis.PyQt.QtGui import QImage, QColor
    from mapsuke_test.core.processing_provider import pending_images
    assert registry.algorithmById('mapsuke:view_image').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
    small = Path(directory) / 'small.png'
    image = QImage(40, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor('red'))
    assert image.save(str(small))
    copy = processing.run('mapsuke:view_image', {'INPUT': str(small)})['IMAGE']
    assert pending_images == [copy] and copy != str(small) and QImage(copy).size() == image.size()
    noisy = QImage(os.urandom(3000 * 1500 * 4), 3000, 1500, 3000 * 4, QImage.Format.Format_RGB32).copy()
    large = Path(directory) / 'large.png'
    assert noisy.save(str(large))
    copy = processing.run('mapsuke:view_image', {'INPUT': str(large)})['IMAGE']
    assert copy.endswith('.jpg') and QImage(copy).width() == 1568 and QImage(copy).height() == 784
    for _ in range(2):
        processing.run('mapsuke:view_image', {'INPUT': str(small)})
    for path in (str(small), str(Path(directory) / 'missing.png')):
        try:
            processing.run('mapsuke:view_image', {'INPUT': path})
        except QgsProcessingException:
            pass
        else:
            raise AssertionError('Expected rejection: ' + path)
    assert len(pending_images) == 4
    pending_images.clear()
    try:
        processing.run('mapsuke:view_image', {'INPUT': str(Path(directory) / 'not-image.png')})
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
        return processing.run('mapsuke:add_tool', {'NAME': name, 'SOURCE': code})
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
    assert registry.algorithmById('mapsuke:add_tool') is None
    assert processing.run('script:double_value', {'VALUE': 9})['RESULT'] == 18
    registry.removeProvider(script_provider)
    registry.addProvider(AgentProcessingProvider())
    rejected('unavailable', source.replace('double_value', 'unavailable'))
    print('PASS: registration, parameterized execution, updates, failed-update rollback, invalid definitions, persistence and provider lifecycle', flush=True)
    registry.removeProvider(registry.providerById('mapsuke'))

    # Downloads must work through the background bridge with a fresh temporary
    # output, leaving the GUI event loop free to show progress. A timeout made
    # native:filedownloader emit two errors and crash QGIS; it stays rejected.
    from mapsuke_test.core.runtime import BackgroundProcessing
    from qgis.core import QgsNetworkAccessManager
    registry.addProvider(AgentProcessingProvider())
    payload = b'x' * 100_000

    class DownloadHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/missing':
                self.send_error(404)
                return
            if self.path == '/stall':
                sleep(3)
                return
            if self.path in ('/redirect', '/redirect_file'):
                self.send_response(302)
                self.send_header('Location', '/data' if self.path == '/redirect' else 'file:///etc/passwd')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            try:
                for offset in range(0, len(payload), 10_000):
                    self.wfile.write(payload[offset:offset + 10_000])
                    self.wfile.flush()
                    sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    def wait(job, seconds=10):
        saw_progress = False
        deadline = monotonic() + seconds
        while not job.done and monotonic() < deadline:
            QCoreApplication.processEvents()
            saw_progress |= 0 < job.progress() < 100
            sleep(0.01)
        return saw_progress

    server = ThreadingHTTPServer(('127.0.0.1', 0), DownloadHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        assert not registry.algorithmById('mapsuke:download_file').flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
        streamed = Path(directory) / 'streamed.bin'
        job = BackgroundProcessing('mapsuke:download_file', {'URL': url + '/data', 'OUTPUT': str(streamed)})
        # The partial file grows while the transfer runs, so the body is not held in memory.
        partial_sizes = set()
        deadline = monotonic() + 10
        while not job.done and monotonic() < deadline:
            QCoreApplication.processEvents()
            partial_sizes |= {part.stat().st_size for part in Path(directory).glob('.streamed.bin.*.part')}
            sleep(0.01)
        assert job.ok and any(0 < size < len(payload) for size in partial_sizes), (job.summary(), partial_sizes)
        assert streamed.read_bytes() == payload and job.results['BYTES'] == len(payload)

        job = BackgroundProcessing('mapsuke:download_file', {'URL': url + '/redirect', 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
        assert wait(job) and job.done and job.ok, job.summary()
        assert Path(job.results['OUTPUT']).read_bytes() == payload

        job = BackgroundProcessing('mapsuke:download_file', {'URL': url + '/data', 'OUTPUT': str(streamed)})
        while job.progress() <= 0:
            QCoreApplication.processEvents()
            sleep(0.01)
        streamed.write_bytes(b'previous result')
        job.cancel()
        wait(job)
        assert job.done and not job.ok and streamed.read_bytes() == b'previous result', job.summary()
        assert not list(Path(directory).glob('.streamed.bin.*.part'))

        destination = Path(directory) / 'overpass.osm'
        job = BackgroundProcessing('mapsuke:download_file', {'URL': url + '/api', 'DATA': 'data=node;out;',
                                                             'OUTPUT': str(destination)})
        wait(job)
        assert job.ok and destination.read_bytes() == b'data=node;out;', job.summary()

        timeout = QgsNetworkAccessManager.timeout()
        QgsNetworkAccessManager.setTimeout(500)
        try:
            for path in ('/missing', '/stall', '/redirect_file', 'file:///etc/passwd'):
                job = BackgroundProcessing('mapsuke:download_file', {
                    'URL': path if ':' in path else url + path, 'OUTPUT': str(destination)})
                wait(job)
                assert job.done and not job.ok, job.summary()
                assert destination.read_bytes() == b'data=node;out;'
                assert not list(Path(directory).glob('.overpass.osm.*.part'))
            # Late signals from the timed-out request must not touch freed state.
            deadline = monotonic() + 3.5
            while monotonic() < deadline:
                QCoreApplication.processEvents()
                sleep(0.01)
        finally:
            QgsNetworkAccessManager.setTimeout(timeout)
        try:
            BackgroundProcessing('native:filedownloader', {'URL': url + '/data', 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
        except QgsProcessingException as exc:
            assert 'mapsuke:download_file' in str(exc)
        else:
            raise AssertionError('Expected native:filedownloader rejection')
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()
    print('PASS: mapsuke downloader streams in background with progress, POST, redirects, cancel, failures and timeouts', flush=True)

    # A background algorithm can return several layers and reserve others for
    # loading. All must survive the context's cleanup, without duplicate entries.
    from qgis.core import (QgsProcessingContext, QgsProcessingOutputMultipleLayers,
                           QgsProcessingProvider, QgsProcessingUtils, QgsProject,
                           QgsVectorLayer)

    class MultipleLayers(QgsProcessingAlgorithm):
        def name(self): return 'multiple_layers'
        def displayName(self): return 'Multiple layers'
        def createInstance(self): return MultipleLayers()
        def initAlgorithm(self, config=None):
            self.addOutput(QgsProcessingOutputMultipleLayers('LAYERS', 'Layers'))
        def processAlgorithm(self, parameters, context, feedback):
            layers = [QgsVectorLayer('Point?crs=EPSG:4326', name, 'memory')
                      for name in ('reserved output', 'output only', 'reserved only')]
            for layer in layers:
                context.temporaryLayerStore().addMapLayer(layer)
            for layer in (layers[0], layers[2]):
                context.addLayerToLoadOnCompletion(
                    layer.id(), QgsProcessingContext.LayerDetails(
                        layer.name(), context.project(), layer.name(),
                        QgsProcessingUtils.LayerHint.Vector))
            return {'LAYERS': [layers[0].id(), layers[1].id()]}

    class MultipleLayersProvider(QgsProcessingProvider):
        def id(self): return 'smoke'
        def name(self): return 'Smoke'
        def loadAlgorithms(self): self.addAlgorithm(MultipleLayers())

    provider = MultipleLayersProvider()
    registry.addProvider(provider)
    try:
        before = set(QgsProject.instance().mapLayers())
        job = BackgroundProcessing('smoke:multiple_layers', {})
        deadline = monotonic() + 10
        while not job.done and monotonic() < deadline:
            QCoreApplication.processEvents()
            sleep(0.01)
        assert job.done and job.ok, job.summary()
        added = set(QgsProject.instance().mapLayers()) - before
        assert len(added) == 3, job.summary()
        values = job.summary()['results']['LAYERS']
        assert [value['layer'] for value in values] == ['reserved output', 'output only']
        assert {value['id'] for value in values}.issubset(added)
        assert {QgsProject.instance().mapLayer(layer_id).name() for layer_id in added} == {
            'reserved output', 'output only', 'reserved only'}
        for layer_id in added:
            QgsProject.instance().removeMapLayer(layer_id)
    finally:
        registry.removeProvider(provider)
    print('PASS: background multiple outputs and load-on-completion layers', flush=True)
# Avoid macOS QGIS teardown ordering issues at interpreter shutdown.
os._exit(0)
