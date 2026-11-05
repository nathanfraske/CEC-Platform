"""Package surfaces and semantic constructors remain board-independent."""

import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cec_pipeline import geometry
from cec_pipeline.cells import normalize_poses
from cec_pipeline.power import symmetric_grid
from cec_repository_audit import ignored_python_dependencies


class PackageTests(unittest.TestCase):
    def test_grid_is_centered_under_odd_and_even_dimensions(self):
        for rows in (1, 2, 3, 4):
            for columns in (1, 2, 3, 4):
                center = [1234567, -7654321]
                points = symmetric_grid(
                    center_nm=center, rows=rows, columns=columns, pitch_nm=1200000
                )
                self.assertEqual(
                    [sum(p[k] for p in points) // len(points) for k in (0, 1)], center
                )
                reflected = {
                    tuple(2 * center[k] - p[k] for k in (0, 1)) for p in points
                }
                self.assertEqual(reflected, set(map(tuple, points)))

    def test_grid_has_no_rounding_hidden_in_an_asymmetric_array(self):
        with self.assertRaisesRegex(ValueError, "exact_integer_center"):
            symmetric_grid(center_nm=[0, 0], rows=2, columns=2, pitch_nm=1000001)
        with self.assertRaises(ValueError):
            symmetric_grid(center_nm=[0, 0], rows=True, columns=2, pitch_nm=1000000)

    def test_cell_poses_are_explicit_cardinal_and_preserve_reference_identity(self):
        self.assertEqual(
            normalize_poses(
                [
                    dict(
                        reference="ANY_OWNER",
                        at_nm=[1234567, 2345678],
                        rotation_deg=450,
                    )
                ]
            ),
            {"ANY_OWNER": [1.234567, 2.345678, 90]},
        )
        for value in (
            [dict(reference="A", at_nm=[0, 0], rotation_deg=45)],
            [dict(reference="A", at_nm=[0.1, 0], rotation_deg=0)],
        ):
            with self.assertRaises(ValueError):
                normalize_poses(value)

    def test_geometry_has_no_native_or_repository_side_effect_dependencies(self):
        tree = ast.parse(Path(geometry.__file__).read_text())
        imports = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        imports |= {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertLessEqual(imports, {"collections", "math"})

    def test_preserved_helper_inventory_and_literal_siblings_are_closed(self):
        """Moving imports out of ignored output must retain adjacent drivers."""
        folder = Path(__file__).resolve().parents[1] / "experiments/legacy_2026"
        origins = json.loads((folder / "source-origins.json").read_text())["files"]
        self.assertEqual(set(origins), {p.stem for p in folder.glob("*.py")})
        for name, record in origins.items():
            source = folder / (name + ".py")
            if not record["changes"]:
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    record["original_sha256"],
                    name,
                )
            for node in ast.walk(ast.parse(source.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "with_name"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value.endswith(".py")
                ):
                    self.assertTrue((folder / node.args[0].value).is_file(), name)

    def test_dependency_audit_finds_hyphenated_adjacent_driver(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "build").mkdir()
            (root / "tests/test_sample.py").write_text("import sample_operator\n")
            (root / "build/sample_operator.py").write_text(
                "from pathlib import Path\n"
                "DRIVER = Path(__file__).with_name('adjacent-driver.py')\n"
            )
            (root / "build/adjacent-driver.py").write_text("# preserved driver\n")
            inventory = ignored_python_dependencies(root)
            self.assertEqual(set(inventory), {"sample_operator", "adjacent-driver"})
            self.assertTrue(all(row["unresolved"] for row in inventory.values()))


if __name__ == "__main__":
    unittest.main()
