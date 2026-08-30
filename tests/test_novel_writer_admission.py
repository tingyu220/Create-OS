from creative_os.domains.novel_writer_admission import (
    NovelAdmissionRequest,
    NovelWriterAdmissionAdapter,
)


class _AdmissionService:
    def __init__(self):
        self.calls = []

    def pre_admit(self, request):
        self.calls.append(("pre", request.contract_id))
        return "grant"

    def validate_grant_for_context(self, grant):
        self.calls.append(("validate", grant))

    def finalize_admission(self, grant, context_fingerprint, run_id):
        self.calls.append(("finalize", grant, context_fingerprint, run_id))
        return "token"


def test_adapter_executes_existing_two_phase_admission_in_order():
    service = _AdmissionService()
    adapter = NovelWriterAdmissionAdapter(service)

    token = adapter.admit(NovelAdmissionRequest("contract-1", "f" * 64, "run-1"))

    assert token == "token"
    assert [call[0] for call in service.calls] == ["pre", "validate", "finalize"]
