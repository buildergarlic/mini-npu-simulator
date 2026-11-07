"""Mini NPU Simulator.

MAC(Multiply-Accumulate) 연산으로 입력 패턴이 십자가(Cross)인지 X인지 판별한다.

실행 방법:
    python main.py                 # 같은 폴더의 data.json 사용
    python main.py other.json      # 다른 JSON 파일로 모드 2 실행
"""

import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

# =============================================================
# 설정값
# =============================================================
EPSILON = 1e-9  # 두 점수의 차이가 이 값보다 작으면 동점(UNDECIDED)으로 본다.
REPEAT = 10  # 성능 측정 반복 횟수 (평균을 낸다)
BENCH_SIZES = [3, 5, 13, 25]  # 성능 분석 기본 크기
DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data.json"

# 프로그램 내부에서 쓰는 표준 라벨
CROSS = "Cross"
X = "X"
UNDECIDED = "UNDECIDED"
STANDARD_LABELS = (CROSS, X)

# 라벨 정규화 표: (소문자로 바꾼) 원본 표기 → 표준 라벨
#   expected 값: '+' → Cross, 'x' → X
#   filter 키  : 'cross' → Cross, 'x' → X
LABEL_ALIASES = {
    "+": CROSS,
    "cross": CROSS,
    "x": X,
}

FILTER_KEY_RULE = re.compile(r"^size_(\d+)$")  # filters 키: size_{N}
PATTERN_KEY_RULE = re.compile(r"^size_(\d+)_(\d+)$")  # patterns 키: size_{N}_{idx}

# 실패 원인 분류 (데이터/스키마 문제 vs 수치 비교 문제 vs 판정(로직/라벨) 문제)
CAUSE_SCHEMA = "데이터/스키마"
CAUSE_NUMERIC = "수치 비교"
CAUSE_MISMATCH = "판정 불일치"

SECTION_LINE = "#" + "-" * 39


# =============================================================
# 1. 데이터 구조: n×n 2차원 배열
# =============================================================
class Grid:
    """n×n 크기의 2차원 숫자 배열. 패턴과 필터를 모두 이 구조로 저장한다."""

    def __init__(self, size, fill=0.0):
        if not isinstance(size, int) or size < 1:
            raise ValueError("크기는 1 이상의 정수여야 합니다.")
        self.size = size
        self.cells = [[float(fill)] * size for _ in range(size)]

    @classmethod
    def from_rows(cls, rows):
        """2차원 리스트로 Grid를 만든다. 정사각형이 아니거나 숫자가 아닌 값이 있으면 ValueError."""
        shape = describe_shape(rows)
        if shape is None:
            raise ValueError("2차원 배열(리스트의 리스트)이 아닙니다.")
        size = len(rows)
        if size == 0 or shape != f"{size}×{size}":
            raise ValueError(f"정사각형 배열이 아닙니다. (모양: {shape})")

        grid = cls(size)
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                try:
                    grid.set(row_index, col_index, to_number(value))
                except ValueError as error:
                    raise ValueError(f"[{row_index}][{col_index}] 위치: {error}") from None
        return grid

    def get(self, row, col):
        """(row, col) 위치의 값을 읽는다. (0부터 시작)"""
        return self.cells[row][col]

    def set(self, row, col, value):
        """(row, col) 위치에 값을 저장한다. (0부터 시작)"""
        self.cells[row][col] = float(value)

    def shape_text(self):
        return f"{self.size}×{self.size}"

    def flatten(self):
        """(보너스 1) 2차원 배열을 길이 N²인 1차원 리스트로 펼친다. (행 우선: index = row × N + col)"""
        flat = []
        for row in self.cells:
            for value in row:
                flat.append(value)
        return flat

    def show(self, indent="  "):
        """배열을 한 줄에 한 행씩 출력한다."""
        for row in self.cells:
            print(indent + " ".join(f"{value:g}" for value in row))


