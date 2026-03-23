"""exec() 안전 실행 유틸리티

보안 검사 로직은 agents/tester.py의 check_code_safety()로 통합됨.
이 모듈은 추가적인 유틸리티를 위해 유지.
"""

from ..agents.tester import BLOCKED_MODULES, SAFE_BUILTINS, TesterAgent

# 통합된 안전성 검사 함수를 re-export
check_code_safety = TesterAgent.check_code_safety
