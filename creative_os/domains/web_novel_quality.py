from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class QualityResult:
    status: str
    issues: tuple[str, ...]
    soft_review_required: bool
    artifact_hash: str

class WebNovelQualityGate:
    @staticmethod
    def evaluate(metadata: dict) -> QualityResult:
        required=("artifact_hash","chapter","choice","progress","conflict","hook")
        issues=["metadata_missing"] if any(k not in metadata for k in required) else []
        for key,code in (("choice","choice_missing"),("progress","progress_missing"),("conflict","conflict_missing"),("hook","hook_missing")):
            if not metadata.get(key): issues.append(code)
        return QualityResult("blocked" if issues else "passed",tuple(issues),True,str(metadata.get("artifact_hash","")))
