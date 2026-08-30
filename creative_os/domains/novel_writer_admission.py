from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.writer_admission import (
    PreAdmissionRequest,
    WriterAdmissionError,
    WriterAdmissionService,
)


class NovelWriterAdmissionError(ValueError):
    """小说领域统一的 Writer 准入失败。"""


@dataclass(frozen=True, slots=True)
class NovelAdmissionRequest:
    contract_id: str
    context_fingerprint: str
    run_id: str


class NovelWriterAdmissionAdapter:
    """把现有两阶段 Writer Admission 适配为 Novel Domain 单一端口。"""

    def __init__(self, service: WriterAdmissionService) -> None:
        self._service = service

    def admit(self, request: NovelAdmissionRequest) -> object:
        if not request.contract_id.strip() or not request.run_id.strip():
            raise NovelWriterAdmissionError("novel_admission_request_invalid")
        try:
            grant = self._service.pre_admit(PreAdmissionRequest(request.contract_id))
            self._service.validate_grant_for_context(grant)
            return self._service.finalize_admission(
                grant,
                context_fingerprint=request.context_fingerprint,
                run_id=request.run_id,
            )
        except WriterAdmissionError as error:
            raise NovelWriterAdmissionError(str(error)) from error

