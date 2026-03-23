"""코드 버전 관리"""


class CodeManager:
    """코드 버전을 관리한다."""

    def __init__(self):
        self.versions: list[dict] = []  # [{"version": 1, "code": "...", "status": "success"}]

    def add_version(self, code: str, status: str = "success") -> int:
        ver_num = len(self.versions) + 1
        self.versions.append({
            "version": ver_num,
            "code": code,
            "status": status,
        })
        return ver_num

    def get_version(self, version: int) -> str | None:
        for v in self.versions:
            if v["version"] == version:
                return v["code"]
        return None

    def get_latest(self) -> str | None:
        if self.versions:
            return self.versions[-1]["code"]
        return None

    def get_all(self) -> list[dict]:
        return self.versions
