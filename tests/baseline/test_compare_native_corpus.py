from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import compare_native_corpus as corpus
from compare_graphs import JsonObject


class NativeCorpusTests(unittest.TestCase):
    def test_discovery_excludes_expected_outputs_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'input.f90'
            source.touch()
            (root / 'input.expected.f90').touch()
            self.assertEqual(corpus._discover_sources([root, source]), [source.resolve()])

    def run_checker(self, results, decoded=None):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.f90'
            source.touch()
            with patch.object(corpus, '_run', side_effect=results), \
                    patch.object(corpus, '_load_record_class', return_value=object), \
                    patch.object(corpus, 'decode_stream', return_value=decoded), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                status = corpus.main([
                    '--flang', '/flang', '--json-plugin', '/json.so',
                    '--binary-plugin', '/binary.so', '--protoc', '/protoc', str(source),
                ])
            return status, output.getvalue()

    def test_no_valid_baseline_cannot_pass(self):
        status, output = self.run_checker([subprocess.CompletedProcess([], 1, b'', b'error')])
        self.assertEqual(status, 1)
        self.assertIn('baseline_clean=0', output)
        self.assertIn('baseline_failed=1', output)

    def test_binary_failure_cannot_pass(self):
        baseline = b'{"nodes":[],"comments":[],"enums":{}}'
        status, output = self.run_checker([
            subprocess.CompletedProcess([], 0, baseline, b''),
            subprocess.CompletedProcess([], 1, b'', b'error'),
        ])
        self.assertEqual(status, 1)
        self.assertIn('binary_failed=1', output)

    def test_graph_mismatch_cannot_pass(self):
        baseline = b'{"nodes":[],"comments":[],"enums":{}}'
        decoded = JsonObject([('nodes', []), ('comments', []),
                              ('enums', JsonObject([('Changed', [])]))])
        status, output = self.run_checker([
            subprocess.CompletedProcess([], 0, baseline, b''),
            subprocess.CompletedProcess([], 0, b'wire', b''),
        ], decoded)
        self.assertEqual(status, 1)
        self.assertIn('mismatched=1', output)


if __name__ == '__main__':
    unittest.main()
