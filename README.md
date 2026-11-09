# 🧮 Mini NPU Simulator

[![Docker 재현성 검사](https://github.com/buildergarlic/mini-npu-simulator/actions/workflows/docker.yml/badge.svg)](https://github.com/buildergarlic/mini-npu-simulator/actions/workflows/docker.yml)

AI 칩(NPU)이 이미지를 판별할 때 쓰는 **MAC(Multiply-Accumulate) 연산**을 Python으로 직접 구현한 콘솔 프로그램입니다.
숫자 배열로 된 패턴이 **십자가(Cross)** 인지 **X** 인지 판별하고, 패턴 크기(3×3 ~ 25×25 이상)에 따라 연산 시간이 어떻게 늘어나는지 측정합니다.

- 외부 라이브러리 없음 (NumPy 등 미사용, `json`·`time`·`re`·`math`·`unicodedata`·`pathlib` 표준 라이브러리만 사용)
- Python 3.8 이상 (3.8.20, 3.13에서 동작·테스트 확인)
- Docker로 Windows·macOS·Linux 어디서나 같은 환경(Python 3.12.16 고정)에서 실행 가능, push마다 자동 검사 ([9. Docker 실행 가이드](#9-docker-실행-가이드--어떤-개발-환경에서도-똑같이-재현하기))

---

## 1. 실행 방법

두 가지 방법이 있습니다. **PC 환경과 상관없이 똑같이 실행하려면 방법 1(Docker)을 권장합니다.**

### 방법 1. Docker로 실행 (Python 설치 불필요, Windows·macOS·Linux 동일)

```bash
git clone https://github.com/buildergarlic/mini-npu-simulator.git
cd mini-npu-simulator
docker compose build
docker compose run --rm npu
```

- Docker Desktop(또는 Docker Engine)만 설치되어 있으면 됩니다.
- 테스트 실행, 다른 JSON 분석, OS별 명령어, 문제 해결은 [9. Docker 실행 가이드](#9-docker-실행-가이드--어떤-개발-환경에서도-똑같이-재현하기)에 모두 있습니다.

### 방법 2. Python으로 직접 실행

```bash
git clone https://github.com/buildergarlic/mini-npu-simulator.git
cd mini-npu-simulator
python main.py            # macOS/Linux는 python3 main.py
```

실행하면 모드를 고릅니다.

| 번호 | 모드 | 하는 일 |
|:-:|---|---|
| 1 | 사용자 입력 (3x3) | 필터 A·B와 패턴을 한 줄씩 입력 → MAC 점수, 연산 시간, 판정(A/B/판정 불가), 3×3 성능 분석 |
| 2 | data.json 분석 | 필터 로드 → 패턴 검증·판정·PASS/FAIL → 크기별 성능 분석 → 결과 요약 (+ 동점 원인 진단) |
| 3 | 패턴 생성기 (보너스) | 크기 N 입력 → N×N Cross/X 자동 생성 → 판정 → N을 포함한 크기별 성능 분석 |
| 0 | 종료 | |

- **data.json 위치**: `main.py`와 같은 폴더 (어느 폴더에서 실행해도 이 파일을 찾습니다)
- **다른 JSON으로 모드 2 실행**: `python main.py samples/data_with_errors.json` (의도적 오류 데이터로 예외 처리 확인)
- **모드 1 입력 팁**: 각 행을 `0 1 0`처럼 공백으로 구분해 3줄 입력합니다. 첫 줄에 `cross` 또는 `x`를 입력하면 해당 3×3 패턴이 자동으로 채워집니다.
- **테스트 실행**: `python -m unittest -v` (19개)
- `Ctrl+C` / `Ctrl+D`로 언제든 안전하게 종료됩니다.

## 2. 파일 구조

```
mini-npu-simulator/
├── main.py                       # 메인 실행 파일 (전체 구현)
├── data.json                     # 미션 제공 데이터 (원본 그대로)
├── samples/
│   └── data_with_errors.json     # 의도적 오류 케이스 모음 (예외 처리 검증용)
├── test_main.py                  # 단위 테스트 (unittest)
├── Dockerfile                    # Docker 이미지 설계도 (Python 3.12.16 + 코드 + 데이터)
├── compose.yaml                  # Docker Compose 설정 (입력 연결)
├── .dockerignore                 # 이미지에 넣지 않을 파일 목록
├── .github/workflows/
│   └── docker.yml                # push·PR마다 Docker 빌드·테스트를 자동 검사 (GitHub Actions)
└── README.md
```

`main.py` 내부 구성

| 구역 | 주요 요소 | 역할 |
|---|---|---|
| 1. 데이터 구조 | `Grid` | n×n 배열 저장, `get`/`set`, JSON 2차원 리스트 검증, `flatten`(1차원 변환) |
| 2. 패턴 생성기 | `generate_cross`, `generate_x` | N×N 십자가/X 자동 생성 |
| 3. 연산·판정 | `mac_2d`, `mac_flat`, `judge`, `normalize_label` | MAC 연산, epsilon 동점 판정, 라벨 표준화 |
| 4. 성능 측정 | `measure_ms`, `benchmark` | 연산 함수 호출 구간만 10회 반복 측정 |
| 6~8. 모드 | `run_user_mode`, `run_json_mode`, `run_generator_mode` | 각 모드 실행 흐름 |

## 3. 구현 요약

### 3-1. MAC 연산

```python
def mac_2d(pattern, filt):
    total = 0.0
    for i in range(n):
        for j in range(n):
            total += a[i][j] * b[i][j]   # 같은 위치끼리 곱해서(Multiply) 누적(Accumulate)
    return total
```

- 두 배열을 겹쳐 같은 위치의 값끼리 곱하고 모두 더한 값이 **유사도 점수**입니다. 필터와 모양이 겹치는 칸이 많을수록 점수가 커집니다.
- 미션 예시와 같이 3×3 십자가 패턴은 십자가 필터에서 5점, X 필터에서 1점이 나옵니다. (테스트 `test_mission_examples`)
- N×N 배열이면 곱셈과 덧셈을 정확히 **N²번** 합니다.

### 3-2. 라벨 정규화 (표준 라벨: `Cross`, `X`)

data.json은 같은 뜻을 여러 표기로 씁니다. 필터 키는 `cross`/`x`이고, 정답 라벨(expected)은 `+`/`x`입니다.
이대로 비교하면 판정 결과 `cross`와 expected `+`가 **같은 뜻인데도 문자열이 달라 FAIL**이 됩니다.
그래서 읽는 즉시 `normalize_label()`로 표준 라벨로 바꾸고, 출력과 PASS/FAIL 비교는 모두 표준 라벨로만 합니다.

| 원본 표기 | 쓰이는 곳 | 표준 라벨 |
|---|---|---|
| `+` | expected | `Cross` |
| `cross` | filter 키 | `Cross` |
| `x` | expected, filter 키 | `X` |

- 앞뒤 공백과 대소문자는 무시합니다 (`" CROSS "` → `Cross`).
- 표에 없는 라벨(예: `o`)은 **추측하지 않고** 해당 케이스를 FAIL로 처리합니다.
- 라벨 표기는 `main.py`의 `LABEL_ALIASES` 표 한 곳에서만 관리합니다. 새 라벨을 추가하는 단계별 방법은 [8. 새 라벨 추가 절차](#8-새-라벨-추가-절차)에 있습니다.

### 3-3. 점수 비교 정책 (epsilon)

```python
EPSILON = 1e-9
if abs(score_a - score_b) < EPSILON:  → 동점: UNDECIDED (모드 1에서는 '판정 불가')
else:                                  → 점수가 큰 쪽 라벨
```

- `0.1`, `0.3` 같은 소수는 2진수로 정확히 표현할 수 없습니다. 그래서 `0.1`을 9번 더하면 `0.9`가 아니라 `0.8999999999999999`가 됩니다.
- `==`나 `>`로 그대로 비교하면 **수학적으로 같은 두 점수**의 승패가 이 미세한 반올림 오차로 정해집니다. 그래서 차이가 1e-9보다 작으면 동점으로 봅니다.
- UNDECIDED는 Cross도 X도 아니므로 expected와 비교하면 **FAIL**입니다. (근거 없는 판정을 PASS로 세지 않음)

### 3-4. 입력 검증과 스키마 검증

| 모드 | 상황 | 처리 |
|---|---|---|
| 1 | 한 줄의 숫자 개수가 3개가 아님 | `입력 형식 오류: 각 줄에 3개의 숫자를 공백으로 구분해 입력하세요.` → 그 줄 재입력 |
| 1 | 숫자로 바꿀 수 없음 (`a`, `nan`, `inf`) | 안내 → 그 줄 재입력 |
| 1 | 3줄을 채우기 전에 빈 줄(Enter) | `행이 3개여야 합니다` → 처음부터 재입력 |
| 2 | 파일 없음 / JSON 문법 오류 / `filters`·`patterns` 없음 | 안내 메시지 출력 후 메뉴로 복귀 (종료되지 않음) |
| 2 | 필터 묶음 오류 (Cross/X 누락, 정사각형 아님, 키 크기와 다름) | 해당 크기 필터를 `✗`로 표시, 그 크기의 패턴들은 FAIL |
| 2 | 패턴 키가 `size_{N}_{idx}` 형식이 아님 / 해당 N의 필터 없음 | 케이스 FAIL |
| 2 | 패턴 크기와 필터 크기 불일치 (예: 5×4 vs 5×5) | 케이스 FAIL (`크기 불일치: 패턴 5×4, 필터 5×5`) |
| 2 | expected 누락·알 수 없는 라벨, 숫자 아닌 값 | 케이스 FAIL |

패턴 키에서 `N`을 정규식 `^size_(\d+)_(\d+)$`로 꺼낸 뒤 `size_N` 필터를 골라 씁니다.
FAIL에는 원인 분류(**데이터/스키마**, **수치 비교**, **판정 불일치**)를 붙여 결과 요약에서 원인별 건수를 보여 줍니다.

### 3-5. 성능 측정 방법

- `time.perf_counter()`로 **MAC 함수 호출 반복문만** 측정합니다. 입력·출력·파일 읽기와 1차원 변환은 측정 구간 밖입니다.
- 측정 전에 한 번 미리 호출(워밍업)하고, 10회 반복한 총시간을 10으로 나눈 평균(ms)을 씁니다.
- 표에는 크기, 평균 시간(ms), 연산 횟수(N²), 연산 1회당 시간(ns), 사용한 데이터를 표시합니다.
- 3×3은 data.json에 없으므로 패턴 생성기로 만든 Cross 패턴과 필터를 씁니다.

## 4. 보너스 과제

| 보너스 | 구현 내용 |
|---|---|
| 1. 1차원 배열 최적화 | `Grid.flatten()`으로 N×N을 길이 N² 리스트로 바꾼 뒤 `mac_flat()`으로 반복문 하나·인덱싱 한 번으로 계산합니다. 모든 성능 분석 표 아래에 **같은 입력, 같은 반복 횟수**로 측정한 2D/1D 비교표(속도 향상 배수, 점수 일치 여부)를 출력합니다. |
| 2. 패턴 생성기 | `generate_cross(N)`, `generate_x(N)`으로 3 이상의 홀수 N에 대해 패턴을 만듭니다. 모드 3에서 직접 사용하고, 모드 1의 `cross`/`x` 자동 입력과 모드 2의 3×3 성능 측정에도 재활용합니다. |
| (추가) 동점 원인 진단 | 모드 2에서 동점으로 FAIL한 케이스를 '점수 ÷ 필터 가중치 합'으로 다시 비교해 원인을 진단합니다. 참고용이며 공식 PASS/FAIL 집계는 바꾸지 않습니다. |

## 5. 실행 예시

### 모드 1 — 사용자 입력 (실제 실행 화면)

```
=== Mini NPU Simulator ===

[모드 선택]
1. 사용자 입력 (3x3)
2. data.json 분석
3. 패턴 생성기 + 크기별 성능 분석 (보너스)
0. 종료
선택: 1

#---------------------------------------
# [1] 필터 입력
#---------------------------------------
필터 A (3줄 입력, 공백 구분 / cross 또는 x 입력 시 자동 생성)
0 1 0
1 1 1
0 1 0

필터 B (3줄 입력, 공백 구분 / cross 또는 x 입력 시 자동 생성)
1 0 1
0 1 0
1 0 1

✓ 필터 저장 완료
(저장된 필터 A, B 출력 생략)

#---------------------------------------
# [2] 패턴 입력
#---------------------------------------
패턴 (3줄 입력, 공백 구분 / cross 또는 x 입력 시 자동 생성)
1 0 1
0 1 0
1 0 1

#---------------------------------------
# [3] MAC 결과
#---------------------------------------
A 점수: 1.0
B 점수: 5.0
연산 시간(A·B MAC 2회, 평균/10회): 0.0019 ms
판정: B
```

동점 재현: 필터 A를 `0.1 0.1 0.1` 3줄, 필터 B를 `0 0 0` / `0 0.9 0` / `0 0 0`, 패턴을 `1 1 1` 3줄로 입력하면 다음과 같이 나옵니다.

```
A 점수: 0.8999999999999999
B 점수: 0.9
판정: 판정 불가 (|A-B| = 1.11e-16 < 1e-9)
```

잘못된 입력 처리:

```
필터 A (3줄 입력, 공백 구분 / cross 또는 x 입력 시 자동 생성)
0 1
입력 형식 오류: 각 줄에 3개의 숫자를 공백으로 구분해 입력하세요. (입력된 개수: 2개)
  → 1번째 줄을 다시 입력하세요.
0 1 x
입력 형식 오류: 'x'은(는) 숫자가 아닙니다. 각 줄에 3개의 숫자를 공백으로 구분해 입력하세요.
  → 1번째 줄을 다시 입력하세요.
0 1 0

입력 형식 오류: 행이 3개여야 합니다. (현재 1줄) 처음부터 다시 입력하세요.
```

### 모드 2 — data.json 분석 (요약)

```
# [1] 필터 로드
✓ size_5  필터 로드 완료 (Cross, X)
✓ size_13 필터 로드 완료 (Cross, X)
✓ size_25 필터 로드 완료 (Cross, X)

# [2] 패턴 분석 (라벨 정규화 적용)
--- size_5_1 ---
Cross 점수: 0.9
X 점수: 0.8999999999999999
판정: UNDECIDED | expected: X | FAIL (동점 규칙: |Cross-X| = 1.11e-16 < 1e-9)
--- size_5_2 ---
Cross 점수: 8.9
X 점수: 0.1
판정: Cross | expected: Cross | PASS
...

# [4] 결과 요약
총 테스트: 6개
통과: 3개
실패: 3개

실패 케이스:
- size_5_1: [수치 비교] 동점 규칙: |Cross-X| = 1.11e-16 < 1e-9
- size_13_2: [수치 비교] 동점 규칙: |Cross-X| = 2.66e-15 < 1e-9
- size_25_1: [수치 비교] 동점 규칙: |Cross-X| = 1.78e-15 < 1e-9

실패 원인 분류: 수치 비교 3건
```

---

## 6. 결과 리포트

### 6-1. data.json 판정 결과

| 케이스 | 실제 모양 | Cross 점수 | X 점수 | 판정 | expected | 결과 |
|---|---|---|---|---|---|---|
| size_5_1 | X | 0.9 | 0.8999999999999999 | UNDECIDED | X | **FAIL** |
| size_5_2 | 십자가 | 8.9 | 0.1 | Cross | Cross | PASS |
| size_13_1 | X | 0.3 | 14.700000000000008 | X | X | PASS |
| size_13_2 | 십자가 | 7.499999999999997 | 7.5 | UNDECIDED | Cross | **FAIL** |
| size_25_1 | X | 4.9 | 4.899999999999999 | UNDECIDED | X | **FAIL** |
| size_25_2 | 십자가 | 52.9 | 0.1 | Cross | Cross | PASS |

**총 6개 / 통과 3개 / 실패 3개.** 실패 3건은 모두 **수치 비교(동점)** 범주입니다.

### 6-2. 실패 원인 분석

실패 원인을 "데이터/스키마 문제 → 로직 문제 → 수치 비교 문제" 순서로 하나씩 배제하며 진단했습니다.

1. **데이터/스키마 문제가 아니다.** 세 케이스 모두 키 형식(`size_N_idx`), 필터·패턴 크기(N×N 일치), 숫자 값 검증을 통과했습니다. 라벨도 정규화 후 `X`/`Cross`로 정상 인식되었습니다. 정규화 없이 필터 키를 그대로 판정 라벨로 썼다면 판정 `cross` ≠ expected `+`라서, 지금 PASS인 십자가 케이스 2건(size_5_2, size_25_2)까지 FAIL이 되었을 것입니다.
2. **MAC 로직 문제가 아니다.** 미션 예시(5점/1점)를 그대로 재현하고, 같은 로직으로 나머지 3건은 PASS합니다. 1차원 버전(`mac_flat`)과 결과가 비트 단위까지 같다는 것도 테스트로 확인했습니다.
3. **세 케이스는 수학적으로 정확한 동점이다.** 필터 값을 직접 계산하면 다음과 같습니다.
   - size_5_1 (X 패턴, 1인 칸 9개): Cross 필터와 겹치는 칸은 중앙 하나(0.9) → **0.9**. X 필터는 9칸 × 0.1 = **0.9**.
   - size_13_2 (십자가 패턴, 1인 칸 25개): Cross 필터는 25칸 × 0.3 = **7.5**. X 필터와 겹치는 칸은 중앙 하나(7.5) → **7.5**.
   - size_25_1 (X 패턴, 1인 칸 49개): Cross 필터와 겹치는 칸은 중앙 하나(4.9) → **4.9**. X 필터는 49칸 × 0.1 = **4.9**.
4. **화면의 점수가 다른 이유는 부동소수점 오차다.** `0.1`과 `0.3`은 2진수로 정확히 표현되지 않습니다. 그래서 여러 번 더하면 `0.8999999999999999`, `7.499999999999997`처럼 끝자리가 달라지고, 차이는 1e-16 ~ 1e-15 수준입니다.
5. **epsilon이 없었다면 더 나쁜 결과가 된다.** 그냥 `>`로 비교하면 size_5_1은 Cross, size_13_2는 X, size_25_1은 Cross로 판정됩니다. 세 건 모두 expected와 반대입니다. 반올림 오차가 정답을 '우연히' 고르는 상태이고, 계산 순서만 바꿔도 결과가 뒤집힐 수 있습니다.
6. **epsilon 정책은 '판단 근거가 없음'을 솔직하게 드러낸다.** |차이| < 1e-9이므로 UNDECIDED로 판정하고, 규칙대로 FAIL로 집계했습니다. epsilon을 더 작게 바꾸거나 라벨을 고쳐 PASS로 만드는 것은 문제를 숨기는 것이므로 하지 않았습니다.
7. **근본 원인은 필터 가중치 설계(데이터)다.** Cross·X 필터의 가중치 총량이 서로 다릅니다. 예를 들어 size_5에서 Cross 필터 합은 8.9, X 필터 합은 0.9입니다. 그 결과 '틀린 필터가 한 칸에 몰아 둔 큰 가중치'와 '맞는 필터가 모양 전체에 나눠 둔 작은 가중치'의 합이 정확히 같아졌습니다.
8. **진단 실험.** 모드 2의 `[5] 참고` 섹션에서 각 점수를 필터 가중치 합으로 나누어 다시 비교했습니다. size_5_1은 Cross 0.101 vs X 1.000 → X, size_13_2는 Cross 1.000 vs X 0.510 → Cross, size_25_1은 Cross 0.093 vs X 1.000 → X로, **3건 모두 expected와 일치**했습니다. 실패 원인이 판정 로직이 아니라 필터 설계에 있다는 근거입니다.
9. **개선 방안.** 필터를 만들 때 가중치 합(또는 크기)을 같게 정규화하거나, 정규화된 점수로 비교하도록 정책을 바꿀 수 있습니다. 또 필터를 추가할 때 "각 기준 패턴에서 정답 필터 점수가 확실히 더 큰가"를 검사하는 테스트를 함께 두면 이런 데이터를 미리 잡을 수 있습니다.
10. **다른 실패 범주도 검증했다.** `samples/data_with_errors.json`(11케이스)으로 실행하면 크기 불일치, 알 수 없는 라벨, 숫자 아닌 값, 필터 누락 등 8건은 `데이터/스키마`로, 라벨이 실제 모양과 다른 1건은 `판정 불일치`로 분류됩니다. 프로그램은 중단 없이 2 PASS / 9 FAIL을 집계합니다.

> **참고 — epsilon의 한계:** 이 프로젝트는 권장 기준대로 절대 오차(1e-9)를 씁니다. 점수가 매우 커지면(예: 10⁹ 이상) 오차도 커지므로 `math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)` 같은 상대 오차 비교가 더 적합합니다. 이번 데이터는 점수가 최대 53 정도라 누적 오차(1e-15 수준)가 1e-9보다 훨씬 작아 절대 오차로 충분합니다.

### 6-3. 성능 분석과 시간 복잡도 O(N²)

측정 환경은 Linux 클라우드 컨테이너, Python 3.13입니다. 각 크기에서 MAC 연산(필터 1개 × 패턴 1개)을 10회 반복한 평균이며, 101×101은 모드 3에서 측정했습니다.

| 크기 | 평균 시간(ms) | 연산 횟수(N²) | 연산 1회당(ns) |
|---|---:|---:|---:|
| 3×3 | 0.0007 | 9 | 78.9 |
| 5×5 | 0.0013 | 25 | 50.7 |
| 13×13 | 0.0063 | 169 | 37.4 |
| 25×25 | 0.0239 | 625 | 38.3 |
| 101×101 | 0.3596 | 10,201 | 35.3 |

- **연산 횟수 근거:** MAC은 N×N 칸을 한 번씩 방문해 곱하고 더하는 이중 반복문입니다(`for i in range(N): for j in range(N)`). 따라서 연산 횟수는 정확히 N²이고 시간 복잡도는 **O(N²)** 입니다.
- **측정 근거:** 13×13 → 25×25에서 연산 횟수는 625/169 = **3.7배**, 측정 시간은 0.0239/0.0063 = **3.8배** 늘었습니다. 25×25 → 101×101에서도 연산 횟수 16.3배에 시간은 약 15배로, 시간이 N²에 비례해 늘어납니다.
- **연산 1회당 시간이 거의 일정하다:** 13×13 이상에서는 35~38ns로 수렴합니다. "시간 = N² × (1회 비용)" 꼴, 즉 O(N²)라는 뜻입니다.
- **작은 크기에서 1회당 시간이 큰 이유:** 3×3, 5×5에서는 함수 호출, 반복문 준비 같은 **고정 비용**이 9~25번의 곱셈보다 커서 1회당 시간이 부풀려 보입니다. N이 커질수록 고정 비용의 비중이 작아집니다.
- **측정 오차:** 마이크로초 단위를 10회만 측정하므로, 실행할 때마다 다른 프로세스나 CPU 클럭의 영향으로 수십 % 흔들릴 수 있습니다. 개별 값보다 크기에 따른 **증가 추세**를 봐야 합니다.
- **NPU와의 연결:** 25×25 필터 한 번에 625번입니다. 실제 이미지에서는 이 연산을 이미지의 모든 위치, 수천 개의 필터마다 반복하므로 수억 번 이상의 MAC이 필요합니다. 각 칸의 곱셈은 서로 독립적이므로, CPU처럼 한 번에 하나씩(직렬) 하지 않고 수천 개를 동시에(병렬) 계산하는 NPU가 필요합니다.

### 6-4. 보너스 1 — 1차원 배열 최적화 전/후 비교

같은 입력, 같은 반복 횟수(10회)로 측정했습니다.

| 크기 | 2D 평균(ms) | 1D 평균(ms) | 속도 향상 | 점수 일치 |
|---|---:|---:|---:|:-:|
| 3×3 | 0.0007 | 0.0005 | 1.38x | ✓ |
| 5×5 | 0.0013 | 0.0008 | 1.61x | ✓ |
| 13×13 | 0.0063 | 0.0048 | 1.32x | ✓ |
| 25×25 | 0.0239 | 0.0205 | 1.17x | ✓ |
| 101×101 | 0.3596 | 0.3329 | 1.08x | ✓ |

- 2차원 접근 `a[i][j]`는 '행 리스트 찾기 → 값 찾기'로 인덱싱을 두 번 하고 반복문도 이중입니다. 1차원 `a[k]`는 인덱싱 한 번, 반복문 하나로 접근 패턴이 단순해서 **약 1.1~1.6배** 빨라졌습니다.
- N이 커질수록 향상 폭이 줄어듭니다. 큰 배열에서는 곱셈·덧셈 자체(Python float 객체 생성 포함)가 시간의 대부분을 차지해, 인덱싱을 줄여서 아끼는 비율이 작아지기 때문입니다.
- 최적화 후에도 N²칸을 모두 계산하므로 **시간 복잡도는 O(N²) 그대로**이고, 상수 배만 줄어듭니다. 덧셈 순서가 같아 점수는 2D와 완전히 같습니다(부동소수점 결과가 달라지지 않음).

## 7. 테스트

```bash
python -m unittest -v
```

단위 테스트 19개를 둡니다. 데이터 구조, MAC 예시, 1D/2D 일치, epsilon 동점, 라벨 정규화와 라벨 표 규칙, 입력 파싱, 패턴 생성기, data.json 결과(3 PASS/3 FAIL), 오류 샘플의 케이스별 FAIL 분류를 확인하며, Python 3.8과 3.13에서 모두 통과합니다.

## 8. 새 라벨 추가 절차

라벨을 추가하는 경우는 두 가지입니다.

| 경우 | 예 | 바꿀 곳 |
|---|---|---|
| **A. 기존 모양의 새 표기** (가장 흔함) | 데이터가 Cross를 `plus`로, X를 `×`로 적음 | `LABEL_ALIASES` 한 줄 + 테스트 + README |
| **B. 새 모양(새 표준 라벨)** | `T` 모양을 세 번째로 판별 | 상수, 데이터, 판정 로직, 테스트 (8-2 참고) |

### 8-1. 기존 모양의 새 표기 추가 (예: `plus` → Cross, `×` → X)

**1단계 — 코드: `main.py`의 `LABEL_ALIASES`에 한 줄씩 추가합니다.**

```python
LABEL_ALIASES = {
    "+": CROSS,
    "cross": CROSS,
    "x": X,
    "plus": CROSS,  # 새 표기
    "×": X,         # 새 표기 (곱셈 기호)
}
```

- 키는 **소문자, 앞뒤 공백 없이** 적습니다. `normalize_label()`은 입력을 `strip().lower()`로 바꾼 뒤 이 표에서 찾기 때문입니다. `"Plus"`처럼 대문자로 적으면 어떤 입력도 이 키와 같아지지 않습니다.
- 값은 표준 라벨 상수(`CROSS`, `X`) 중 하나만 씁니다.

**2단계 — 다른 코드는 고치지 않습니다.** 아래 기능이 모두 같은 표를 읽으므로 새 표기가 자동으로 반영됩니다.

- `normalize_label()`: data.json의 expected 값과 filter 키 정규화
- 알 수 없는 라벨 오류 메시지의 허용 목록 (`허용: '+', 'cross', 'x', 'plus', '×'`)
- 모드 1의 자동 생성 입력 (첫 줄에 `plus`를 입력하면 3×3 Cross 생성)

**3단계 — 테스트: `test_main.py`의 `LabelTest.test_normalize`에 새 표기를 추가합니다.**

```python
cases = {"+": "Cross", "x": "X", "cross": "Cross", "X": "X", " Cross ": "Cross",
         "plus": "Cross", " PLUS ": "Cross", "×": "X"}  # 새 표기와 대소문자·공백 변형
```

- 새 표기가 `test_unknown_label`의 목록(`"o"`, `"circle"` 등)에 있으면 그 목록에서 뺍니다.

**4단계 — (선택) 실제 데이터로 확인합니다.** 새 표기를 쓰는 JSON을 만들고 모드 2로 실행합니다.

```json
{
  "filters": {"size_5": {"plus": [[...5×5...]], "×": [[...5×5...]]}},
  "patterns": {"size_5_1": {"input": [[...5×5...]], "expected": "plus"}}
}
```

```bash
python main.py new_label.json      # 메뉴에서 2 선택 → "✓ size_5 필터 로드 완료 (Cross, X)", PASS 확인
```

**5단계 — 테스트를 실행합니다.**

```bash
python -m unittest -v
```

아래 두 테스트가 라벨 표의 규칙을 자동으로 검사하므로, 추가를 잘못하면 여기서 실패합니다.

| 테스트 | 검사 내용 | 실패 예 |
|---|---|---|
| `test_alias_table_rules` | 키가 소문자·공백 없음, 값이 표준 라벨, 모든 표준 라벨에 표기가 1개 이상 | `"Plus": CROSS`, `"o": "Circle"` |
| `test_error_message_lists_all_aliases` | 오류 메시지에 모든 표기가 나옴 | 허용 목록을 코드에 직접 적은 경우 |

**6단계 — 문서와 커밋:** README [3-2 라벨 표](#3-2-라벨-정규화-표준-라벨-cross-x)에 새 표기 행을 추가하고 커밋합니다.

```bash
git add main.py test_main.py README.md
git commit -m "Feat: 라벨 표기 'plus', '×' 추가"
```

> 이 절차는 실제로 적용해 확인했습니다. 위 1~5단계를 그대로 따랐을 때 테스트가 모두 통과했고, 새 표기를 쓰는 JSON은 모드 2에서 2 PASS / 0 FAIL, 모드 1에서는 `plus`와 `×` 입력으로 자동 생성이 동작했습니다.

**주의할 점**

- 한 표기를 두 라벨에 연결할 수 없습니다. 파이썬 dict는 키가 하나뿐이라, `"x"`를 아래 줄에 다시 적으면 앞의 연결을 덮어씁니다.
- 한 필터 묶음 안에 같은 라벨의 표기를 두 개 쓰면(예: `"cross"`와 `"plus"`를 함께 씀) `Cross 필터가 중복되었습니다` 오류가 나고, 그 크기의 필터는 쓰지 않습니다.

### 8-2. 새 모양(새 표준 라벨) 추가 (예: `T`)

미션 요구 사항이 Cross·X 두 라벨의 비교이므로, 현재 판정 로직은 라벨이 두 개라고 가정합니다. 세 번째 모양을 추가하려면 아래 위치를 함께 바꿔야 합니다.

| 순서 | 파일 · 위치 | 바꿀 내용 |
|:-:|---|---|
| 1 | `main.py` 상수 | `T = "T"`를 추가하고 `STANDARD_LABELS = (CROSS, X, T)`로 바꿉니다. |
| 2 | `main.py` `LABEL_ALIASES` | `"t": T`처럼 새 라벨의 표기를 추가합니다. (8-1 규칙 동일) |
| 3 | `data.json`, `samples/*.json` | **모든** `size_N` 필터 묶음에 `"t"` 필터를 추가합니다. `parse_filter_group()`은 `STANDARD_LABELS`의 필터가 모두 있어야 로드하므로, 하나라도 빠지면 그 크기의 필터 로드가 실패합니다. |
| 4 | `main.py` `analyze_case()`, `judge()` | 지금은 두 점수만 비교합니다. 표준 라벨마다 점수를 계산하고, 가장 큰 점수의 라벨을 고르되 1위와 2위의 차이가 `EPSILON`보다 작으면 `UNDECIDED`로 판정하도록 일반화합니다. 결과의 `"cross"`/`"x"` 키는 라벨별 점수 딕셔너리로 바꿉니다. |
| 5 | `main.py` `print_case()`, `print_tie_diagnosis()` | 라벨별 점수를 반복문으로 출력하도록 바꿉니다. |
| 6 | `main.py` 생성기 (선택) | `generate_t(size)`를 만들고 `GENERATORS`에 등록하면 모드 1 자동 입력과 모드 3에서 쓸 수 있습니다. 모드 3(`run_generator_mode()`)의 패턴 목록에도 추가합니다. |
| 7 | `test_main.py` | `t` 정규화, T 패턴 판정, 세 라벨 동점 시 UNDECIDED, data.json 결과 기대값을 테스트에 추가·갱신합니다. |
| 8 | `README.md` | 3-2 라벨 표와 6장 결과 리포트를 갱신합니다. |

## 9. Docker 실행 가이드 — 어떤 개발 환경에서도 똑같이 재현하기

### 9-1. 왜 Docker를 쓰나요?

- 이 프로그램을 그냥 실행하려면 PC에 Python 3.8 이상이 있어야 합니다. 그런데 PC마다 OS, Python 버전, 문자 인코딩이 달라서 "내 PC에서는 되는데 다른 PC에서는 안 되는" 일이 생깁니다.
- Docker는 **Linux + Python 3.12.16 + 코드 + data.json**을 하나의 이미지로 묶습니다. 누가 어떤 OS에서 실행해도 컨테이너 안은 똑같은 환경이고, MAC 점수와 PASS/FAIL 결과도 똑같이 나옵니다.
- PC에 Python을 설치하지 않아도 됩니다. Docker만 있으면 됩니다.

| 용어 | 뜻 |
|---|---|
| 이미지 | 실행 환경, 코드, 데이터를 묶은 '설치본'. `Dockerfile`로 만듭니다. |
| 컨테이너 | 이미지를 실행한 것. 한 번 실행 = 컨테이너 하나. 끝나면 지워도 됩니다. |

> 이 프로그램은 파일을 저장하지 않으므로 볼륨이 필요 없습니다. (내 JSON 파일을 분석할 때만 폴더를 연결합니다 → 9-4)

### 9-2. 준비물

| OS | 설치할 것 |
|---|---|
| Windows 10/11 | Docker Desktop (설치 중 WSL 2 사용 선택) |
| macOS (Intel / Apple Silicon) | Docker Desktop |
| Linux | Docker Engine + Docker Compose 플러그인 |

- 설치 안내: https://docs.docker.com/get-started/get-docker/ (Linux: https://docs.docker.com/engine/install/)
- Windows·macOS는 **Docker Desktop을 실행해 둔 상태**에서 명령어를 입력합니다.
- 설치 확인:

```bash
docker --version
docker compose version
```

### 9-3. 실행하기

#### 방법 A. Docker Compose (권장)

```bash
git clone https://github.com/buildergarlic/mini-npu-simulator.git
cd mini-npu-simulator
docker compose build          # 이미지 만들기 (처음 한 번, 코드가 바뀔 때마다)
docker compose run --rm npu   # 프로그램 실행 → 모드 선택
```

| 하고 싶은 일 | 명령 |
|---|---|
| 프로그램 실행 (모드 1·2·3) | `docker compose run --rm npu` |
| 의도적 오류 데이터로 모드 2 | `docker compose run --rm npu samples/data_with_errors.json` |
| 단위 테스트 19개 실행 | `docker compose run --rm --entrypoint python npu -m unittest -v` |
| 컨테이너 안 Python 버전 확인 | `docker compose run --rm --entrypoint python npu --version` |

- `run --rm`: 끝나면 컨테이너를 지웁니다.
- `docker compose up`은 쓰지 않습니다. `up`은 서버를 백그라운드로 띄우는 용도라 키보드 입력을 주고받기 어렵습니다.

#### 방법 B. docker 명령어만 사용

```bash
docker build -t mini-npu-simulator .
docker run --rm -it mini-npu-simulator
```

| 하고 싶은 일 | 명령 |
|---|---|
| 프로그램 실행 | `docker run --rm -it mini-npu-simulator` |
| 의도적 오류 데이터로 모드 2 | `docker run --rm -it mini-npu-simulator samples/data_with_errors.json` |
| 단위 테스트 실행 | `docker run --rm --entrypoint python mini-npu-simulator -m unittest -v` |

| 옵션 | 뜻 |
|---|---|
| `-t mini-npu-simulator` (build) | 만든 이미지에 이름을 붙입니다. |
| `--rm` | 끝나면 컨테이너를 지웁니다. |
| `-it` | `-i` 키보드 입력 + `-t` 터미널 화면. 빠지면 입력할 수 없습니다. |
| 이미지 이름 뒤의 인자 | `main.py`에 그대로 전달됩니다. (Dockerfile의 `ENTRYPOINT ["python", "main.py"]`) |
| `--entrypoint python` | `main.py` 대신 `python`을 실행합니다. 뒤의 `-m unittest -v`가 python에 전달됩니다. |

**종료:** 메뉴 `0`, `Ctrl+C`, 다른 터미널에서 `docker stop` 모두 정상 종료합니다.

### 9-4. 내 JSON 파일을 분석하기

컨테이너는 내 PC의 파일을 바로 볼 수 없습니다. 파일이 있는 폴더를 컨테이너의 `/work`에 **읽기 전용(`:ro`)** 으로 연결하고, 그 경로를 인자로 넘깁니다.

예: 프로젝트 폴더 안 `my-data/my.json`을 분석

| 환경 | 명령 |
|---|---|
| macOS | `docker compose run --rm -v "$(pwd)/my-data:/work:ro" npu /work/my.json` |
| Linux | `docker compose run --rm --user "$(id -u):$(id -g)" -v "$(pwd)/my-data:/work:ro" npu /work/my.json` |
| Windows PowerShell | `docker compose run --rm -v "${PWD}/my-data:/work:ro" npu /work/my.json` |
| Windows 명령 프롬프트(cmd) | `docker compose run --rm -v "%cd%\my-data:/work:ro" npu /work/my.json` |

- 실행 후 모드 `2`를 고르면 `파일: /work/my.json`으로 분석합니다.
- Linux에서 `--user`를 붙이는 이유: 컨테이너 안 사용자(uid 1000)가 내 파일을 읽을 권한이 없으면 `✗ 파일을 읽을 수 없습니다: Permission denied`가 나옵니다. `--user`로 내 계정과 같은 사용자로 실행하면 해결됩니다. (Docker Desktop은 권한을 자동으로 맞춰 줍니다.)
- 라벨 표기(`+`, `x`, `cross`)와 키 규칙(`size_N`, `size_N_idx`)은 data.json과 같아야 합니다. 새 표기를 쓰려면 [8. 새 라벨 추가 절차](#8-새-라벨-추가-절차)를 따른 뒤 `docker compose build`로 이미지를 다시 만듭니다.

### 9-5. 운영체제별 차이

| 환경 | 실행 명령 | 현재 폴더 표기 | 참고 |
|---|---|---|---|
| macOS / Linux 터미널 | `docker compose run --rm npu` | `$(pwd)` | |
| Windows PowerShell / Windows Terminal (권장) | `docker compose run --rm npu` | `${PWD}` | |
| Windows 명령 프롬프트(cmd) | `docker compose run --rm npu` | `%cd%` | 한글·`×`·`✓`가 깨지면 `chcp 65001` 실행 후 다시 시작 |
| Windows Git Bash | `winpty docker compose run --rm npu` | `$(pwd)` | 입력이 안 되면 `winpty`를 앞에 붙입니다. 권장하지 않습니다. |

- Apple Silicon(M1~M4) Mac에서도 그대로 동작합니다. 공식 Python 이미지가 arm64를 지원하고, GitHub Actions에서 arm64 테스트를 매번 실행합니다.
- 성능 분석의 시간(ms)은 PC 성능에 따라 다르지만, **크기가 커질수록 N²에 비례해 늘어나는 경향**은 어떤 환경에서도 같습니다. 컨테이너 안에서 잰 25×25 평균은 약 0.02 ms로, 6-3의 표(컨테이너 밖에서 잼)와 비슷한 수준이었습니다.

### 9-6. 재현 확인 체크리스트

아래 결과가 그대로 나오면 이 프로젝트가 여러분의 PC에서 똑같이 재현된 것입니다.

| 순서 | 명령 / 동작 | 기대 결과 |
|:-:|---|---|
| 1 | `docker compose build` | `Image mini-npu-simulator Built` |
| 2 | `docker compose run --rm --entrypoint python npu --version` | `Python 3.12.16` |
| 3 | `docker compose run --rm --entrypoint python npu -m unittest -v` | `Ran 19 tests ... OK` |
| 4 | `docker compose run --rm npu` → `1` → 필터 A `0 1 0`/`1 1 1`/`0 1 0`, 필터 B `1 0 1`/`0 1 0`/`1 0 1`, 패턴 `1 0 1`/`0 1 0`/`1 0 1` | `A 점수: 1.0`, `B 점수: 5.0`, `판정: B` |
| 5 | `docker compose run --rm npu` → `2` | `총 테스트: 6개`, `통과: 3개`, `실패: 3개` (실패 3건은 모두 `수치 비교` 동점 — 6장 참고) |
| 6 | `docker compose run --rm npu samples/data_with_errors.json` → `2` | `총 테스트: 11개`, `통과: 2개`, `실패: 9개` |
| 7 | 입력 없이 자동 확인: `printf '2\n0\n' \| docker compose run --rm -T npu` (PowerShell: `"2","0" \| docker compose run --rm -T npu`) | 5번과 같은 결과 |

### 9-7. 다른 Python 버전으로 실행해 보기

과제 기준 최소 버전(Python 3.8)에서도 똑같이 동작하는지 확인할 수 있습니다.

```bash
docker build --build-arg PYTHON_VERSION=3.8 -t mini-npu-simulator:py3.8 .
docker run --rm --entrypoint python mini-npu-simulator:py3.8 -m unittest -v
docker run --rm -it mini-npu-simulator:py3.8
```

### 9-8. 함께 작업하기

| 상황 | 할 일 |
|---|---|
| 처음 프로젝트에 참여 | `git clone` → `docker compose build` → `docker compose run --rm npu` |
| 다른 사람이 코드를 바꿔 push함 | `git pull` → `docker compose build` → 실행 (이미지는 빌드할 때의 코드를 담고 있어서, 코드가 바뀌면 **다시 빌드**해야 합니다) |
| 코드를 고치면서 바로 확인 | `docker compose run --rm -v "$(pwd):/app" npu` — 내 폴더의 코드를 컨테이너에 연결해 다시 빌드하지 않고 실행합니다. (Linux는 `--user "$(id -u):$(id -g)"` 추가) |
| 코드를 고친 뒤 테스트 | `docker compose run --rm -v "$(pwd):/app" --entrypoint python npu -m unittest -v` |
| 변경 사항을 올림 (push / Pull Request) | GitHub Actions가 자동으로 Docker 이미지를 빌드하고 테스트합니다. 위 배지와 PR의 체크 표시가 초록색이면 재현성이 유지된 것입니다. |

- 자동 검사(`.github/workflows/docker.yml`) 내용: 이미지 빌드, 단위 테스트 19개, data.json 결과(6개 중 3 PASS/3 FAIL), 오류 샘플(11개 중 9 FAIL), 모드 1 미션 예시, Python 3.8 빌드·테스트, Docker Compose 실행, arm64 빌드·테스트

### 9-9. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `Cannot connect to the Docker daemon` / `error during connect` | Docker가 실행 중이 아님 | Docker Desktop을 실행하고 다시 시도 |
| `the input device is not a TTY` | `-it` 없이 실행했거나 Git Bash 사용 | `-it`를 붙이거나, PowerShell을 쓰거나, 명령 앞에 `winpty` |
| 메뉴는 나오는데 입력이 안 됨 | `-i` 옵션이 빠짐 | `docker run --rm -it ...` |
| 한글·`×`·`✓`가 깨짐 (Windows) | 콘솔 문자 코드가 UTF-8이 아님 | Windows Terminal 사용, 또는 `chcp 65001` 실행 후 다시 시작 |
| 표의 열이 조금 어긋남 | 터미널 글꼴마다 한글·기호 폭이 다름 | 결과에는 영향 없음. D2Coding 등 한글 고정폭 글꼴 권장 |
| `✗ 파일을 찾을 수 없습니다: ...` | 경로를 컨테이너 기준으로 쓰지 않음 | 연결한 경로(`/work/my.json`)로 지정 (9-4) |
| `✗ 파일을 읽을 수 없습니다: Permission denied` | Linux에서 파일 권한이 맞지 않음 | `--user "$(id -u):$(id -g)"` 추가 |
| 코드를 고쳤는데 반영되지 않음 | 이미지를 다시 빌드하지 않음 | `docker compose build` |

### 9-10. Docker 관련 파일 설명

| 파일 | 역할 |
|---|---|
| `Dockerfile` | 이미지 설계도. `python:3.12.16-slim` 위에 `main.py`, `test_main.py`, `data.json`, `samples/`를 복사하고, UTF-8 입출력, 일반 사용자(`npu`, uid 1000)로 실행, `ENTRYPOINT ["python", "main.py"]`(뒤의 인자를 main.py에 전달)를 설정합니다. 외부 라이브러리가 없어 `pip install` 단계가 없습니다. |
| `compose.yaml` | `docker compose` 설정. 입력 연결(`stdin_open`, `tty`)을 적어 두어 짧은 명령으로 실행합니다. |
| `.dockerignore` | `.git`, 문서 등 이미지에 필요 없는 파일을 빼서 빌드를 빠르게 합니다. |
| `.github/workflows/docker.yml` | push·PR마다 GitHub 서버에서 위 체크리스트를 자동으로 실행합니다. |