def describe_shape(rows):
    """2차원 리스트의 모양을 'R×C' 문자열로 반환한다. 2차원 리스트가 아니면 None."""
    if not isinstance(rows, list):
        return None
    widths = []
    for row in rows:
        if not isinstance(row, list):
            return None
        widths.append(len(row))
    if not widths:
        return "0×0"
    if min(widths) == max(widths):
        return f"{len(rows)}×{widths[0]}"
    return f"{len(rows)}×(행마다 {min(widths)}~{max(widths)}열)"


def to_number(value):
    """JSON에서 읽은 값을 float로 바꾼다. bool, 문자열, NaN/무한대는 거부한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"숫자가 아닌 값 {value!r}")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"너무 큰 값 {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"유한한 숫자가 아닌 값 {value!r}")
    return number


# =============================================================
# 2. 패턴 생성기: N×N 십자가 / X
# =============================================================
def check_generator_size(size):
    """생성기는 가운데 칸이 하나인 3 이상의 홀수 크기만 만든다."""
    if not isinstance(size, int) or size < 3 or size % 2 == 0:
        raise ValueError("패턴 크기는 3 이상의 홀수여야 합니다.")


def generate_cross(size):
    """N×N 십자가 패턴: 가운데 행과 가운데 열이 1, 나머지는 0."""
    check_generator_size(size)
    grid = Grid(size)
    middle = size // 2
    for i in range(size):
        grid.set(middle, i, 1.0)
        grid.set(i, middle, 1.0)
    return grid


def generate_x(size):
    """N×N X 패턴: 두 대각선이 1, 나머지는 0."""
    check_generator_size(size)
    grid = Grid(size)
    for i in range(size):
        grid.set(i, i, 1.0)
        grid.set(i, size - 1 - i, 1.0)
    return grid


GENERATORS = {CROSS: generate_cross, X: generate_x}


# =============================================================
# 3. MAC 연산 / 판정 / 라벨 정규화
# =============================================================
def mac_2d(pattern, filt):
    """패턴과 필터를 같은 위치끼리 곱하고(Multiply) 모두 더한다(Accumulate).

    외부 라이브러리 없이 이중 반복문으로 N×N개 칸을 하나씩 계산한다. → 곱셈 N²번
    """
    if pattern.size != filt.size:
        raise ValueError(f"크기 불일치: 패턴 {pattern.shape_text()}, 필터 {filt.shape_text()}")
    a = pattern.cells
    b = filt.cells
    n = pattern.size
    total = 0.0
    for i in range(n):
        for j in range(n):
            total += a[i][j] * b[i][j]
    return total


def mac_flat(pattern_flat, filter_flat):
    """(보너스 1) 1차원(길이 N²) 리스트로 MAC 연산을 한다.

    2차원 접근 a[i][j]는 '행 찾기 → 열 찾기' 두 번의 인덱싱과 이중 반복문이 필요하지만,
    1차원 접근 a[k]는 인덱싱 한 번, 반복문 하나로 끝난다. 더하는 순서(행 우선)는 mac_2d와 같다.
    """
    if len(pattern_flat) != len(filter_flat):
        raise ValueError(f"크기 불일치: 패턴 {len(pattern_flat)}칸, 필터 {len(filter_flat)}칸")
    total = 0.0
    for k in range(len(pattern_flat)):
        total += pattern_flat[k] * filter_flat[k]
    return total


def judge(score_a, score_b, label_a, label_b, epsilon=EPSILON):
    """두 점수를 허용오차(epsilon) 기반으로 비교한다.

    |score_a - score_b| < epsilon 이면 동점으로 보고 None을, 아니면 더 큰 쪽의 라벨을 반환한다.
    부동소수점 계산 오차(예: 0.9 vs 0.8999999999999999)로 승패가 갈리지 않게 하기 위함이다.
    """
    if abs(score_a - score_b) < epsilon:
        return None
    return label_a if score_a > score_b else label_b


def normalize_label(raw):
    """'+', 'x', 'cross' 등 여러 표기를 표준 라벨(Cross / X)로 바꾼다. 알 수 없으면 ValueError."""
    if not isinstance(raw, str):
        raise ValueError(f"라벨이 문자열이 아닙니다: {raw!r}")
    key = raw.strip().lower()
    if key in LABEL_ALIASES:
        return LABEL_ALIASES[key]
    raise ValueError(f"알 수 없는 라벨 {raw!r} (허용: '+', 'x', 'cross')")


def fmt_sci(value):
    """작은 수를 '1.11e-16', '1e-9'처럼 짧게 표시한다."""
    text = f"{value:.3g}"
    return re.sub(r"e([+-])0(\d)", r"e\1\2", text)


EPSILON_TEXT = fmt_sci(EPSILON)


# =============================================================
# 4. 성능 측정
# =============================================================
def measure_ms(func, *args, repeat=REPEAT):
    """func(*args)를 repeat번 호출하고, 1회 평균 시간(ms)을 반환한다.

    측정 구간은 함수 호출 반복문뿐이다. (입력/출력/파일 읽기 시간 제외)
    첫 호출의 일회성 비용이 섞이지 않도록 측정 전에 한 번 미리 호출한다.
    """
    func(*args)  # 워밍업
    start = time.perf_counter()
    for _ in range(repeat):
        func(*args)
    elapsed = time.perf_counter() - start
    return elapsed / repeat * 1000


def benchmark(cases, repeat=REPEAT):
    """cases: [(크기, 패턴 Grid, 필터 Grid, 데이터 출처)] → 크기별 측정 결과 목록."""
    results = []
    for size, pattern, filt, source in cases:
        # 1차원 변환은 측정 구간 밖에서 한 번만 한다. (같은 입력, 같은 반복 횟수로 비교)
        pattern_flat = pattern.flatten()
        filter_flat = filt.flatten()
        results.append({
            "size": size,
            "ops": size * size,
            "ms_2d": measure_ms(mac_2d, pattern, filt, repeat=repeat),
            "ms_1d": measure_ms(mac_flat, pattern_flat, filter_flat, repeat=repeat),
            "same": mac_2d(pattern, filt) == mac_flat(pattern_flat, filter_flat),
            "source": source,
        })
    return results


def print_benchmark(results, repeat=REPEAT):
    """크기 / 평균 시간(ms) / 연산 횟수(N²) / 연산 1회당 시간 표를 출력한다."""
    rows = []
    for item in results:
        per_op_ns = item["ms_2d"] * 1_000_000 / item["ops"]
        rows.append([
            f"{item['size']}×{item['size']}",
            f"{item['ms_2d']:.4f}",
            str(item["ops"]),
            f"{per_op_ns:.1f}",
            item["source"],
        ])
    print_table(
        ["크기", "평균 시간(ms)", "연산 횟수(N²)", "1회당(ns)", "데이터"],
        rows,
        ["left", "right", "right", "right", "left"],
    )
    print(f"※ 크기별 MAC 연산(필터 1개 × 패턴 1개)을 {repeat}회 반복한 평균입니다.")

    print("\n[보너스] 2차원 → 1차원 배열 최적화 비교 (같은 입력, 같은 반복 횟수)")
    rows = []
    for item in results:
        speedup = item["ms_2d"] / item["ms_1d"] if item["ms_1d"] > 0 else float("inf")
        rows.append([
            f"{item['size']}×{item['size']}",
            f"{item['ms_2d']:.4f}",
            f"{item['ms_1d']:.4f}",
            f"{speedup:.2f}x",
            "✓" if item["same"] else "✗",
        ])
    print_table(
        ["크기", "2D 평균(ms)", "1D 평균(ms)", "속도 향상", "점수 일치"],
        rows,
        ["left", "right", "right", "right", "right"],
    )


# =============================================================
# 5. 콘솔 출력 도우미
# =============================================================
def print_section(title):
    print()
    print(SECTION_LINE)
    print(f"# {title}")
    print(SECTION_LINE)


def display_width(text):
    """터미널에서 차지하는 폭. 한글 등 전각 문자는 2칸으로 센다."""
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def pad(text, width, align):
    gap = max(0, width - display_width(text))
    return " " * gap + text if align == "right" else text + " " * gap


def print_table(headers, rows, aligns):
    """한글 폭을 고려해 열을 맞춘 표를 출력한다."""
    widths = []
    for col, header in enumerate(headers):
        cells = [header] + [row[col] for row in rows]
        widths.append(max(display_width(cell) for cell in cells))
    gap = "   "
    print(gap.join(pad(h, w, a) for h, w, a in zip(headers, widths, aligns)).rstrip())
    print("-" * (sum(widths) + len(gap) * (len(widths) - 1)))
    for row in rows:
        print(gap.join(pad(c, w, a) for c, w, a in zip(row, widths, aligns)).rstrip())


# =============================================================
# 6. 모드 1: 사용자 입력 (3×3)
# =============================================================
def parse_row(line, size):
    """한 줄을 숫자 size개로 바꾼다. 반환: (숫자 리스트, None) 또는 (None, 오류 메시지)"""
    guide = f"각 줄에 {size}개의 숫자를 공백으로 구분해 입력하세요."
    parts = line.split()
    if len(parts) != size:
        return None, f"입력 형식 오류: {guide} (입력된 개수: {len(parts)}개)"
    values = []
    for part in parts:
        try:
            number = float(part)
        except ValueError:
            return None, f"입력 형식 오류: '{part}'은(는) 숫자가 아닙니다. {guide}"
        if not math.isfinite(number):
            return None, f"입력 형식 오류: '{part}'은(는) 사용할 수 없는 값입니다. {guide}"
        values.append(number)
    return values, None


def read_matrix(title, size=3):
    """size×size 배열을 한 줄씩(공백 구분) 입력받아 Grid로 반환한다.

    - 열 개수가 다르거나 숫자가 아니면: 안내 후 그 줄을 다시 입력받는다.
    - 줄을 다 채우기 전에 빈 줄(Enter)을 입력하면: 행 수 부족 안내 후 처음부터 다시 입력받는다.
    - (보너스 2) 첫 줄에 cross 또는 x를 입력하면 패턴 생성기로 자동 생성한다.
    """
    print(f"{title} ({size}줄 입력, 공백 구분 / cross 또는 x 입력 시 자동 생성)")
    rows = []
    while len(rows) < size:
        line = input().strip()
        if not rows and line.lower() in ("cross", "x", "+"):
            label = normalize_label(line)
            grid = GENERATORS[label](size)
            print(f"→ 패턴 생성기로 {size}×{size} {label} 생성:")
            grid.show()
            return grid
        if line == "" and not rows:
            print(f"입력 형식 오류: 빈 줄입니다. 각 줄에 {size}개의 숫자를 공백으로 구분해 입력하세요.")
            continue
        if line == "":
            print(f"입력 형식 오류: 행이 {size}개여야 합니다. (현재 {len(rows)}줄) 처음부터 다시 입력하세요.")
            rows = []
            continue
        values, error = parse_row(line, size)
        if error:
            print(error)
            print(f"  → {len(rows) + 1}번째 줄을 다시 입력하세요.")
            continue
        rows.append(values)
    return Grid.from_rows(rows)


def score_pair(pattern, filter_a, filter_b):
    """패턴에 두 필터를 각각 MAC 연산한 점수 (A, B)."""
    return mac_2d(pattern, filter_a), mac_2d(pattern, filter_b)


def run_user_mode():
    """모드 1: 필터 A, B 입력 → 저장 확인 → 패턴 입력 → MAC 연산 → 판정 → 성능 분석(3×3)."""
    size = 3
    print_section("[1] 필터 입력")
    filter_a = read_matrix("필터 A", size)
    print()
    filter_b = read_matrix("필터 B", size)
    print("\n✓ 필터 저장 완료")
    print("필터 A:")
    filter_a.show()
    print("필터 B:")
    filter_b.show()

    print_section("[2] 패턴 입력")
    pattern = read_matrix("패턴", size)

    print_section("[3] MAC 결과")
    score_a, score_b = score_pair(pattern, filter_a, filter_b)
    elapsed = measure_ms(score_pair, pattern, filter_a, filter_b)
    print(f"A 점수: {score_a!r}")
    print(f"B 점수: {score_b!r}")
    print(f"연산 시간(A·B MAC 2회, 평균/{REPEAT}회): {elapsed:.4f} ms")
    decision = judge(score_a, score_b, "A", "B")
    if decision is None:
        diff = abs(score_a - score_b)
        print(f"판정: 판정 불가 (|A-B| = {fmt_sci(diff)} < {EPSILON_TEXT})")
    else:
        print(f"판정: {decision}")

    print_section(f"[4] 성능 분석 ({size}×{size}, 평균/{REPEAT}회)")
    print_benchmark(benchmark([(size, pattern, filter_a, "입력 패턴 × 필터 A")]))


# =============================================================
# 7. 모드 2: data.json 분석
# =============================================================
def load_json(path):
    """JSON 파일을 읽어 (데이터, None) 또는 (None, 오류 메시지)를 반환한다."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return None, f"파일을 찾을 수 없습니다: {path}"
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return None, f"JSON 형식 오류: {error}"
    except OSError as error:
        return None, f"파일을 읽을 수 없습니다: {error}"

    if not isinstance(data, dict):
        return None, "스키마 오류: 최상위 값이 객체({ })가 아닙니다."
    for key in ("filters", "patterns"):
        if not isinstance(data.get(key), dict):
            return None, f"스키마 오류: '{key}' 객체가 없습니다."
    return data, None


