# Mini NPU Simulator — 어떤 OS(Windows/macOS/Linux)에서도 같은 Python 환경으로 실행하기 위한 이미지
#
# 빌드: docker build -t mini-npu-simulator .
# 실행: docker run --rm -it mini-npu-simulator
# 테스트: docker run --rm --entrypoint python mini-npu-simulator -m unittest -v

# 파이썬 버전을 정확히 고정해 누가 빌드해도 같은 환경(같은 계산 결과)이 되게 한다.
# 최소 지원 버전 확인: docker build --build-arg PYTHON_VERSION=3.8 -t mini-npu-simulator:py3.8 .
ARG PYTHON_VERSION=3.12.16
FROM python:${PYTHON_VERSION}-slim

# PYTHONUNBUFFERED      : 출력을 바로 화면에 보낸다 (입력 프롬프트가 늦게 보이지 않게)
# PYTHONDONTWRITEBYTECODE: __pycache__ 파일을 만들지 않는다
# PYTHONIOENCODING, LANG : 한글·기호(×, ✓) 입출력을 UTF-8로 고정한다
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

WORKDIR /app

# 관리자(root)가 아닌 일반 사용자(uid 1000)로 실행한다.
RUN useradd --create-home --uid 1000 npu

# 프로그램, 미션 데이터, 오류 샘플, 테스트를 복사한다. (외부 라이브러리가 없어서 pip 설치 단계가 없다)
COPY --chown=npu:npu main.py test_main.py data.json ./
COPY --chown=npu:npu samples/ ./samples/

USER npu

# docker stop을 Ctrl+C와 같은 신호(SIGINT)로 보내 안전하게 종료되게 한다.
STOPSIGNAL SIGINT

# docker run 뒤에 붙인 인자는 main.py에 그대로 전달된다. 예: ... mini-npu-simulator samples/data_with_errors.json
ENTRYPOINT ["python", "main.py"]
