import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import devlog


class DevLogTests(unittest.TestCase):
    def test_count_and_uniqueness(self):
        dates = list(devlog.days_in_range(date(2026, 8, 20), date(2026, 10, 19)))
        self.assertEqual(61, len(dates))
        self.assertEqual(61, len({devlog.selected_topic(d) for d in dates}))

    def test_validate_valid_json(self):
        item = {'titulo': 'Ejercicio con algoritmo de búsqueda binaria',
                'objetivo': 'Aprender a localizar elementos ordenados usando una búsqueda eficaz.',
                'explicacion': 'Los elementos deben estar ordenados. El punto medio reduce el intervalo de búsqueda de forma iterativa. Este método resulta útil con arreglos grandes y ayuda a comprender la complejidad logarítmica.',
                'ejemplo': '```python\nvalores = [1,2,3]\nprint(valores.index(2))\n```\nUna lista simple para ilustrar el objetivo.',
                'ejercicio': 'Implementa una búsqueda binaria real y verifica que encuentre distintos índices.',
                'criterios': 'Comprueba arreglo vacío, primer y último elemento, y elemento ausente.'}
        devlog.validate(item)
        md = devlog.to_markdown(date(2026, 8, 20), item, datetime(2026, 10, 19, tzinfo=timezone.utc), True)
        self.assertIn('Retrospectiva', md)
        self.assertIn('2026-10-19', md)
        with self.assertRaises(ValueError):
            devlog.validate({'titulo': 'mal'})

    def test_real_local_git_commits_with_fake_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.gitignore').write_text('logs/\n')
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True)
            git('init', '-b', 'main')
            git('config', 'user.name', 'DevLog Test')
            git('config', 'user.email', 'devlog@example.com')
            git('add', '.')
            git('commit', '-m', 'inicio')
            item = {'titulo': 'Ejercicio con algoritmo de búsqueda binaria',
                    'objetivo': 'Aprender a localizar elementos ordenados usando una búsqueda eficaz.',
                    'explicacion': 'Los elementos deben estar ordenados. El punto medio reduce el intervalo de búsqueda de forma iterativa. Este método resulta útil con arreglos grandes y ayuda a comprender la complejidad logarítmica.',
                    'ejemplo': '```python\nvalores = [1,2,3]\nprint(valores.index(2))\n```\nUna lista simple para ilustrar el objetivo.',
                    'ejercicio': 'Implementa una búsqueda binaria real y verifica que encuentre distintos índices.',
                    'criterios': 'Comprueba arreglo vacío, primer y último elemento, y elemento ausente.'}
            with patch.object(devlog, 'ROOT', root), patch.object(devlog, 'ENTRIES', root / 'entries'), patch.object(devlog, 'generate', return_value=item):
                devlog.check_repo()
                self.assertTrue(devlog.create(date(2026, 8, 20), retrospective=True, no_push=True))
                self.assertFalse(devlog.create(date(2026, 8, 20), retrospective=True, no_push=True))
                author = git('log', '-1', '--format=%aI').stdout.strip()
                committer = git('log', '-1', '--format=%cI').stdout.strip()
                self.assertTrue(author.startswith('2026-08-20T12:00:00'))
                self.assertNotEqual(author[:10], committer[:10])
                self.assertTrue((root / 'entries/2026/2026-08-20.md').exists())


if __name__ == '__main__':
    unittest.main()