def parse_filter_group(size, group):
    """size_N 필터 묶음({'cross': [...], 'x': [...]})을 {Cross: Grid, X: Grid}로 바꾼다."""
    if not isinstance(group, dict):
        raise ValueError("필터 묶음이 객체({ })가 아닙니다.")
    result = {}
    for raw_label, rows in group.items():
        label = normalize_label(raw_label)
        if label in result:
            raise ValueError(f"{label} 필터가 중복되었습니다. ('{raw_label}')")
        try:
            grid = Grid.from_rows(rows)
        except ValueError as error:
            raise ValueError(f"{label} 필터 형식 오류: {error}") from None
        if grid.size != size:
            raise ValueError(f"{label} 필터 크기 {grid.shape_text()}가 키(size_{size})와 다릅니다.")
        result[label] = grid
    missing = [label for label in STANDARD_LABELS if label not in result]
    if missing:
        raise ValueError(f"{', '.join(missing)} 필터가 없습니다.")
    return result


def load_filters(raw_filters):
    """filters 전체를 읽는다. 반환: (filters, errors)

    filters[N] = {"Cross": Grid, "X": Grid}, errors[N] = 그 크기의 필터를 쓸 수 없는 이유
    """
    filters = {}
    errors = {}
    for key, group in raw_filters.items():
        match = FILTER_KEY_RULE.match(str(key))
        if not match:
            print(f"✗ {key}: 키 형식 오류 (size_N 형태여야 합니다)")
            continue
        size = int(match.group(1))
        try:
            filters[size] = parse_filter_group(size, group)
        except ValueError as error:
            errors[size] = str(error)
            print(f"✗ {pad(key, 7, 'left')} 필터 로드 실패: {error}")
            continue
        print(f"✓ {pad(key, 7, 'left')} 필터 로드 완료 ({', '.join(filters[size])})")
    return filters, errors


