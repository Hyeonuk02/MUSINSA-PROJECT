"""scoping/ 모듈은 스크립트로도 쓰이므로 패키지가 아니다 — 경로만 더한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
