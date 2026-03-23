"""Gemini API 클라이언트"""

import json
import re
import ssl
import urllib.request
import urllib.error

DEFAULT_MODEL = "gemini-3-flash-preview"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# 모델명 허용 패턴 (영숫자, 하이픈, 마침표만)
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9.\-]+$")


def call_gemini(api_key: str, system_prompt: str, messages: list[dict], model: str = DEFAULT_MODEL) -> str:
    """Gemini API를 호출하여 응답 텍스트를 반환한다.

    Args:
        api_key: Google API 키
        system_prompt: 시스템 프롬프트
        messages: [{"role": "user"|"model", "text": "..."}] 형태의 대화 리스트
        model: Gemini 모델명

    Returns:
        응답 텍스트
    """
    # API 키 검증
    if not api_key:
        return "[오류] API 키가 설정되지 않았습니다"

    # 모델명 검증
    if not _MODEL_PATTERN.match(model):
        return f"[오류] 잘못된 모델명: {model}"

    contents = []
    for msg in messages:
        contents.append({
            "role": msg["role"],
            "parts": [{"text": msg["text"]}],
        })

    body = {
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
    }

    data = json.dumps(body).encode("utf-8")
    url = f"{API_BASE}/{model}:generateContent?key={api_key}"

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        ssl_ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=120, context=ssl_ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "(응답 없음)"
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        # API 키가 에러 메시지에 포함되지 않도록 필터링
        safe_body = error_body.replace(api_key, "***") if api_key else error_body
        return f"[API 오류 {e.code}] {safe_body}"
    except urllib.error.URLError as e:
        return f"[연결 오류] {e.reason}"
    except Exception as e:
        error_str = str(e).replace(api_key, "***") if api_key else str(e)
        return f"[오류] {error_str}"