def new_result(key):
    return {
        "key": key,
        "size": None,
        "pattern": None,
        "cross": None,
        "x": None,
        "decision": None,
        "expected": None,
        "passed": False,
        "cause": None,
        "reason": "",
    }


def fail(result, cause, reason):
    result["passed"] = False
    result["cause"] = cause
    result["reason"] = reason
    return result


def analyze_case(key, case, filters, filter_errors):
    """패턴 1개를 검증하고 판정한다. 어떤 오류가 있어도 예외 대신 FAIL 결과를 반환한다."""
    result = new_result(key)

    match = PATTERN_KEY_RULE.match(str(key))
    if not match:
        return fail(result, CAUSE_SCHEMA, "키 형식 오류: size_{N}_{idx} 형태여야 합니다.")
    size = int(match.group(1))
    result["size"] = size

    if not isinstance(case, dict):
        return fail(result, CAUSE_SCHEMA, "패턴 항목이 객체({ })가 아닙니다.")
    missing_keys = [name for name in ("input", "expected") if name not in case]
    if missing_keys:
        return fail(result, CAUSE_SCHEMA, f"{', '.join(missing_keys)} 항목이 없습니다.")

    try:
        result["expected"] = normalize_label(case["expected"])
    except ValueError as error:
        return fail(result, CAUSE_SCHEMA, f"expected 라벨 오류: {error}")

    if size in filter_errors:
        return fail(result, CAUSE_SCHEMA, f"size_{size} 필터를 쓸 수 없습니다: {filter_errors[size]}")
    if size not in filters:
        return fail(result, CAUSE_SCHEMA, f"size_{size} 필터가 없습니다.")

    shape = describe_shape(case["input"])
    if shape is None:
        return fail(result, CAUSE_SCHEMA, "input이 2차원 배열이 아닙니다.")
    if shape != f"{size}×{size}":
        return fail(result, CAUSE_SCHEMA, f"크기 불일치: 패턴 {shape}, 필터 {size}×{size}")
    try:
        pattern = Grid.from_rows(case["input"])
    except ValueError as error:
        return fail(result, CAUSE_SCHEMA, f"input 형식 오류: {error}")
    result["pattern"] = pattern

    result["cross"] = mac_2d(pattern, filters[size][CROSS])
    result["x"] = mac_2d(pattern, filters[size][X])
    decision = judge(result["cross"], result["x"], CROSS, X)
    result["decision"] = decision if decision else UNDECIDED

    if decision is None:
        diff = abs(result["cross"] - result["x"])
        return fail(result, CAUSE_NUMERIC,
                    f"동점 규칙: |Cross-X| = {fmt_sci(diff)} < {EPSILON_TEXT}")
    if decision != result["expected"]:
        return fail(result, CAUSE_MISMATCH, f"판정 {decision} ≠ expected {result['expected']}")
    result["passed"] = True
    return result


