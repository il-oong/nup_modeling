"""Gemini API 클라이언트"""

import json
import urllib.request
import urllib.error

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def call_gemini(api_key: str, system_prompt: str, messages: list[dict]) -> str:
    """Gemini API를 호출하여 응답 텍스트를 반환한다.

    Args:
        api_key: Google API 키
        system_prompt: 시스템 프롬프트
        messages: [{"role": "user"|"model", "text": "..."}] 형태의 대화 리스트

    Returns:
        응답 텍스트
    """
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
    url = f"{API_URL}?key={api_key}"

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "(응답 없음)"
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return f"[API 오류 {e.code}] {error_body}"
    except urllib.error.URLError as e:
        return f"[연결 오류] {e.reason}"
    except Exception as e:
        return f"[오류] {e}"
