"""main.py 단위 테스트 (표준 라이브러리 unittest만 사용).

실행: python -m unittest -v
"""

import contextlib
import io
import unittest
from pathlib import Path

import main

ROOT = Path(__file__).resolve().parent


def quiet(func, *args):
    """함수가 출력하는 내용을 숨기고 반환값만 돌려준다."""
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args)


class GridTest(unittest.TestCase):
    def test_get_set(self):
        grid = main.Grid(3)
        grid.set(1, 2, 7)
        self.assertEqual(grid.get(1, 2), 7.0)
        self.assertEqual(grid.get(0, 0), 0.0)

    def test_from_rows_supports_required_sizes(self):
        for n in (3, 5, 13, 25):
            grid = main.Grid.from_rows([[1] * n for _ in range(n)])
            self.assertEqual(grid.size, n)

    def test_from_rows_rejects_bad_shapes_and_values(self):
        bad_inputs = [
            [[1, 0], [0, 1, 0]],  # 행마다 열 수가 다름
            [[1, 0, 0], [0, 1, 0]],  # 2×3
            [[1, "a"], [0, 1]],  # 문자열
            [[True, 0], [0, 1]],  # bool
            [[float("nan"), 0], [0, 1]],  # NaN
            [],  # 빈 배열
            "not a list",
        ]
        for rows in bad_inputs:
            with self.assertRaises(ValueError, msg=repr(rows)):
                main.Grid.from_rows(rows)

    def test_flatten_is_row_major(self):
        grid = main.Grid.from_rows([[1, 2], [3, 4]])
        self.assertEqual(grid.flatten(), [1.0, 2.0, 3.0, 4.0])


class MacTest(unittest.TestCase):
    CROSS = main.Grid.from_rows([[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    X = main.Grid.from_rows([[1, 0, 1], [0, 1, 0], [1, 0, 1]])

    def test_mission_examples(self):
        self.assertEqual(main.mac_2d(self.CROSS, self.CROSS), 5.0)  # Case 1: 일치
        self.assertEqual(main.mac_2d(self.CROSS, self.X), 1.0)  # Case 2: 불일치

    def test_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            main.mac_2d(self.CROSS, main.generate_cross(5))

    def test_flat_matches_2d_exactly(self):
        for n in (3, 5, 13, 25):
            pattern, filt = main.generate_x(n), main.Grid.from_rows([[0.1] * n for _ in range(n)])
            self.assertEqual(main.mac_2d(pattern, filt), main.mac_flat(pattern.flatten(), filt.flatten()))


class JudgeTest(unittest.TestCase):
    def test_epsilon_tie(self):
        total = 0.0
        for _ in range(9):
            total += 0.1  # 0.8999999999999999
        self.assertNotEqual(total, 0.9)
        self.assertIsNone(main.judge(total, 0.9, "A", "B"))

    def test_clear_winner(self):
        self.assertEqual(main.judge(5.0, 1.0, "A", "B"), "A")
        self.assertEqual(main.judge(1.0, 5.0, "A", "B"), "B")
        self.assertEqual(main.judge(1.0, 1.0 + 1e-6, "A", "B"), "B")  # 차이가 epsilon보다 크면 판정


class LabelTest(unittest.TestCase):
    def test_normalize(self):
        cases = {"+": "Cross", "x": "X", "cross": "Cross", "X": "X", " Cross ": "Cross"}
        for raw, expected in cases.items():
            self.assertEqual(main.normalize_label(raw), expected)

    def test_unknown_label(self):
        for raw in ("o", "", "plus", 1, None):
            with self.assertRaises(ValueError):
                main.normalize_label(raw)


class InputTest(unittest.TestCase):
    def test_parse_row(self):
        self.assertEqual(main.parse_row(" 0  1 0.5 ", 3), ([0.0, 1.0, 0.5], None))
        for line in ("0 1", "0 1 0 1", "0 a 1", "0 nan 1", "0,1,0"):
            values, error = main.parse_row(line, 3)
            self.assertIsNone(values)
            self.assertIn("입력 형식 오류", error)


class GeneratorTest(unittest.TestCase):
    def test_shapes(self):
        for n in (3, 5, 13, 25, 101):
            cross, x = main.generate_cross(n), main.generate_x(n)
            self.assertEqual(main.filter_weight(cross), 2 * n - 1)
            self.assertEqual(main.filter_weight(x), 2 * n - 1)
            self.assertEqual(main.judge(main.mac_2d(cross, cross), main.mac_2d(cross, x), "Cross", "X"), "Cross")
            self.assertEqual(main.judge(main.mac_2d(x, cross), main.mac_2d(x, x), "Cross", "X"), "X")

    def test_rejects_even_or_small(self):
        for n in (1, 2, 4, 0):
            with self.assertRaises(ValueError):
                main.generate_cross(n)


class JsonModeTest(unittest.TestCase):
    def analyze(self, path):
        data, error = main.load_json(path)
        self.assertIsNone(error)
        filters, filter_errors = quiet(main.load_filters, data["filters"])
        return {
            key: main.analyze_case(key, case, filters, filter_errors)
            for key, case in data["patterns"].items()
        }

    def test_data_json_results(self):
        results = self.analyze(ROOT / "data.json")
        self.assertEqual(len(results), 6)
        passed = sorted(k for k, r in results.items() if r["passed"])
        self.assertEqual(passed, ["size_13_1", "size_25_2", "size_5_2"])
        for key in ("size_5_1", "size_13_2", "size_25_1"):
            self.assertEqual(results[key]["decision"], "UNDECIDED")
            self.assertEqual(results[key]["cause"], main.CAUSE_NUMERIC)

    def test_error_samples_fail_per_case(self):
        results = self.analyze(ROOT / "samples" / "data_with_errors.json")
        self.assertTrue(results["size_5_1"]["passed"])
        self.assertTrue(results["size_5_2"]["passed"])  # ' CROSS ' 라벨 정규화
        self.assertIn("크기 불일치", results["size_5_3"]["reason"])
        self.assertEqual(results["size_5_7"]["cause"], main.CAUSE_MISMATCH)
        for key in ("size_5_4", "size_5_5", "size_5_6", "size_7_1", "size_9_1", "size_11_1", "pattern_1"):
            self.assertFalse(results[key]["passed"], key)
            self.assertEqual(results[key]["cause"], main.CAUSE_SCHEMA, key)

    def test_missing_and_broken_files(self):
        _, error = main.load_json(ROOT / "no_such_file.json")
        self.assertIn("찾을 수 없습니다", error)


if __name__ == "__main__":
    unittest.main()