def print_case(result):
    print(f"--- {result['key']} ---")
    if result["cross"] is not None:
        print(f"Cross 점수: {result['cross']!r}")
        print(f"X 점수: {result['x']!r}")
    decision = result["decision"] or "-"
    expected = result["expected"] or "-"
    status = "PASS" if result["passed"] else f"FAIL ({result['reason']})"
    print(f"판정: {decision} | expected: {expected} | {status}")


def build_benchmark_cases(results, filters):
    """성능 분석용 입력: data.json에 있는 크기는 그 데이터를, 없는 크기(3×3 등)는 생성기 패턴을 쓴다."""
    cases = []
    for size in BENCH_SIZES:
        data_case = None
        for result in results:
            if result["pattern"] is not None and result["size"] == size:
                data_case = result
                break
        if data_case is not None:
            cases.append((size, data_case["pattern"], filters[size][CROSS], f"data.json {data_case['key']}"))
        else:
            cases.append((size, generate_cross(size), generate_cross(size), "패턴 생성기 (Cross)"))
    return cases


def print_summary(results):
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    print(f"총 테스트: {len(results)}개")
    print(f"통과: {len(passed)}개")
    print(f"실패: {len(failed)}개")
    if not failed:
        print("\n실패 케이스: 없음")
        return

    print("\n실패 케이스:")
    for result in failed:
        print(f"- {result['key']}: [{result['cause']}] {result['reason']}")

    counts = {}
    for result in failed:
        counts[result["cause"]] = counts.get(result["cause"], 0) + 1
    summary = ", ".join(f"{cause} {count}건" for cause, count in counts.items())
    print(f"\n실패 원인 분류: {summary}")


def run_json_mode(data_path):
    """모드 2: 필터 로드 → 패턴 로드/검증 → MAC·판정·PASS/FAIL → 성능 분석 → 결과 요약."""
    print_section("[1] 필터 로드")
    print(f"파일: {data_path}")
    data, error = load_json(data_path)
    if error:
        print(f"✗ {error}")
        print("data.json을 확인한 뒤 다시 실행하세요.")
        return None
    filters, filter_errors = load_filters(data["filters"])

    print_section("[2] 패턴 분석 (라벨 정규화 적용)")
    results = []
    for key, case in data["patterns"].items():
        result = analyze_case(key, case, filters, filter_errors)
        print_case(result)
        results.append(result)
    if not results:
        print("(분석할 패턴이 없습니다)")

    print_section(f"[3] 성능 분석 (평균/{REPEAT}회)")
    print_benchmark(benchmark(build_benchmark_cases(results, filters)))

    print_section("[4] 결과 요약")
    print_summary(results)
    return results


# =============================================================
# 8. 모드 3: 패턴 생성기 + 크기별 성능 분석 (보너스 2)
# =============================================================
MAX_GENERATOR_SIZE = 201  # 생성기 최대 크기
SHOW_LIMIT = 25  # 이 크기까지만 패턴을 화면에 출력


def read_odd_size():
    """패턴 크기 N(3 이상 MAX_GENERATOR_SIZE 이하 홀수)을 입력받는다."""
    guide = f"3 이상 {MAX_GENERATOR_SIZE} 이하의 홀수를 입력하세요."
    while True:
        raw = input(f"패턴 크기 N (3~{MAX_GENERATOR_SIZE} 홀수): ").strip()
        if raw == "":
            print(f"입력 형식 오류: 빈 입력입니다. {guide}")
            continue
        try:
            size = int(raw)
        except ValueError:
            print(f"입력 형식 오류: '{raw}'은(는) 정수가 아닙니다. {guide}")
            continue
        if size < 3 or size > MAX_GENERATOR_SIZE or size % 2 == 0:
            print(f"입력 형식 오류: 가운데 칸이 하나인 패턴을 만들기 위해 {guide}")
            continue
        return size


def run_generator_mode():
    """모드 3: N 입력 → Cross/X 자동 생성 → 생성 패턴 판정 → 크기별 성능 분석."""
    print_section("[1] 패턴 생성")
    size = read_odd_size()
    patterns = {CROSS: generate_cross(size), X: generate_x(size)}
    for label, grid in patterns.items():
        print(f"\n{label} ({size}×{size}, 값이 1인 칸 {2 * size - 1}개)")
        if size <= SHOW_LIMIT:
            grid.show()
        else:
            print(f"  (N이 {SHOW_LIMIT}보다 커서 출력 생략)")

    print_section("[2] 생성 패턴 판정 (필터 = 생성된 Cross/X)")
    for label, pattern in patterns.items():
        cross_score = mac_2d(pattern, patterns[CROSS])
        x_score = mac_2d(pattern, patterns[X])
        decision = judge(cross_score, x_score, CROSS, X) or UNDECIDED
        status = "PASS" if decision == label else "FAIL"
        print(f"--- 생성 {label} 패턴 ---")
        print(f"Cross 점수: {cross_score!r}")
        print(f"X 점수: {x_score!r}")
        print(f"판정: {decision} | expected: {label} | {status}")

    print_section(f"[3] 성능 분석 (평균/{REPEAT}회)")
    cases = []
    for n in sorted(set(BENCH_SIZES + [size])):
        cases.append((n, generate_cross(n), generate_cross(n), "패턴 생성기 (Cross)"))
    print_benchmark(benchmark(cases))


# =============================================================
# 9. 메뉴 / 실행
# =============================================================
def choose_mode():
    print("\n[모드 선택]")
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    print("3. 패턴 생성기 + 크기별 성능 분석 (보너스)")
    print("0. 종료")
    while True:
        choice = input("선택: ").strip()
        if choice in ("0", "1", "2", "3"):
            return choice
        print("⚠️ 0, 1, 2, 3 중 하나를 입력하세요.")


def main(argv=None):
    argv = sys.argv if argv is None else argv
    data_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DATA_PATH
    print("=== Mini NPU Simulator ===")
    try:
        while True:
            choice = choose_mode()
            if choice == "0":
                break
            if choice == "1":
                run_user_mode()
            elif choice == "2":
                run_json_mode(data_path)
            else:
                run_generator_mode()
    except (KeyboardInterrupt, EOFError):
        print("\n\n입력이 중단되었습니다.")
    print("프로그램을 종료합니다.")


if __name__ == "__main__":
    main()
